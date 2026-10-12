from __future__ import annotations

import tempfile
import unittest
import zipfile
import json
import tarfile
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from control_center import backends, themes


class ValidationTests(unittest.TestCase):
    def test_service_validation_rejects_command_injection(self) -> None:
        with self.assertRaises(ValueError):
            backends.validate_service_name("demo.service;touch /tmp/oops")

    def test_package_validation_rejects_options_and_commands(self) -> None:
        for invalid in ("--remove-all", "demo;echo", ""):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                backends.validate_package_name(invalid)

    def test_extension_uuid_validation_requires_uuid_shape(self) -> None:
        self.assertEqual(backends.validate_extension_uuid("example@gnome.org"), "example@gnome.org")
        with self.assertRaises(ValueError):
            backends.validate_extension_uuid("https://example.org")

    def test_package_commands_use_authorization_and_fixed_arguments(self) -> None:
        with patch.object(backends, "available_package_manager", return_value="apt-get"):
            self.assertEqual(
                backends.package_manager_command("example-app", "install"),
                ["pkexec", "apt-get", "-y", "--no-install-recommends", "install", "example-app"],
            )

    def test_system_service_action_uses_pkexec_and_validated_arguments(self) -> None:
        with (
            patch.object(backends.shutil, "which", return_value="/usr/bin/pkexec"),
            patch.object(backends, "run_command") as run,
        ):
            backends.manage_service("example.service", "stop", "system")
        run.assert_called_once_with(
            ["pkexec", "systemctl", "stop", "example.service"],
            timeout=120,
        )

    def test_user_service_action_does_not_request_system_authorization(self) -> None:
        with patch.object(backends, "run_command") as run:
            backends.manage_service("example.service", "start", "user")
        run.assert_called_once_with(
            ["systemctl", "--user", "start", "example.service"],
            timeout=60,
        )

    def test_extension_catalog_search_validates_and_sanitizes_results(self) -> None:
        response_data = json.dumps(
            {
                "extensions": [
                    {
                        "uuid": "example@gnome.org",
                        "name": "Example Extension",
                        "description": "<p>Useful &amp; safe</p>",
                        "creator": "Example Author",
                        "downloads": 1234,
                        "link": "/extension/123/example/",
                        "icon": "/extension-data/icons/icon_123.png",
                    },
                    {"uuid": "bad uuid", "name": "Invalid", "description": "Ignored"},
                ]
            }
        ).encode()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return response_data

        with (
            patch.object(backends.shutil, "which", return_value="/usr/bin/gnome-shell"),
            patch.object(
                backends,
                "run_command",
                return_value=CompletedProcess(
                    ["gnome-shell"], 0, stdout="GNOME Shell 46.2\n", stderr=""
                ),
            ),
            patch("urllib.request.urlopen", return_value=Response()),
        ):
            results = backends.search_gnome_extensions("  clipboard  ")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].uuid, "example@gnome.org")
        self.assertEqual(results[0].description, "Useful & safe")
        self.assertEqual(results[0].creator, "Example Author")
        self.assertEqual(results[0].downloads, 1234)
        self.assertEqual(
            results[0].details_url,
            "https://extensions.gnome.org/extension/123/example/",
        )
        self.assertEqual(
            results[0].icon_url,
            "https://extensions.gnome.org/extension-data/icons/icon_123.png",
        )

    def test_extension_status_parses_enabled_and_active_separately(self) -> None:
        command_results = [
            CompletedProcess(
                ["gnome-extensions", "list"],
                0,
                stdout="active@example.org\ndisabled@example.org\n",
                stderr="",
            ),
            CompletedProcess(
                ["gnome-extensions", "info"],
                0,
                stdout=(
                    "active@example.org\n"
                    "  Name: Active Extension\n"
                    "  Enabled: Yes\n"
                    "  State: ACTIVE\n"
                ),
                stderr="",
            ),
            CompletedProcess(
                ["gnome-extensions", "info"],
                0,
                stdout=(
                    "disabled@example.org\n"
                    "  Name: Disabled Extension\n"
                    "  Enabled: No\n"
                    "  State: INITIALIZED\n"
                ),
                stderr="",
            ),
        ]
        with (
            patch.object(backends.shutil, "which", return_value="/usr/bin/gnome-extensions"),
            patch.object(backends, "run_command", side_effect=command_results),
        ):
            extensions = backends.list_gnome_extensions()
        self.assertEqual(
            [(item.uuid, item.name, item.enabled, item.active) for item in extensions],
            [
                ("active@example.org", "Active Extension", True, True),
                ("disabled@example.org", "Disabled Extension", False, False),
            ],
        )


