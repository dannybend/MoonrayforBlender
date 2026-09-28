#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
#
# Builds and installs moonray_bridge into /opt/MoonRay/bridge.
# Usage: wsl -d AlmaLinux-9 -u root -- bash /mnt/c/.../wsl/build_bridge.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/../bridge"
BUILD=/opt/MoonRay/build-bridge
PREFIX=/opt/MoonRay/bridge

export PATH=/installs/cmake-3.23.1-linux-x86_64/bin:$PATH
# setup.sh reads unset variables (PYTHONPATH...), which breaks under set -u
set +u
source /opt/MoonRay/installs/openmoonray/scripts/setup.sh >/dev/null
set -u

cmake -S "$SRC" -B "$BUILD" -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" -j "${JOBS:-8}"
cmake --install "$BUILD"
install -m 755 "$HERE/run_bridge.sh" "$PREFIX/run_bridge.sh"
echo "moonray_bridge installed in $PREFIX/bin (launcher: $PREFIX/run_bridge.sh)"
