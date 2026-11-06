#!/usr/bin/env bash
# Installs TuxControl from this archive.
#   ./install.sh                 installs to /usr/local as root, otherwise to ~/.local
#   ./install.sh --prefix DIR    installs to DIR
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
if [[ "$(id -u)" -eq 0 ]]; then prefix=/usr/local; else prefix="$HOME/.local"; fi
if [[ "${1:-}" == "--prefix" ]]; then
  [[ -n "${2:-}" ]] || { echo "--prefix needs a directory." >&2; exit 2; }
  prefix="$2"
fi
mkdir -p "$prefix"
prefix="$(cd "$prefix" && pwd)"
libdir="$prefix/lib/tuxcontrol"
manifest_dir="$prefix/share/tuxcontrol"

rm -rf "$libdir"
install -d "$prefix/bin" "$libdir" "$prefix/share/applications" \
  "$prefix/share/icons/hicolor/256x256/apps" "$manifest_dir"
cp -a "$here/payload/control_center" "$libdir/"
install -m 0644 "$here/payload/tuxcenter.png" "$libdir/tuxcenter.png"
install -m 0644 "$here/payload/tuxcenter.png" "$prefix/share/icons/hicolor/256x256/apps/tuxcontrol.png"
install -m 0644 "$here"/payload/desktop/*.desktop "$prefix/share/applications/"
for launcher in "$here"/payload/launchers/*; do
  name="$(basename "$launcher")"
  sed "s|@LIBDIR@|$libdir|g" "$launcher" > "$prefix/bin/$name"
  chmod 0755 "$prefix/bin/$name"
done
# Record exactly what was installed so uninstall.sh removes nothing else.
{
  for launcher in "$here"/payload/launchers/*; do echo "$prefix/bin/$(basename "$launcher")"; done
  for desktop in "$here"/payload/desktop/*.desktop; do echo "$prefix/share/applications/$(basename "$desktop")"; done
  echo "$prefix/share/icons/hicolor/256x256/apps/tuxcontrol.png"
} > "$manifest_dir/installed-files.txt"
install -m 0755 "$here/uninstall.sh" "$manifest_dir/uninstall.sh"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$prefix/share/applications" || true
echo "TuxControl installed to $prefix."
echo "Uninstall with: $manifest_dir/uninstall.sh"
case ":$PATH:" in *":$prefix/bin:"*) ;; *) echo "Note: add $prefix/bin to your PATH." ;; esac
