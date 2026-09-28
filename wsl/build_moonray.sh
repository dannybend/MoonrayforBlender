#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
#
# Builds MoonRay inside WSL (AlmaLinux 9 / Rocky Linux 9).
# Usage (from Windows):
#   wsl -d AlmaLinux-9 -u root -- bash /mnt/c/.../wsl/build_moonray.sh [deps|moonray|all]
#
# GPU=1 builds the GPU (XPU) mode; it needs CUDA 11.8 (wsl/install_cuda.sh).
# From PowerShell: $env:WSLENV="GPU/u"; $env:GPU="1"; wsl -d AlmaLinux-9 -u root -- bash ...
#
# Requires, beforehand:
#   source /opt/MoonRay/source/openmoonray/building/Rocky9/install_packages.sh --nocuda
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEP="${1:-all}"
JOBS="${JOBS:-10}"          # WSL gets ~half the RAM by default; more jobs can run out of memory
ROOT=/opt/MoonRay
SRC=$ROOT/source/openmoonray
LOGS=$ROOT/logs

export PATH=/installs/cmake-3.23.1-linux-x86_64/bin:$PATH
mkdir -p "$LOGS" $ROOT/{installs,build,build-deps} $ROOT/installs/{bin,lib,include}

build_deps() {
    echo "[$(date +%T)] Building dependencies (log: $LOGS/deps.log)"
    cd $ROOT/build-deps
    cmake "$SRC/building/Rocky9" >"$LOGS/deps.log" 2>&1
    cmake --build . -- -j "$JOBS" >>"$LOGS/deps.log" 2>&1
    echo "[$(date +%T)] Dependencies OK"
}

build_moonray() {
    echo "[$(date +%T)] Building MoonRay (log: $LOGS/moonray.log)"
    # Lets XPU mode find the NVIDIA driver under WSL2
    python3 "$HERE/patch_moonray_wsl.py" "$SRC"
    cd "$SRC"
    if [ "${GPU:-0}" = "1" ]; then
        export PATH=/usr/local/cuda-11.8/bin:$PATH
        export CUDAToolkit_ROOT=/usr/local/cuda-11.8
        # Explicit: a previous configure without CUDA leaves NOTFOUND in the cache
        extra=(-DMOONRAY_USE_OPTIX=YES -DCMAKE_CUDA_COMPILER=/usr/local/cuda-11.8/bin/nvcc)
    else
        extra=(-DMOONRAY_USE_OPTIX=NO)
    fi
    cmake --preset rocky9-release "${extra[@]}" >"$LOGS/moonray.log" 2>&1
    cmake --build --preset rocky9-release -- -j "$JOBS" >>"$LOGS/moonray.log" 2>&1
    echo "[$(date +%T)] MoonRay OK -> $ROOT/installs/openmoonray"
}

case "$STEP" in
    deps)    build_deps ;;
    moonray) build_moonray ;;
    all)     build_deps; build_moonray ;;
    *)       echo "Unknown step: $STEP"; exit 1 ;;
esac
