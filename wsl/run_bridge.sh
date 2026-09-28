#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
#
# Starts moonray_bridge with MoonRay's environment loaded.
# The Blender add-on launches it automatically; to run it by hand:
#   wsl -d AlmaLinux-9 -- bash /opt/MoonRay/bridge/run_bridge.sh --port 5577
source /opt/MoonRay/installs/openmoonray/scripts/setup.sh >/dev/null

# WSL2: the GPU driver libraries live in /usr/lib/wsl/lib. OptiX dlopen()s
# "libnvoptix.so.1", but that file's SONAME is libnvoptix_loader.so.1, so the
# ldconfig cache doesn't list it under the name OptiX asks for.
if [ -d /usr/lib/wsl/lib ]; then
    export LD_LIBRARY_PATH=/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
fi

exec /opt/MoonRay/bridge/bin/moonray_bridge "$@"
