"""User-local theme discovery and archive installation."""

from __future__ import annotations

import os
import re
import shutil
import stat
import html
import configparser
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

MAX_ARCHIVE_SIZE = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 5000
_THEME_MARKERS = {
    "index.theme",
    "metadata.desktop",
    "metadata.json",
    "gtk.css",
}
_ARCHIVE_LAYOUT_DIRS = {
    "gtk-2.0", "gtk-3.0", "gtk-4.0", "contents", "cursors", "scalable",
    "16x16", "22x22", "24x24", "32x32", "48x48", "64x64", "128x128",
    "256x256", "512x512",
}


@dataclass(frozen=True)
class Theme:
    name: str
    path: Path
    user_owned: bool
    kind: str


@dataclass(frozen=True)
class StoreTheme:
    content_id: str
    name: str
    category: str
    summary: str
    download_name: str
    download_url: str
    detail_url: str
    author: str = ""
    version: str = ""
    downloads: int = 0
    description: str = ""
    preview_url: str = ""


def theme_directories() -> list[tuple[Path, str]]:
    home = Path.home()
    return [
        (home / ".themes", "gtk"),
        (home / ".local/share/themes", "gtk"),
        (home / ".local/share/icons", "icons"),
        (home / ".local/share/plasma/desktoptheme", "plasma"),
        (home / ".local/share/plasma/look-and-feel", "look-and-feel"),
        (Path("/usr/share/themes"), "gtk"),
        (Path("/usr/share/icons"), "icons"),
        (Path("/usr/share/plasma/desktoptheme"), "plasma"),
        (Path("/usr/share/plasma/look-and-feel"), "look-and-feel"),
    ]


def list_themes() -> list[Theme]:
    themes: dict[tuple[str, str], Theme] = {}
    for root, kind in theme_directories():
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and not child.is_symlink():
                key = (kind, child.name)
                themes.setdefault(key, Theme(child.name, child, root.is_relative_to(Path.home()), kind))
    return sorted(themes.values(), key=lambda theme: (theme.name.casefold(), theme.kind))


def active_theme_names(desktop: str) -> set[tuple[str, str]]:
    active: set[tuple[str, str]] = set()
    if desktop == "GNOME":
        for schema, key, kind in (
            ("org.gnome.desktop.interface", "gtk-theme", "gtk"),
            ("org.gnome.shell.extensions.user-theme", "name", "gtk"),
        ):
            result = subprocess.run(
                ["gsettings", "get", schema, key],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                name = result.stdout.strip().strip("'\"")
                if name and name != "''":
                    active.add((kind, name))
    elif desktop == "KDE Plasma":
        config = configparser.ConfigParser()
        config_path = Path.home() / ".config/plasmarc"
        try:
            config.read(config_path, encoding="utf-8")
            plasma_theme = config.get("Theme", "name", fallback="").strip()
            if plasma_theme:
                active.add(("plasma", plasma_theme))
        except (OSError, configparser.Error):
            pass
    return active


def _safe_theme_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "", name).strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("The archive does not contain a valid theme name.")
    return cleaned[:100]


def _trusted_store_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    trusted = (
        "pling.com",
        "opendesktop.org",
        "gnome-look.org",
    )
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and parsed.port in (None, 443)
        and any(
        host == domain or host.endswith(f".{domain}") for domain in trusted
        )
    )


def _plain_store_text(value: str, limit: int) -> str:
    return html.unescape(re.sub(r"<[^>]*>", " ", value)).strip()[:limit]


