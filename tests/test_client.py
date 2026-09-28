# SPDX-License-Identifier: GPL-3.0-or-later
#
# Client test against a fake bridge speaking the same protocol.
#
# Usage:
#   blender --background --factory-startup --python tests/test_client.py

import os
import socket
import sys
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))

from moonray_blender import protocol as P  # noqa: E402
from moonray_blender.client import BridgeClient  # noqa: E402


def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError
        buf += chunk
    return buf


def send(conn, t, payload=b""):
    conn.sendall(P.HEADER.pack(P.MAGIC, t, len(payload)) + payload)


def fake_bridge(listener, log):
    conn, _ = listener.accept()
    w, h = 4, 2
    try:
        while True:
            magic, t, size = P.HEADER.unpack(recv_exact(conn, P.HEADER.size))
            payload = recv_exact(conn, size) if size else b""
            log.append(t)
            if t == P.HELLO:
                send(conn, P.WELCOME, b"fake 1")
            elif t == P.START:
                # Two progressive frames; the second only after the first is ACKed
                for k, progress in enumerate((0.5, 1.0)):
                    pixels = np.full(w * h * 4, k + 1, dtype=np.float32)
                    flags = P.FRAME_FLAG_COMPLETE if progress == 1.0 else 0
                    send(conn, P.FRAME, P.FRAME_HEADER.pack(w, h, 4, flags, progress, 0) + pixels.tobytes())
                    while True:
                        magic, t2, size2 = P.HEADER.unpack(recv_exact(conn, P.HEADER.size))
                        if size2:
                            recv_exact(conn, size2)
                        log.append(t2)
                        if t2 == P.ACK:
                            break
                send(conn, P.COMPLETE)
            elif t == P.BYE:
                break
    finally:
        conn.close()


def main():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    log = []
    server = threading.Thread(target=fake_bridge, args=(listener, log), daemon=True)
    server.start()

    client = BridgeClient("127.0.0.1", port)
    client.connect()
    client.hello(threads=2, fps=10)
    assert client.version == "fake 1", client.version

    client.send_rdla('SceneVariables { ["image_width"] = 4 }')
    client.start()

    frames = []
    while len(frames) < 2:
        f = client.wait_frame(5.0)
        assert f is not None, "frame did not arrive"
        frames.append(f)
    assert frames[0].progress == 0.5 and not frames[0].complete
    assert frames[1].complete and frames[1].pixels[0] == 2.0
    assert frames[1].pixels.shape == (4 * 2 * 4,)

    client.close()
    server.join(5.0)
    assert log[:3] == [P.HELLO, P.RDLA, P.START], log
    assert log.count(P.ACK) == 2, log
    assert log[-1] == P.BYE, log
    print("OK: client works", log)


try:
    main()
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
