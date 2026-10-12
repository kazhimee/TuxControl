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
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT

if ! command -v makepkg >/dev/null 2>&1; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "makepkg is missing and Docker is unavailable. Run this on Arch Linux or install Docker." >&2
    exit 1
  fi
  docker_output="$build_dir/docker-output"
  mkdir -p "$docker_output"
  chmod 0777 "$docker_output"
  docker run --rm -i \
    -e TUXCONTROL_VERSION="$version" \
    -v "$source_root:/workspace:ro" \
    -v "$docker_output:/out" \
    archlinux:base-devel \
    bash -s -- "$version" <<'ARCH_BUILD'
set -euo pipefail
version="$1"
pacman -Sy --noconfirm
pacman -S --noconfirm --needed python python-gobject gtk4 systemd
useradd --create-home builder
cp -a /workspace /tmp/tuxcontrol
chown -R builder:builder /tmp/tuxcontrol /out
runuser -u builder -- env TUXCONTROL_VERSION="$version" \
  /bin/bash -c 'cd /tmp/tuxcontrol && packaging/build-arch.sh "$TUXCONTROL_VERSION" /out'
ARCH_BUILD
  shopt -s nullglob
  packages=("$docker_output"/*.pkg.tar.zst)
  if ((${#packages[@]} == 0)); then
    echo "The Arch Linux container did not produce a package." >&2
    exit 1
  fi
  cp "${packages[@]}" "$output_dir/"
  echo "Built Arch package(s) in: $output_dir"
  exit 0
fi

install -m 0644 "$source_root/packaging/arch/PKGBUILD" "$build_dir/PKGBUILD"
sed -i "s/^pkgver=.*/pkgver=$version/" "$build_dir/PKGBUILD"
tar -C "$source_root/src" -czf "$build_dir/tuxcontrol-${version}.tar.gz" \
  control_center
cp "$source_root/org.tuxcontrol.App.desktop" "$build_dir/"
cp "$source_root/LICENSE" "$build_dir/"
(cd "$build_dir" && makepkg --nodeps --noconfirm)
cp "$build_dir"/*.pkg.tar.zst "$output_dir/"
echo "Built Arch package(s) in: $output_dir"
