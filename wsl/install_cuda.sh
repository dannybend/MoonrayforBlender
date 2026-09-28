#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
#
# Installs the CUDA 11.8 compiler, needed to build MoonRay's GPU (XPU) mode.
# Under WSL the driver comes from Windows (/usr/lib/wsl/lib): do NOT install
# NVIDIA driver packages inside the distribution, only the toolkit.
set -euo pipefail

dnf config-manager --add-repo https://developer.download.nvidia.com/compute/cuda/repos/rhel9/x86_64/cuda-rhel9.repo
dnf install -y cuda-toolkit-11-8

/usr/local/cuda-11.8/bin/nvcc --version | tail -2
