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
if ! command -v rpmbuild >/dev/null 2>&1; then
  echo "rpmbuild is required. Install the RPM build tools (for example: sudo apt install rpm)." >&2
  exit 1
fi
output_dir="${2:-$source_root/dist}"
build_root="$(mktemp -d)"
trap 'rm -rf "$build_root"' EXIT

mkdir -p "$build_root"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS,rpmdb}
source_stage="$build_root/tuxcontrol-${version}"
mkdir -p "$source_stage"
cp -a "$source_root/src/control_center" "$source_stage/"
install -m 0644 "$source_root/org.tuxcontrol.App.desktop" "$source_stage/"
install -m 0644 "$source_root/LICENSE" "$source_stage/"
tar -C "$build_root" -czf "$build_root/SOURCES/tuxcontrol-${version}.tar.gz" \
  "tuxcontrol-${version}"
cp "$source_root/packaging/rpm/tuxcontrol.spec" "$build_root/SPECS/tuxcontrol.spec"
rpmbuild -bb \
  --define "_topdir $build_root" \
  --define "_dbpath $build_root/rpmdb" \
  --define "pkgver $version" \
  "$build_root/SPECS/tuxcontrol.spec"
mkdir -p "$output_dir"
find "$build_root/RPMS" -type f -name '*.rpm' -exec cp {} "$output_dir/" \;
echo "Built RPM package(s) in: $output_dir"
