#!/usr/bin/env bash
# Removes a TuxControl installation made by install.sh.
#   --purge  also deletes your Quick Share settings and its private Python environment
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
manifest="$here/installed-files.txt"
[[ -f "$manifest" ]] || { echo "No installation manifest found next to this script." >&2; exit 1; }
prefix="$(cd "$here/../.." && pwd)"
[[ "$(basename "$here")" == "tuxcontrol" && "$(basename "$(dirname "$here")")" == "share" ]] \
  || { echo "Run the uninstaller from the installed location." >&2; exit 1; }

while IFS= read -r file; do
  case "$file" in "$prefix"/*) rm -f -- "$file" ;; esac
done < "$manifest"
rm -rf -- "$prefix/lib/tuxcontrol" "$here"

if [[ "${1:-}" == "--purge" ]]; then
  rm -rf -- "${XDG_CONFIG_HOME:-$HOME/.config}/tuxcontrol" \
            "${XDG_DATA_HOME:-$HOME/.local/share}/tuxcontrol" \
            "${XDG_CACHE_HOME:-$HOME/.cache}/tuxcontrol"
fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$prefix/share/applications" || true
echo "TuxControl removed from $prefix."
