#!/usr/bin/env bash
# Builds tuxcontrol-VERSION-portable.tar.gz: unpack anywhere and run ./tuxcontrol.
# Includes an .itch.toml so the itch.io app knows what to launch.
# Usage: packaging/build-portable.sh [VERSION] [OUTPUT_DIR]
set -euo pipefail
. "$(dirname "$0")/common.sh"
version="$(resolve_version "${1:-}")"
output_dir="$(resolve_output_dir "${2:-}")"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

top="$stage/tuxcontrol-portable"
mkdir -p "$top"
cp -a "$source_root/src/control_center" "$top/"
find "$top" -name '__pycache__' -type d -prune -exec rm -rf {} +
cp "$source_root"/packaging/launchers/* "$top/"
chmod 0755 "$top"/tuxcontrol*
cp "$source_root/tuxcenter.png" "$source_root/LICENSE" "$top/"
cat > "$top/.itch.toml" <<'ITCH'
[[actions]]
name = "TuxControl"
path = "tuxcontrol"

[[actions]]
name = "Quick Share tray"
path = "tuxcontrol-quickshare-tray"
ITCH
cat > "$top/README.txt" <<'TXT'
TuxControl (portable)

Run ./tuxcontrol. Requires Python 3.10+, GTK 4 and PyGObject
(Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0).
Quick Share: run ./tuxcontrol-quickshare-tray (installs its extras on request).
Nothing is installed system-wide; delete this folder to remove the program.
Settings live in ~/.config/tuxcontrol and ~/.local/share/tuxcontrol.
TXT
tar --owner=0 --group=0 -C "$stage" -czf "$output_dir/tuxcontrol-${version}-portable.tar.gz" tuxcontrol-portable
echo "Built: $output_dir/tuxcontrol-${version}-portable.tar.gz"
