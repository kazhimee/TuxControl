#!/usr/bin/env bash
# Usage: packaging/build-rpm.sh [VERSION] [OUTPUT_DIR]
set -euo pipefail
. "$(dirname "$0")/common.sh"
version="$(resolve_version "${1:-}")"
output_dir="$(resolve_output_dir "${2:-}")"
command -v rpmbuild >/dev/null 2>&1 || {
  echo "rpmbuild is required (for example: sudo apt install rpm)." >&2
  exit 1
}
build_root="$(mktemp -d)"
trap 'rm -rf "$build_root"' EXIT

mkdir -p "$build_root"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
source_stage="$build_root/tuxcontrol-${version}"
stage_tree "$source_stage" /usr
tar -C "$build_root" -czf "$build_root/SOURCES/tuxcontrol-${version}.tar.gz" "tuxcontrol-${version}"
cp "$source_root/packaging/rpm/tuxcontrol.spec" "$build_root/SPECS/tuxcontrol.spec"
rpmbuild --quiet -bb --define "_topdir $build_root" --define "pkgver $version" "$build_root/SPECS/tuxcontrol.spec" >/dev/null
find "$build_root/RPMS" -type f -name '*.rpm' -exec cp {} "$output_dir/" \;
echo "Built RPM package(s) in: $output_dir"
