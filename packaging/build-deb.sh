#!/usr/bin/env bash
# Usage: packaging/build-deb.sh [VERSION] [OUTPUT_DIR]
set -euo pipefail
. "$(dirname "$0")/common.sh"
version="$(resolve_version "${1:-}")"
output_dir="$(resolve_output_dir "${2:-}")"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

pkg="$stage/tuxcontrol"
stage_tree "$pkg" /usr
install -d "$pkg/DEBIAN"
cat > "$pkg/DEBIAN/control" <<CONTROL
Package: tuxcontrol
Version: $version
Section: utils
Priority: optional
Architecture: all
Maintainer: Kazhime Kagemori <kazhimee@gmail.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, systemd
Recommends: gir1.2-ayatanaappindicator3-0.1, python3-venv, zenity
Homepage: https://github.com/kazhimee/TuxControl
Description: GNOME control center for applications, services, themes, and extensions
 TuxControl is an open-source GTK 4 application for managing GNOME applications,
 services, themes, and shell extensions. It also includes an optional Quick Share
 tray for receiving files from nearby Android devices.
CONTROL
for script in postinst postrm; do
  cat > "$pkg/DEBIAN/$script" <<'HOOK'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database -q /usr/share/applications || true; fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true; fi
exit 0
HOOK
  chmod 0755 "$pkg/DEBIAN/$script"
done
dpkg-deb --root-owner-group --build "$pkg" "$output_dir/tuxcontrol_${version}_all.deb" >/dev/null
echo "Built: $output_dir/tuxcontrol_${version}_all.deb"
