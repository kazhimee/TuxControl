#!/usr/bin/env bash
set -euo pipefail

source_root="$(cd "$(dirname "$0")/.." && pwd)"
project_version="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$source_root/pyproject.toml" | head -n 1)"
version="${1:-$project_version}"
if [[ -z "$version" ]]; then
  echo "Could not read the project version from pyproject.toml." >&2
  exit 2
fi
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "VERSION must be a semantic version such as 1.2.3." >&2
  exit 2
}
output_dir="${2:-$source_root/dist}"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

package_root="$stage/tuxcontrol"
install -d "$package_root/DEBIAN" "$package_root/usr/lib/tuxcontrol/control_center"
install -d "$package_root/usr/bin" "$package_root/usr/share/applications"
install -d "$package_root/usr/share/doc/tuxcontrol"
install -m 0644 "$source_root"/src/control_center/*.py "$package_root/usr/lib/tuxcontrol/control_center/"
install -m 0644 "$source_root/org.tuxcontrol.App.desktop" \
  "$package_root/usr/share/applications/org.tuxcontrol.App.desktop"
install -m 0644 "$source_root/LICENSE" "$package_root/usr/share/doc/tuxcontrol/copyright"
cat > "$package_root/usr/bin/tuxcontrol" <<'LAUNCHER'
#!/bin/sh
export PYTHONPATH="/usr/lib/tuxcontrol${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m control_center.app "$@"
LAUNCHER
chmod 0755 "$package_root/usr/bin/tuxcontrol"
cat > "$package_root/DEBIAN/control" <<CONTROL
Package: tuxcontrol
Version: $version
Section: utils
Priority: optional
Architecture: all
Maintainer: Kazhime Kagemori <kazhimee@gmail.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, systemd
Description: GNOME control center for applications, services, themes, and extensions
 TuxControl is an open-source GTK 4 application for managing GNOME applications,
 services, themes, and shell extensions.
CONTROL
mkdir -p "$output_dir"
dpkg-deb --root-owner-group --build "$package_root" "$output_dir/tuxcontrol_${version}_all.deb"
echo "Built: $output_dir/tuxcontrol_${version}_all.deb"
