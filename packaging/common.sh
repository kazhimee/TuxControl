#!/usr/bin/env bash
# Shared helpers for the package builders. Source this file; do not run it.

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

resolve_version() {
  local version="${1:-$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$source_root/pyproject.toml" | head -n 1)}"
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo "VERSION must be a semantic version such as 1.2.3." >&2
    return 2
  }
  printf '%s' "$version"
}

resolve_output_dir() {
  local dir="${1:-$source_root/dist}"
  mkdir -p "$dir"
  (cd "$dir" && pwd)
}

# stage_tree DESTDIR PREFIX
# Installs the program below DESTDIR/PREFIX. Launchers are rewritten so that
# they find the library directory under PREFIX at runtime.
stage_tree() {
  local root="$1" prefix="$2"
  local libdir="$prefix/lib/tuxcontrol"
  local target="$root$prefix"
  install -d "$target/bin" "$target/lib/tuxcontrol" "$target/share/applications" \
    "$target/share/icons/hicolor/256x256/apps" "$target/share/doc/tuxcontrol"
  cp -a "$source_root/src/control_center" "$target/lib/tuxcontrol/"
  find "$target/lib/tuxcontrol" -name '__pycache__' -type d -prune -exec rm -rf {} +
  find "$target/lib/tuxcontrol" -type d -exec chmod 0755 {} +
  find "$target/lib/tuxcontrol" -type f -exec chmod 0644 {} +
  install -m 0644 "$source_root/tuxcenter.png" "$target/lib/tuxcontrol/tuxcenter.png"
  install -m 0644 "$source_root/tuxcenter.png" "$target/share/icons/hicolor/256x256/apps/tuxcontrol.png"
  install -m 0644 "$source_root"/packaging/desktop/*.desktop "$target/share/applications/"
  install -m 0644 "$source_root/LICENSE" "$target/share/doc/tuxcontrol/copyright"
  local launcher
  for launcher in "$source_root"/packaging/launchers/*; do
    sed "s|@LIBDIR@|$libdir|g" "$launcher" > "$target/bin/$(basename "$launcher")"
    chmod 0755 "$target/bin/$(basename "$launcher")"
  done
}
