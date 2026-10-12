# TuxControl

> **Support status: GNOME only. KDE Plasma is not supported yet.**

TuxControl is an open-source GTK 4 desktop control panel for Linux. It currently provides:

- Launching installed desktop applications and removing supported Flatpak or package-managed apps.
- Installing a system package through the distribution's package manager.
- Listing and controlling user-session and system-wide systemd services (PolicyKit authorization for system-wide changes).
- Browsing GNOME-Look.org and Pling catalogs in a separate window, downloading supported themes, installing GTK/icon/Plasma archives into user folders, and applying/removing themes.
- Showing active versus disabled GNOME Shell extensions; browsing the compatible extensions.gnome.org catalog in a separate window, installing by search result or UUID, enabling, disabling, and uninstalling extensions.

**GitHub description:** An open-source GNOME control center for apps, services, themes, and extensions.

**Suggested GitHub topics:** `linux`, `gnome`, `gtk4`, `python`, `themes`, `gnome-extensions`.

## Project contacts

- Developer: Kazhime Kagemori
- Developer email: kazhimee@gmail.com
- Contact email: kazhimeofficial@gmail.com
- License: MIT (open source)

Contributions are welcome under the terms of the MIT License.

## Requirements

- Linux with Python 3.10 or newer
- GTK 4 and PyGObject (`python3-gi` / `python3-gobject`)
- systemd for service management
- Optional: Flatpak, `gnome-extensions` and GNOME Shell, `pkexec` and one supported package manager

GTK and PyGObject should be installed from your distribution packages; they are not Python-pip dependencies.

## Run from a checkout

On Debian/Ubuntu, install the runtime prerequisites first:

```sh
sudo apt install python3-gi gir1.2-gtk-4.0
```

From the project directory, launch it directly:

```sh
PYTHONPATH=src python3 -m control_center.app
```

To install the `tuxcontrol` launcher command instead:

```sh
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -e .
tuxcontrol
```

GNOME-specific installation dependencies may also be installed by your distribution package manager:

```sh
sudo apt install gnome-shell gnome-shell-extensions
```

## Security and scope

- Commands are invoked as argument arrays, never through a shell.
- System package changes use `pkexec`, so the system authorization dialog is separate from the application. The app does not run as root.
- Service actions are always confirmed. User services run through `systemctl --user`; system-wide actions invoke `pkexec systemctl` and require separate administrator authorization.
- Flatpak operations use the current user's installation and install only from Flathub.
- Theme archive paths, file count, and expanded size are checked before installing into user GTK, icon, or Plasma theme folders. Only themes inside user theme folders can be removed.
- GNOME extension downloads use HTTPS from extensions.gnome.org and verify the returned UUID before installation.
- Review every confirmation before applying changes. Package removal can remove dependencies according to your distribution's package manager.

## Supported package managers

APT, DNF, Pacman, and Zypper are detected for system package installation/removal. Desktop app package-owner lookup is supported for Debian, RPM, and Pacman-based systems. Unsupported distributions can still use Flatpak where available. Theme search uses the public Open Collaboration Services (OCS) API and downloads files from the GNOME-Look.org / Pling domains.

## Development

Run the tests with:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

This project is licensed under the MIT License. It is ready to publish to GitHub; add a remote repository URL when creating the upstream repository.

## Release packages

Tagged GitHub releases (`v*`) are configured to publish Debian `.deb`, RPM `.rpm`, and Arch Linux `.pkg.tar.zst` installation packages. Arch users can also use the `packaging/arch/PKGBUILD` recipe.

From the project root, build a package using the version in `pyproject.toml`:

```sh
./packaging/build-deb.sh
./packaging/build-rpm.sh
./packaging/build-arch.sh
```

Alternatively, run `./build-deb.sh`, `./build-rpm.sh`, or `./build-arch.sh` from inside `packaging/`. To choose a version explicitly, pass it as the first argument, for example `./packaging/build-deb.sh 0.1.0`. Packages are written to `dist/`. The RPM builder needs `rpmbuild`. The Arch builder uses `makepkg` on Arch Linux, or Docker to build inside an Arch Linux container on other distributions.
