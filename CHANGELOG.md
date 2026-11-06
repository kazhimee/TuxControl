# Changelog

## 0.1.1 — unreleased changes

### Quick Share
- Fixed the receiver connection: it is now a separate process supervised by the tray, started and stopped by the **Visibility** menu (LAN / Everyone / Closed) instead of being disconnected from it.
- Fixed declined transfers hanging forever (they are now explicitly rejected) and the confirmation dialog freezing the receiver (dialogs are asynchronous, with a 60 s timeout).
- Fixed received files being written to a relative `downloads/` folder in the working directory; they now go to the configured folder. Sender-supplied file names are reduced to a plain name (no path traversal) and never overwrite existing files.
- The configured device name is now actually advertised (the library hardcoded `pyquickshare`).
- Added a configurable auto-stop timer that really closes visibility, and desktop notification when files arrive.
- `pyquickshare` is installed by the tray launcher with `--ignore-requires-python` into a private venv (works on Python 3.14); the install location moved to `~/.local/share/tuxcontrol/venv` so it also works from system packages.
- Only one Quick Share tray can run at a time: a second launch exits immediately instead of creating a duplicate icon and receiver (lock file in `$XDG_RUNTIME_DIR`).
- Tray icon lookup, status line in the tray menu, crash back-off and clean shutdown of the receiver.

### Interface
- **Support on Patreon** button on the About page (`DONATE_URL` in `app.py`; hidden if emptied, https only).
- Applications list: each app shows its description under the name, buttons are vertically centred and Remove uses the destructive style. Nothing else was restyled.

### Sending files
- Quick Share can now send as well as receive. New send window (`tuxcontrol-quickshare-send`, tray menu *Send files…*, button in the Quick Share tab, desktop-entry action): choose one or more files, see nearby devices live, press Send.
- The protocol runs in a separate worker (`quickshare/sender.py`) in the private venv and talks to the window over a JSON-lines pipe, so the GTK app never blocks. Failures the library only logs are caught and shown instead of reporting a false success; reverse-DNS lookups that could stall for many seconds are skipped; the computer's own receiver is hidden from the list.
- Fixed phones never being listed: pyquickshare reads the visibility bit of the mDNS record from the wrong position and treats every device as hidden. The sender now decodes the record itself and patches the library's parser so sending to visible devices works. A phone that registers several services is listed once.
- Limitation: only devices visible to everyone are listed (no QR/contacts-only mode).

### Settings
- New **Quick Share** tab in the app and a standalone `tuxcontrol-quickshare-settings` window: visibility, device name, download folder (with folder picker), auto-stop timer, ask-before-accept.
- Settings are validated on load and save; unknown or invalid values fall back to safe defaults.
- Removed the speed-limit option because nothing could enforce it.

### Application removal
- Before removing, a confirmation window lists what will happen: for system packages the exact packages that will be removed (with a warning when other packages depend on it) and the installed files; for Flatpak/Snap/launchers the command and what is kept.
- Removal now opens a progress window with a spinner and the live output of the package tool, and reports success or the failure reason.
- Removal now identifies the installation source in a background thread (the UI no longer freezes on package queries) and shows a specific confirmation: user/system Flatpak, Snap, system package, or user launcher file.
- Added system-wide Flatpak and Snap support, and deletion of orphan launchers in the home folder (only the `.desktop` file).
- Critical packages (python3, systemd, gnome-shell, GTK, package managers, …) are protected.
- APT removal runs non-interactively; the Remove button is no longer disabled when no package manager is detected.
- The list drops launchers that no longer exist, so removed apps disappear immediately.
- Added `uninstall.sh` (with `--purge`) for the tarball install.

### Packaging
- Packages: `.deb`, `.rpm`, `.tar.gz` (with `install.sh`/`uninstall.sh`) and a portable archive for itch.io (with `.itch.toml`). Build all with `packaging/build-all.sh`.
- All formats share `packaging/common.sh` and the same launchers, so every package now includes the Quick Share modules, tray, settings, icon and a second desktop entry (previously `.deb`/`.rpm` shipped only top-level modules and no icon).
- Launchers moved to `packaging/launchers/`, desktop files to `packaging/desktop/`; the app icon is installed as `tuxcontrol`.
- Added post-install/post-remove icon and desktop-database refresh for `.deb` and `.rpm`.
- The release workflow is a single job building and publishing the four files.

### Removed
- Arch Linux packaging (`PKGBUILD`, `build-arch.sh`, Docker build, CI job).
- Redundant `install-quickshare-deps.sh`, `run-quickshare-tray.sh`, root `build-portable.sh`, `QUICKSHARE-EXPERIMENTAL.md`, the committed `dist/` and `src/tuxcontrol.egg-info/` build output.
- `tray` extra replaced by a `quickshare` extra in `pyproject.toml`.

### Tests
- Added tests for removal planning, protected packages, user-launcher deletion, config sanitising and file-name safety.
