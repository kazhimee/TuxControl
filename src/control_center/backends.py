"""Desktop discovery and safe system-management operations."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from html import unescape
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import urlencode

_SERVICE_NAME = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")
_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:-]*$")
_EXTENSION_UUID = re.compile(r"^[A-Za-z0-9_.+-]+@[A-Za-z0-9_.+-]+$")


@dataclass(frozen=True)
class DesktopInfo:
    desktop: str
    distribution: str


@dataclass(frozen=True)
class Service:
    name: str
    description: str
    active: bool
    enabled: bool
    enableable: bool
    scope: str


@dataclass(frozen=True)
class ExtensionCatalogItem:
    uuid: str
    name: str
    description: str
    creator: str = ""
    downloads: int = 0
    details_url: str = ""
    icon_url: str = ""


@dataclass(frozen=True)
class ExtensionStatus:
    uuid: str
    name: str
    enabled: bool
    active: bool


def run_command(
    args: Sequence[str],
    *,
    timeout: int = 30,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a fixed argument vector without a shell and preserve useful errors."""
    if not args or not all(isinstance(arg, str) for arg in args):
        raise ValueError("A command must be a non-empty sequence of strings.")
    result = subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "LC_ALL": "C"},
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail or f"{args[0]} exited with status {result.returncode}.")
    return result


def detect_desktop() -> DesktopInfo:
    session = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in session:
        desktop = "GNOME"
    elif "kde" in session or "plasma" in session:
        desktop = "KDE Plasma"
    else:
        desktop = session.upper() or "Unknown desktop"

    distro = "Linux"
    os_release = Path("/etc/os-release")
    if os_release.is_file():
        for line in os_release.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("PRETTY_NAME="):
                distro = line.split("=", 1)[1].strip().strip('"')
                break
    return DesktopInfo(desktop=desktop, distribution=distro)


def available_package_manager() -> str | None:
    for manager in ("apt-get", "dnf", "pacman", "zypper"):
        if shutil.which(manager):
            return manager
    return None


def validate_service_name(name: str) -> str:
    if not _SERVICE_NAME.fullmatch(name):
        raise ValueError("Invalid service name.")
    return name


def validate_package_name(name: str) -> str:
    if not _PACKAGE_NAME.fullmatch(name):
        raise ValueError("Enter a valid package name.")
    return name


def validate_extension_uuid(uuid: str) -> str:
    if not _EXTENSION_UUID.fullmatch(uuid):
        raise ValueError("Enter a valid GNOME extension UUID.")
    return uuid


