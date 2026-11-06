#!/usr/bin/env bash
# Builds .deb, .rpm, .tar.gz and the portable archive into dist/.
# Usage: packaging/build-all.sh [VERSION] [OUTPUT_DIR]
set -euo pipefail
dir="$(dirname "$0")"
"$dir/build-deb.sh" "$@"
"$dir/build-rpm.sh" "$@"
"$dir/build-tarball.sh" "$@"
"$dir/build-portable.sh" "$@"