def search_store_themes(store: str, query: str, limit: int = 30) -> list[StoreTheme]:
    query = query.strip()
    if len(query) > 100:
        raise ValueError("Search text must be 100 characters or fewer.")
    if not 1 <= limit <= 50:
        raise ValueError("Search result limit is out of range.")
    hosts = {
        "gnome-look": "api.gnome-look.org",
        "pling": "api.pling.com",
    }
    if store not in hosts:
        raise ValueError("Choose GNOME-Look.org or Pling.")
    host = hosts[store]
    params = {"pagesize": limit, "page": 1}
    if query:
        params["search"] = query
    query_string = urlencode(params)
    request = Request(
        f"https://{host}/ocs/v1/content/data?{query_string}",
        headers={"User-Agent": "TuxControl/0.1", "Accept": "application/xml"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            if urlparse(response.geturl()).hostname != host:
                raise RuntimeError("Theme store redirected to an unexpected server.")
            payload = response.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise RuntimeError("Theme catalog response exceeds the 2 MiB size limit.")
        root = ET.fromstring(payload)
    except (OSError, ET.ParseError) as error:
        raise RuntimeError(f"Could not search {store}: {error}") from error
    if root.findtext("./meta/status") != "ok":
        raise RuntimeError(root.findtext("./meta/message") or "The theme store rejected the search.")

    results: list[StoreTheme] = []
    for item in root.findall("./data/content"):
        content_id = item.findtext("id") or ""
        name = item.findtext("name") or ""
        download_url = item.findtext("downloadlink1") or ""
        download_name = item.findtext("downloadname1") or name
        detail_url = item.findtext("detailpage") or ""
        category = item.findtext("typename") or "Theme"
        summary = item.findtext("summary") or ""
        description = item.findtext("description") or summary
        preview_url = item.findtext("previewpic1") or ""
        author = item.findtext("personname") or item.findtext("personid") or ""
        version = item.findtext("version") or ""
        downloads_text = item.findtext("downloads") or "0"
        if not content_id.isdigit() or not name or not _trusted_store_url(download_url):
            continue
        results.append(
            StoreTheme(
                content_id=content_id,
                name=html.unescape(name)[:180],
                category=html.unescape(category)[:100],
                summary=_plain_store_text(summary, 350),
                download_name=Path(urlparse(download_name).path).name[:180],
                download_url=download_url,
                detail_url=detail_url if _trusted_store_url(detail_url) else "",
                author=html.unescape(author)[:120],
                version=html.unescape(version)[:80],
                downloads=int(downloads_text) if downloads_text.isdigit() else 0,
                description=_plain_store_text(description, 3000),
                preview_url=preview_url if _trusted_store_url(preview_url) else "",
            )
        )
        if len(results) >= limit:
            break
    return results


def download_and_install_store_theme(theme: StoreTheme) -> Path:
    if not _trusted_store_url(theme.download_url):
        raise ValueError("The theme download URL is not from a trusted store domain.")
    request = Request(
        theme.download_url,
        headers={"User-Agent": "TuxControl/0.1"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            if not _trusted_store_url(response.geturl()):
                raise RuntimeError("Theme download redirected to an unexpected server.")
            with tempfile.NamedTemporaryFile(prefix="tuxcontrol-theme-") as downloaded:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_ARCHIVE_SIZE:
                        raise RuntimeError("Theme download exceeds the 100 MiB size limit.")
                    downloaded.write(chunk)
                downloaded.flush()
                if not total:
                    raise RuntimeError("Theme store returned an empty download.")
                return install_theme_archive(downloaded.name, preferred_name=theme.name)
    except OSError as error:
        raise RuntimeError(f"Could not download the theme from its store: {error}") from error


def _ensure_user_theme_root(root: Path) -> None:
    relative = root.relative_to(Path.home())
    current = Path.home()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Theme folders cannot be installed through symbolic links.")
        if current.exists() and not current.is_dir():
            raise ValueError(f"Theme destination is not a directory: {current}")
        current.mkdir(exist_ok=True)


def _contains_theme_path_symlink(path: Path) -> bool:
    relative = path.relative_to(Path.home())
    current = Path.home()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def install_theme_archive(
    archive_path: str | Path,
    *,
    preferred_name: str | None = None,
) -> Path:
    source = Path(archive_path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("The downloaded theme is not a regular archive file.")
    if zipfile.is_zipfile(source):
        archive_type = "zip"
        archive = zipfile.ZipFile(source)
    elif tarfile.is_tarfile(source):
        archive_type = "tar"
        archive = tarfile.open(source, mode="r:*")
    else:
        raise ValueError("Theme store returned an unsupported archive format.")

    with archive:
        entries = archive.infolist() if archive_type == "zip" else archive.getmembers()
        if len(entries) > MAX_ARCHIVE_FILES:
            raise ValueError("Theme archive contains too many files.")
        total = sum(entry.file_size if archive_type == "zip" else entry.size for entry in entries)
        if total > MAX_ARCHIVE_SIZE:
            raise ValueError("Theme archive exceeds the 100 MiB size limit.")

        safe_entries = []
        theme_roots: set[str] = set()
        paths: list[PurePosixPath] = []
        for entry in entries:
            raw_name = entry.filename if archive_type == "zip" else entry.name
            path = PurePosixPath(raw_name)
            mode = entry.external_attr >> 16 if archive_type == "zip" else 0
            unsafe_link = stat.S_ISLNK(mode) if archive_type == "zip" else (
                entry.issym() or entry.islnk() or not (entry.isfile() or entry.isdir())
            )
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in raw_name
                or (path.parts and re.match(r"^[A-Za-z]:", path.parts[0]))
                or unsafe_link
            ):
                raise ValueError("Theme archive contains an unsafe path or symbolic link.")
            safe_entries.append((entry, path))
            paths.append(path)
            if path.name in _THEME_MARKERS:
                first_part = path.parts[0] if len(path.parts) > 1 else ""
                theme_roots.add("" if first_part in _ARCHIVE_LAYOUT_DIRS else first_part)
        if not theme_roots:
            raise ValueError("No recognized GTK or icon theme files were found in the archive.")
        if len(theme_roots) != 1:
            raise ValueError("Archive must contain exactly one theme at its root.")

        archive_root = next(iter(theme_roots))
        theme_name = _safe_theme_name(archive_root or preferred_name or source.stem)
        relative_paths = [
            PurePosixPath(*(path.parts[1:] if archive_root else path.parts))
            for path in paths
            if not archive_root or (path.parts and path.parts[0] == archive_root)
        ]
        plasma_package = (
            any("contents" in path.parts for path in relative_paths)
            and any(path.name in {"metadata.desktop", "metadata.json"} for path in relative_paths)
        )
        gtk_package = any(path.name in {"gtk.css", "gtkrc"} for path in relative_paths)
        if plasma_package:
            target_root = (
                Path.home() / ".local/share/plasma/look-and-feel"
                if any("lookandfeel" in path.parts for path in relative_paths)
                else Path.home() / ".local/share/plasma/desktoptheme"
            )
        elif gtk_package:
            target_root = Path.home() / ".local/share/themes"
        elif any(path.name == "index.theme" for path in relative_paths):
            target_root = Path.home() / ".local/share/icons"
        else:
            raise ValueError("Archive does not contain a supported GTK, icon, or Plasma theme.")
        _ensure_user_theme_root(target_root)
        target = target_root / theme_name
        if target.exists():
            raise FileExistsError(f"A theme named “{theme_name}” is already installed.")

        staging = Path(tempfile.mkdtemp(prefix=".theme-install-", dir=target_root))
        extraction = Path(tempfile.mkdtemp(prefix=".tuxcontrol-unpack-", dir=Path.home()))
        try:
            seen_paths: set[PurePosixPath] = set()
            for entry, path in safe_entries:
                if path in seen_paths:
                    raise ValueError("Theme archive contains duplicate file paths.")
                seen_paths.add(path)
                if archive_root:
                    if not path.parts or path.parts[0] != archive_root:
                        continue
                    relative = Path(*path.parts[1:])
                else:
                    relative = Path(*path.parts)
                if not relative.parts:
                    continue
                output = extraction / relative
                if not output.resolve().is_relative_to(extraction.resolve()):
                    raise ValueError("Theme archive contains an unsafe path.")
                is_dir = entry.is_dir() if archive_type == "zip" else entry.isdir()
                if is_dir:
                    output.mkdir(parents=True, exist_ok=True)
                else:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    input_stream = (
                        archive.open(entry)
                        if archive_type == "zip"
                        else archive.extractfile(entry)
                    )
                    if input_stream is None:
                        raise ValueError("Theme archive contains an unreadable file.")
                    with input_stream, output.open("wb") as output_file:
                        shutil.copyfileobj(input_stream, output_file)
            extracted_root = extraction
            for child in extracted_root.iterdir():
                destination = staging / child.name
                if child.is_dir():
                    shutil.copytree(child, destination)
                else:
                    shutil.copy2(child, destination)
            os.replace(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(extraction, ignore_errors=True)
    return target


def remove_user_theme(theme_path: str | Path) -> None:
    unresolved_target = Path(theme_path).expanduser()
    allowed_roots = [
        Path.home() / ".themes",
        Path.home() / ".local/share/themes",
        Path.home() / ".local/share/icons",
        Path.home() / ".local/share/plasma/desktoptheme",
        Path.home() / ".local/share/plasma/look-and-feel",
    ]
    root = next(
        (
            candidate
            for candidate in allowed_roots
            if unresolved_target.absolute().parent == candidate.absolute()
        ),
        None,
    )
    if root is None:
        raise ValueError("Only a theme installed in your user theme folders can be removed.")
    if (
        _contains_theme_path_symlink(root)
        or _contains_theme_path_symlink(unresolved_target)
    ):
        raise ValueError("Symbolic links cannot be removed as themes.")
    if not unresolved_target.is_dir():
        raise ValueError("Selected theme is not a removable theme directory.")
    shutil.rmtree(unresolved_target)