def _list_services(scope: str) -> list[Service]:
    if not shutil.which("systemctl"):
        raise RuntimeError("systemctl is required to manage services.")
    if scope not in {"user", "system"}:
        raise ValueError("Unsupported service scope.")
    prefix = ["--user"] if scope == "user" else []
    result = run_command(
        ["systemctl", *prefix, "list-units", "--type=service", "--all", "--no-legend", "--plain", "--no-pager"],
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Could not read {scope} services.")

    file_states_result = run_command(
        ["systemctl", *prefix, "list-unit-files", "--type=service", "--no-legend", "--no-pager"],
        check=False,
    )
    if file_states_result.returncode:
        raise RuntimeError(
            file_states_result.stderr.strip() or f"Could not read {scope} service enablement states."
        )
    file_states: dict[str, str] = {}
    for line in file_states_result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and _SERVICE_NAME.fullmatch(fields[0]):
            file_states[fields[0]] = fields[1]
    services: list[Service] = []
    for line in result.stdout.splitlines():
        fields = line.split(None, 4)
        if len(fields) < 4 or not _SERVICE_NAME.fullmatch(fields[0]):
            continue
        description = fields[4] if len(fields) > 4 else fields[0]
        file_state = file_states.get(fields[0], "unknown")
        services.append(
            Service(
                name=fields[0],
                description=description,
                active=fields[2] == "active",
                enabled=file_state in {"enabled", "enabled-runtime"},
                enableable=file_state
                in {"enabled", "enabled-runtime", "disabled", "linked", "linked-runtime", "alias"},
                scope=scope,
            )
        )
    return sorted(services, key=lambda service: service.name.casefold())


def list_user_services() -> list[Service]:
    return _list_services("user")


def list_system_services() -> list[Service]:
    return _list_services("system")


def manage_service(name: str, action: str, scope: str = "user") -> None:
    validate_service_name(name)
    allowed_actions = {"start", "stop", "enable", "disable"}
    if action not in allowed_actions:
        raise ValueError("Unsupported service action.")
    if scope not in {"user", "system"}:
        raise ValueError("Unsupported service scope.")
    if scope == "system":
        if not shutil.which("pkexec"):
            raise RuntimeError("pkexec is required to request administrator authorization.")
        run_command(["pkexec", "systemctl", action, name], timeout=120)
    else:
        run_command(["systemctl", "--user", action, name], timeout=60)


def manage_user_service(name: str, action: str) -> None:
    manage_service(name, action, "user")


def package_manager_command(package: str, action: str) -> list[str]:
    validate_package_name(package)
    if action not in {"install", "remove"}:
        raise ValueError("Unsupported package action.")
    manager = available_package_manager()
    if manager is None:
        raise RuntimeError("No supported system package manager was found.")

    prefix = ["pkexec"]
    if manager == "apt-get":
        return prefix + [manager, "-y", "--no-install-recommends", action, package]
    if manager == "dnf":
        return prefix + [manager, "-y", action, package]
    if manager == "pacman":
        return prefix + [manager, "--noconfirm", "-S" if action == "install" else "-R", package]
    return prefix + [manager, "--non-interactive", action, package]


def change_system_package(package: str, action: str) -> None:
    if not shutil.which("pkexec"):
        raise RuntimeError("pkexec is required to request administrator authorization.")
    run_command(package_manager_command(package, action), timeout=900)


def desktop_app_package(desktop_file: str) -> str | None:
    """Return the package manager's owner for a launcher, where available."""
    if not Path(desktop_file).is_absolute():
        return None
    probes: list[list[str]] = []
    if shutil.which("dpkg-query"):
        probes.append(["dpkg-query", "-S", desktop_file])
    if shutil.which("rpm"):
        probes.append(["rpm", "-qf", "--qf", "%{NAME}", desktop_file])
    if shutil.which("pacman"):
        probes.append(["pacman", "-Qoq", desktop_file])
    for command in probes:
        result = run_command(command, check=False)
        if not result.returncode:
            owner = result.stdout.split(":", 1)[0].split(",", 1)[0].strip()
            try:
                return validate_package_name(owner)
            except ValueError:
                continue
    return None


def installed_flatpaks() -> list[tuple[str, str]]:
    if not shutil.which("flatpak"):
        return []
    result = run_command(
        ["flatpak", "list", "--user", "--app", "--columns=application,name"],
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Could not list Flatpak applications.")
    apps = []
    for line in result.stdout.splitlines():
        fields = line.split("\t", 1)
        if fields and fields[0]:
            apps.append((fields[0], fields[1] if len(fields) > 1 else fields[0]))
    return sorted(apps, key=lambda app: app[1].casefold())


def install_flatpak(app_id: str, remote: str = "flathub") -> None:
    validate_flatpak_app_id(app_id)
    if remote not in {"flathub"}:
        raise ValueError("Unsupported Flatpak remote.")
    if not shutil.which("flatpak"):
        raise RuntimeError("Flatpak is not installed.")
    run_command(
        ["flatpak", "install", "--user", "--noninteractive", remote, app_id],
        timeout=900,
    )


def remove_flatpak(app_id: str) -> None:
    validate_flatpak_app_id(app_id)
    run_command(["flatpak", "uninstall", "--user", "--noninteractive", app_id], timeout=900)


def validate_flatpak_app_id(app_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+", app_id):
        raise ValueError("Enter a valid Flatpak application ID.")
    return app_id


def list_gnome_extensions() -> list[ExtensionStatus]:
    if not shutil.which("gnome-extensions"):
        raise RuntimeError("gnome-extensions is required to manage GNOME Shell extensions.")
    result = run_command(["gnome-extensions", "list"], check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Could not list GNOME extensions.")
    extensions: list[ExtensionStatus] = []
    for uuid in result.stdout.splitlines():
        uuid = uuid.strip()
        if _EXTENSION_UUID.fullmatch(uuid):
            state = run_command(["gnome-extensions", "info", uuid], check=False)
            if state.returncode:
                raise RuntimeError(state.stderr.strip() or f"Could not inspect GNOME extension {uuid}.")
            lines = state.stdout.splitlines()
            name = uuid
            enabled: bool | None = None
            active = False
            for line in lines:
                if line.startswith("  Name: "):
                    name = line.partition(":")[2].strip() or uuid
                elif line.startswith("  Enabled: "):
                    enabled = line.partition(":")[2].strip().casefold() == "yes"
                elif line.startswith("  State: "):
                    active = line.partition(":")[2].strip().casefold() == "active"
            extensions.append(ExtensionStatus(uuid, name, active if enabled is None else enabled, active))
    return sorted(extensions, key=lambda extension: extension.name.casefold())


def search_gnome_extensions(query: str, limit: int = 30) -> list[ExtensionCatalogItem]:
    import json
    import ssl
    import urllib.request

    query = query.strip()
    if len(query) > 100:
        raise ValueError("Extension search text must be 100 characters or fewer.")
    if not 1 <= limit <= 50:
        raise ValueError("Extension search result limit is out of range.")
    if not shutil.which("gnome-shell"):
        raise RuntimeError("GNOME Shell is required to search compatible extensions.")
    version_result = run_command(["gnome-shell", "--version"], check=False)
    version_match = re.search(r"(\d+)\.(\d+)", version_result.stdout)
    if not version_match:
        raise RuntimeError("Could not determine the installed GNOME Shell version.")

    major_version = version_match.group(1)
    params = urlencode(
        {"shell_version": major_version, **({"search": query} if query else {})}
    )
    request = urllib.request.Request(
        f"https://extensions.gnome.org/extension-query/?{params}",
        headers={"User-Agent": "Linux-Control-Center/0.1"},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=20, context=ssl.create_default_context()
        ) as response:
            payload = json.load(response)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not search extensions.gnome.org: {error}") from error

    rows = payload.get("extensions") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("The GNOME extension catalog returned an unexpected response.")
    results: list[ExtensionCatalogItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        uuid = row.get("uuid")
        name = row.get("name")
        description = row.get("description", "")
        creator = row.get("creator", "")
        downloads = row.get("downloads", 0)
        link = row.get("link", "")
        icon = row.get("icon", "")
        if (
            isinstance(uuid, str)
            and _EXTENSION_UUID.fullmatch(uuid)
            and isinstance(name, str)
            and isinstance(description, str)
            and isinstance(creator, str)
        ):
            details_url = f"https://extensions.gnome.org{link}" if isinstance(link, str) and link.startswith("/") else ""
            icon_url = f"https://extensions.gnome.org{icon}" if isinstance(icon, str) and icon.startswith("/") else ""
            results.append(
                ExtensionCatalogItem(
                    uuid=uuid,
                    name=name[:160],
                    description=unescape(re.sub(r"<[^>]*>", "", description))[:400],
                    creator=creator[:120],
                    downloads=downloads if isinstance(downloads, int) else 0,
                    details_url=details_url,
                    icon_url=icon_url,
                )
            )
        if len(results) >= limit:
            break
    return results


def set_gnome_extension(uuid: str, enabled: bool) -> None:
    validate_extension_uuid(uuid)
    action = "enable" if enabled else "disable"
    run_command(["gnome-extensions", action, uuid])


def uninstall_gnome_extension(uuid: str) -> None:
    validate_extension_uuid(uuid)
    run_command(["gnome-extensions", "uninstall", uuid], timeout=60)


def install_gnome_extension(uuid: str) -> None:
    """Fetch a compatible extension from extensions.gnome.org and install as the user."""
    import json
    import ssl
    import urllib.parse
    import urllib.request
    import zipfile
    from io import BytesIO

    validate_extension_uuid(uuid)
    shell_version = None
    if shutil.which("gnome-shell"):
        version_result = run_command(["gnome-shell", "--version"], check=False)
        version_match = re.search(r"(\d+\.\d+)", version_result.stdout)
        shell_version = version_match.group(1) if version_match else None
    if shell_version is None:
        raise RuntimeError("Could not determine the installed GNOME Shell version.")

    base = "https://extensions.gnome.org"
    major_version = shell_version.split(".", 1)[0]
    query = urllib.parse.urlencode({"uuid": uuid, "shell_version": major_version})
    context = ssl.create_default_context()
    request = urllib.request.Request(
        f"{base}/extension-info/?{query}",
        headers={"User-Agent": "Linux-Control-Center/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            details = json.load(response)
        version_map = details.get("shell_version_map", {})
        version = version_map.get(shell_version) or version_map.get(major_version)
        version_tag = version.get("version") if isinstance(version, dict) else None
        if not version_tag:
            raise RuntimeError(f"No compatible release was found for GNOME Shell {shell_version}.")
        download = f"{base}/download-extension/{urllib.parse.quote(uuid, safe='')}?version_tag={version_tag}"
        with urllib.request.urlopen(
            urllib.request.Request(download, headers={"User-Agent": "Linux-Control-Center/0.1"}),
            timeout=60,
            context=context,
        ) as response:
            archive = response.read(20 * 1024 * 1024 + 1)
        if len(archive) > 20 * 1024 * 1024:
            raise RuntimeError("Extension archive exceeds the 20 MiB size limit.")
        with zipfile.ZipFile(BytesIO(archive)) as package:
            metadata_file = package.getinfo("metadata.json") if "metadata.json" in package.namelist() else None
            if metadata_file is None:
                raise RuntimeError("The downloaded archive is not a GNOME extension.")
            if metadata_file.file_size > 1024 * 1024:
                raise RuntimeError("GNOME extension metadata exceeds the 1 MiB size limit.")
            metadata = json.loads(package.read(metadata_file))
        if metadata.get("uuid") != uuid:
            raise RuntimeError("Extension UUID does not match the requested extension.")
        command = shutil.which("gnome-extensions")
        if not command:
            raise RuntimeError("gnome-extensions is not installed.")
        with tempfile.NamedTemporaryFile(suffix=".shell-extension.zip") as temporary:
            temporary.write(archive)
            temporary.flush()
            run_command([command, "install", "--force", temporary.name], timeout=120)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not download or verify the extension: {error}") from error