class ThemeTests(unittest.TestCase):
    def test_store_search_parses_catalog_and_rejects_untrusted_downloads(self) -> None:
        xml = b"""<?xml version="1.0"?>
        <ocs><meta><status>ok</status></meta><data>
          <content><id>12345</id><name>Night &amp; Day</name>
            <typename>GTK Themes</typename><summary>&lt;p&gt;A theme&lt;/p&gt;</summary>
            <downloadname1>night.tar.gz</downloadname1>
            <downloadlink1>https://files.pling.com/api/files/123</downloadlink1>
            <detailpage>https://www.gnome-look.org/p/12345</detailpage>
            <personname>Theme Author</personname><version>2.1</version>
            <downloads>987</downloads><description>&lt;p&gt;Full details&lt;/p&gt;</description>
            <previewpic1>https://www.gnome-look.org/p/12345/preview</previewpic1>
          </content>
          <content><id>12346</id><name>Unsafe</name>
            <downloadlink1>https://evil.example/theme.zip</downloadlink1>
          </content>
        </data></ocs>"""

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return "https://api.pling.com/ocs/v1/content/data?search=night"

            def read(self, *_args):
                return xml

        with patch("control_center.themes.urlopen", return_value=Response()):
            results = themes.search_store_themes("pling", "night")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Night & Day")
        self.assertEqual(results[0].category, "GTK Themes")
        self.assertEqual(results[0].summary, "A theme")
        self.assertEqual(results[0].author, "Theme Author")
        self.assertEqual(results[0].version, "2.1")
        self.assertEqual(results[0].downloads, 987)
        self.assertEqual(results[0].description, "Full details")
        self.assertEqual(
            results[0].preview_url,
            "https://www.gnome-look.org/p/12345/preview",
        )

    def test_empty_theme_search_requests_latest_catalog_items(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return "https://api.pling.com/ocs/v1/content/data?page=1&pagesize=30"

            def read(self, *_args):
                return b"""<ocs><meta><status>ok</status></meta><data/></ocs>"""

        with patch("control_center.themes.urlopen") as open_url:
            open_url.return_value = Response()
            self.assertEqual(themes.search_store_themes("pling", ""), [])
        request = open_url.call_args.args[0]
        self.assertNotIn("search=", request.full_url)

    def test_installs_tar_gz_theme_from_pling_style_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            archive_path = home / "theme.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                for name, content in (
                    ("ExampleTheme/gtk-3.0/gtk.css", b"/* theme */"),
                    ("ExampleTheme/gtk-4.0/gtk.css", b"/* theme */"),
                ):
                    data = BytesIO(content)
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    archive.addfile(info, data)
            with patch.object(themes.Path, "home", return_value=home):
                installed = themes.install_theme_archive(archive_path)
            self.assertEqual(installed, home / ".local/share/themes/ExampleTheme")
            self.assertTrue((installed / "gtk-3.0/gtk.css").is_file())

    def test_rejects_symlinks_in_tar_theme_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            archive_path = home / "unsafe.tar"
            with tarfile.open(archive_path, "w") as archive:
                symlink = tarfile.TarInfo("ExampleTheme/gtk-3.0/gtk.css")
                symlink.type = tarfile.SYMTYPE
                symlink.linkname = "/etc/passwd"
                archive.addfile(symlink)
                file_data = BytesIO(b"theme")
                regular = tarfile.TarInfo("ExampleTheme/index.theme")
                regular.size = 5
                archive.addfile(regular, file_data)
            with patch.object(themes.Path, "home", return_value=home):
                with self.assertRaises(ValueError):
                    themes.install_theme_archive(archive_path)
            self.assertFalse((home / "ExampleTheme").exists())

    def test_installs_single_theme_archive_into_user_theme_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            archive_path = home / "example.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("Example/index.theme", "[Desktop Entry]\n")
                archive.writestr("Example/gtk-3.0/gtk.css", "/* theme */")
            with patch.object(themes.Path, "home", return_value=home):
                installed = themes.install_theme_archive(archive_path)
                self.assertEqual(installed, home / ".local/share/themes/Example")
                self.assertTrue((installed / "index.theme").is_file())

    def test_rejects_archive_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            archive_path = home / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape/index.theme", "[Desktop Entry]\n")
            with patch.object(themes.Path, "home", return_value=home):
                with self.assertRaises(ValueError):
                    themes.install_theme_archive(archive_path)
                self.assertFalse((home.parent / "escape").exists())

    def test_installs_plasma_theme_into_plasma_theme_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            archive_path = home / "plasma-theme.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("BreezeExtra/metadata.desktop", "[Desktop Entry]\n")
                archive.writestr("BreezeExtra/contents/widgets/button.svg", "<svg/>")
            with patch.object(themes.Path, "home", return_value=home):
                installed = themes.install_theme_archive(archive_path)
                self.assertEqual(
                    installed,
                    home / ".local/share/plasma/desktoptheme/BreezeExtra",
                )
                self.assertTrue((installed / "contents/widgets/button.svg").is_file())

    def test_preserves_gtk_directory_when_archive_has_no_outer_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            archive_path = home / "plain-theme.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("gtk-3.0/gtk.css", "/* theme */")
            with patch.object(themes.Path, "home", return_value=home):
                installed = themes.install_theme_archive(archive_path)
                self.assertEqual(installed.name, "plain-theme")
                self.assertTrue((installed / "gtk-3.0/gtk.css").is_file())

    def test_removal_is_limited_to_user_theme_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            allowed = home / ".local/share/themes/Example"
            allowed.mkdir(parents=True)
            outside = home / "Example"
            outside.mkdir()
            with patch.object(themes.Path, "home", return_value=home):
                themes.remove_user_theme(allowed)
                self.assertFalse(allowed.exists())
                with self.assertRaises(ValueError):
                    themes.remove_user_theme(outside)

    def test_removal_refuses_symlinked_theme_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            external = Path(temporary) / "external"
            home.mkdir()
            external.mkdir()
            theme = external / "Example"
            theme.mkdir()
            user_theme_root = home / ".local/share/themes"
            user_theme_root.parent.mkdir(parents=True)
            user_theme_root.symlink_to(external, target_is_directory=True)
            with patch.object(themes.Path, "home", return_value=home):
                with self.assertRaises(ValueError):
                    themes.remove_user_theme(user_theme_root / "Example")
                self.assertTrue(theme.exists())


if __name__ == "__main__":
    unittest.main()
