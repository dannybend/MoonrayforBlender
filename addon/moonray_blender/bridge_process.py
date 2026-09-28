# SPDX-License-Identifier: GPL-3.0-or-later
#
# Starting moonray_bridge inside WSL.

import subprocess
import sys
import threading

from .client import wait_for_port

_process = None
_lock = threading.Lock()
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def is_listening(prefs, timeout=0.5):
    return wait_for_port(prefs.host, prefs.port, timeout)


def ensure_running(prefs):
    """Makes sure a moonray_bridge is listening, launching it if needed."""
    global _process
    with _lock:
        if is_listening(prefs):
            return
        if not prefs.autostart and _process is None:
            raise RuntimeError(
                f"moonray_bridge is not listening on {prefs.host}:{prefs.port} "
                "and auto-start is disabled"
            )
        if _process is None or _process.poll() is not None:
            cmd = [
                "wsl.exe", "-d", prefs.wsl_distro, "-u", prefs.wsl_user, "--",
                "bash", prefs.bridge_script, "--port", str(prefs.port),
            ]
            print("[MoonRay] Launching:", " ".join(cmd))
            _process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=_NO_WINDOW,
            )
            threading.Thread(target=_pump_output, args=(_process,), daemon=True).start()

        # The first time, WSL may take a while to boot the distribution
        if not wait_for_port(prefs.host, prefs.port, timeout=30.0):
            code = _process.poll()
            raise RuntimeError(
                "moonray_bridge did not start"
                + (f" (exit code {code})" if code is not None else "")
                + ". Check Blender's system console."
            )


def _pump_output(proc):
    for line in iter(proc.stdout.readline, b""):
        print("[moonray_bridge]", line.decode("utf-8", "replace").rstrip())


def stop(prefs=None):
    global _process
    with _lock:
        if _process is not None and _process.poll() is None:
            _process.terminate()
        _process = None
        if prefs is not None:
            # Closing wsl.exe doesn't always kill the Linux process; kill it by name.
            subprocess.run(
                ["wsl.exe", "-d", prefs.wsl_distro, "-u", prefs.wsl_user, "--", "pkill", "-f", "moonray_bridge"],
                stdin=subprocess.DEVNULL, capture_output=True, creationflags=_NO_WINDOW,
            )
