from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from control_center.quickshare import config, receiver


class ConfigTests(unittest.TestCase):
    def _patched(self, tmp: str):
        return (
            patch.object(config, "CONFIG_DIR", Path(tmp)),
            patch.object(config, "CONFIG_FILE", Path(tmp) / "quickshare.json"),
        )

    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self._patched(tmp)
            with a, b:
                data = config.load_config()
                data.update(visibility="Everyone", auto_disable_minutes=30, ask_before_accept=False)
                config.save_config(data)
                loaded = config.load_config()
        self.assertEqual(loaded["visibility"], "Everyone")
        self.assertEqual(loaded["auto_disable_minutes"], 30)
        self.assertFalse(loaded["ask_before_accept"])

    def test_invalid_values_fall_back_to_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self._patched(tmp)
            with a, b:
                (Path(tmp) / "quickshare.json").write_text(
                    '{"visibility": "Nobody", "auto_disable_minutes": 7, "device_name": "  ", "speed_limit_mbps": 5}'
                )
                loaded = config.load_config()
        self.assertEqual(loaded["visibility"], "LAN")
        self.assertEqual(loaded["auto_disable_minutes"], 0)
        self.assertTrue(loaded["device_name"])
        self.assertNotIn("speed_limit_mbps", loaded)
        self.assertTrue(loaded["ask_before_accept"])


class ReceiverTests(unittest.TestCase):
    def test_remote_file_names_cannot_escape_the_download_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for hostile in ("../../etc/passwd", "/etc/passwd", "..\\..\\x", "..", ""):
                destination = receiver.unique_destination(folder, hostile)
                self.assertEqual(destination.parent, folder, hostile)

    def test_existing_files_are_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "photo.jpg").write_bytes(b"x")
            self.assertEqual(receiver.unique_destination(folder, "photo.jpg").name, "photo (1).jpg")


if __name__ == "__main__":
    unittest.main()
