#!/usr/bin/env bash
# Builds tuxcontrol-VERSION.tar.gz, an archive with install.sh / uninstall.sh.
# Usage: packaging/build-tarball.sh [VERSION] [OUTPUT_DIR]
set -euo pipefail
. "$(dirname "$0")/common.sh"
version="$(resolve_version "${1:-}")"
output_dir="$(resolve_output_dir "${2:-}")"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

top="$stage/tuxcontrol-$version"
mkdir -p "$top/payload"
cp -a "$source_root/src/control_center" "$top/payload/"
find "$top" -name '__pycache__' -type d -prune -exec rm -rf {} +
cp -a "$source_root/packaging/launchers" "$source_root/packaging/desktop" "$top/payload/"
cp "$source_root/tuxcenter.png" "$top/payload/"
cp "$source_root/packaging/installer/install.sh" "$source_root/packaging/installer/uninstall.sh" "$top/"
cp "$source_root/LICENSE" "$source_root/README.md" "$top/"
tar --owner=0 --group=0 -C "$stage" -czf "$output_dir/tuxcontrol-${version}.tar.gz" "tuxcontrol-$version"
echo "Built: $output_dir/tuxcontrol-${version}.tar.gz"
