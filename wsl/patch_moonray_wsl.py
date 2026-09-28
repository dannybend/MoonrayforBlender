#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Makes MoonRay's GPU (XPU) mode work under WSL2.
#
# MoonRay reads the NVIDIA driver version from /sys/module/nvidia/version, which
# doesn't exist in WSL2 (the driver lives on the Windows side), so XPU mode
# always falls back to CPU. This patch adds a fallback that asks NVML
# (libnvidia-ml.so.1, which WSL does provide) for the driver version.
#
# Idempotent: running it twice doesn't patch twice.
# Usage: python3 wsl/patch_moonray_wsl.py [/opt/MoonRay/source/openmoonray]

import sys
from pathlib import Path

MARKER = "// WSL2 fallback (moonray-blender)"

FALLBACK = """    if (!success) {
        %s: WSL2 has no nvidia kernel module, so ask NVML.
        if (void* nvml = dlopen("libnvidia-ml.so.1", RTLD_LAZY)) {
            using InitFn = int (*)();
            using ShutdownFn = int (*)();
            using VersionFn = int (*)(char*, unsigned int);
            auto init = reinterpret_cast<InitFn>(dlsym(nvml, "nvmlInit_v2"));
            auto shutdown = reinterpret_cast<ShutdownFn>(dlsym(nvml, "nvmlShutdown"));
            auto getVersion = reinterpret_cast<VersionFn>(dlsym(nvml, "nvmlSystemGetDriverVersion"));
            if (init && getVersion && init() == 0) {
                char version[96] = {0};
                if (getVersion(version, sizeof(version)) == 0 &&
                    sscanf(version, "%%d.%%d", major, minor) == 2) {
                    success = true;
                }
                if (shutdown) shutdown();
            }
            dlclose(nvml);
        }
    }
    return success;""" % MARKER

FILES = [
    "moonray/moonray/lib/rendering/rt/gpu/optix/OptixGPUUtils.cc",
    "moonray/mcrt_denoise/lib/denoiser/OptixDenoiserImpl.cc",
]


def patch(path):
    text = path.read_text()
    if MARKER in text:
        print("already patched:", path)
        return
    start = text.index("getNVIDIADriverVersion(int* major, int* minor)\n{")
    end = text.index("    return success;", start)
    text = text[:end] + FALLBACK + text[end + len("    return success;"):]
    # dlopen/dlsym
    first_include = text.index("#include")
    text = text[:first_include] + "#include <dlfcn.h>\n" + text[first_include:]
    path.write_text(text)
    print("patched:", path)


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/MoonRay/source/openmoonray")
    for rel in FILES:
        patch(root / rel)


if __name__ == "__main__":
    main()
