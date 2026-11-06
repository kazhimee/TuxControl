# TuxControl

> **Support status: GNOME only. KDE Plasma is not supported yet.**

TuxControl is an open-source GTK 4 desktop control panel for Linux. It currently provides:

- Launching installed desktop applications and removing Flatpak, Snap, package-managed or user-launcher apps.
- Installing a system package through the distribution's package manager.
- Listing and controlling user-session and system-wide systemd services (PolicyKit authorization for system-wide changes).
- Browsing GNOME-Look.org and Pling catalogs in a separate window, downloading supported themes, installing GTK/icon/Plasma archives into user folders, and applying/removing themes.
- Receiving files from nearby Android devices through an optional Quick Share tray.
- Showing active versus disabled GNOME Shell extensions; browsing the compatible extensions.gnome.org catalog in a separate window, installing by search result or UUID, enabling, disabling, and uninstalling extensions.

**GitHub description:** An open-source GNOME control center for apps, services, themes, and extensions.

**Suggested GitHub topics:** `linux`, `gnome`, `gtk4`, `python`, `themes`, `gnome-extensions`.

## Support

TuxControl is free and open source. Support development, read devlogs and get new releases first on [Patreon](https://patreon.com/kazhimee).

## Project contacts

- Developer: Kazhime Kagemori
- Developer email: kazhimee@gmail.com
- Contact email: kazhimeofficial@gmail.com
- License: GNU General Public License v3.0 (GPL-3.0-only)

Contributions are welcome under the terms of the GNU General Public License v3.0.

## Requirements

- Linux with Python 3.10 or newer (Python 3.14 tested)
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

This project is licensed under the GNU General Public License v3.0. See [LICENSE](./LICENSE) for the full license text.

## Quick Share (receive from Android)

Run `tuxcontrol-quickshare-tray` (or use **Start Quick Share tray** in the Quick Share tab). On first start it offers to install `pystray`, `Pillow` and `pyquickshare` into a private virtualenv at `~/.local/share/tuxcontrol/venv`; the system Python is never modified. The tray starts and stops the receiver for you.

- **Visibility**: nearby devices (LAN), everyone, or closed. Closed stops the receiver.
- **Device name**, **download folder**, **auto-stop timer** and **ask before accepting** are configurable in the Quick Share tab or in `tuxcontrol-quickshare-settings`. Settings are stored in `~/.config/tuxcontrol/quickshare.json`.
- Incoming transfers show a confirmation dialog (needs `zenity` or `kdialog`); without a dialog tool they are declined. File names from the sender are reduced to a plain name and never overwrite existing files.
- GNOME needs the *AppIndicator and KStatusNotifierItem Support* extension and `gir1.2-ayatanaappindicator3-0.1` (Debian/Ubuntu) to display the tray icon.
- **Sending**: tray menu → *Send files…*, the *Send files…* button in the Quick Share tab, or `tuxcontrol-quickshare-send FILE…`. Pick files, then pick a nearby device. The phone must have Quick Share open, be unlocked and receive from *Everyone*; devices in contacts-only (hidden) mode are not listed. Speed limiting is not implemented. The `pyquickshare` package declares Python 3.10 only; the launcher installs it with `--ignore-requires-python`, and it has been verified to import on Python 3.14.

## Removing applications

The Applications tab detects how an app was installed and asks for confirmation: user or system Flatpak, Snap, a system package (APT/DNF/Pacman/Zypper via `pkexec`), or a launcher file in your home folder (only the `.desktop` file is deleted). Critical system packages are protected.

## Packages

Build everything into `dist/` with `packaging/build-all.sh [VERSION]` (needs `dpkg-deb` and `rpmbuild`), or one at a time:

| Package | Script | Output |
| --- | --- | --- |
| Debian | `packaging/build-deb.sh` | `tuxcontrol_VERSION_all.deb` |
| RPM | `packaging/build-rpm.sh` | `tuxcontrol-VERSION-1.noarch.rpm` |
| Tarball with installer | `packaging/build-tarball.sh` | `tuxcontrol-VERSION.tar.gz` |
| Portable (itch.io) | `packaging/build-portable.sh` | `tuxcontrol-VERSION-portable.tar.gz` |

The tarball contains `install.sh` (installs to `/usr/local` as root, otherwise `~/.local`; `--prefix DIR` overrides) and a matching `uninstall.sh` that is also copied to `<prefix>/share/tuxcontrol/`. `uninstall.sh --purge` additionally deletes Quick Share settings and its virtualenv. The portable archive runs in place with `./tuxcontrol` and includes an `.itch.toml` launch manifest; upload it to itch.io with `butler push dist/tuxcontrol-VERSION-portable.tar.gz USER/GAME:linux`.

Removing the `.deb`/`.rpm` with the package manager does not touch per-user data; delete `~/.config/tuxcontrol` and `~/.local/share/tuxcontrol` manually if wanted. Tagged GitHub releases (`v*`) publish all four files.
