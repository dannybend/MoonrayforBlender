#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
#
# One-time setup of a fresh AlmaLinux 9 WSL distribution for building MoonRay:
# system packages, the OpenMoonRay sources and the CMake version it needs.
#
# Usage (from Windows, after `wsl --install -d AlmaLinux-9 --no-launch`):
#   wsl -d AlmaLinux-9 -u root -- bash /mnt/c/.../wsl/setup_wsl.sh
set -euo pipefail

ROOT=/opt/MoonRay
SRC=$ROOT/source/openmoonray

dnf install -y epel-release
dnf install -y git git-lfs which tar python3
git lfs install

mkdir -p $ROOT/{installs,build,build-deps,source,logs} $ROOT/installs/{bin,lib,include}
if [ ! -d "$SRC" ]; then
    git clone --recurse-submodules https://github.com/OpenMoonRay/openmoonray.git "$SRC"
fi

# The official script must be sourced. libcgroup (optional, used only by Arras)
# may fail to download; that is harmless.
cd "$SRC"
set +eu
source building/Rocky9/install_packages.sh --nocuda
set -eu

/installs/cmake-3.23.1-linux-x86_64/bin/cmake --version | head -1
echo "Setup done. Next: wsl/build_moonray.sh all"
