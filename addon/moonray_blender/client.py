# SPDX-License-Identifier: GPL-3.0-or-later
#
# TCP client for moonray_bridge.
#
# A reader thread receives frames and messages; Blender's main thread sends
# the scene and consumes the latest frame with take_frame(). Only one frame is
# in flight at a time: the bridge waits for an ACK before sending the next.

import socket
import threading
import time

import numpy as np

from . import protocol as P


class BridgeError(Exception):
    pass


class Frame:
    __slots__ = ("width", "height", "progress", "complete", "pixels")

    def __init__(self, width, height, progress, complete, pixels):
        self.width = width
        self.height = height
        self.progress = progress
        self.complete = complete
        self.pixels = pixels  # np.float32, shape (height * width * 4,)


class BridgeClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._sock = None
        self._send_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._frame = None
        self._frame_event = threading.Event()
        self._welcome = threading.Event()
        self._reader = None
        self.connected = False
        self.complete = False
        self.version = ""
        self.errors = []
        self.logs = []

    # -- connection ----------------------------------------------------------

    def connect(self, timeout=2.0):
        try:
            sock = socket.create_connection((self.host, self.port), timeout=timeout)
        except OSError as e:
            raise BridgeError(f"Could not connect to moonray_bridge at {self.host}:{self.port}: {e}") from e
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(None)
        self._sock = sock
        self.connected = True
        self._reader = threading.Thread(target=self._read_loop, name="moonray-bridge-reader", daemon=True)
        self._reader.start()

    def hello(self, threads=0, fps=20.0, exec_mode="", timeout=30.0):
        lines = [f"fps={fps}"]
        if threads > 0:
            lines.append(f"threads={threads}")
        if exec_mode:
            lines.append(f"exec_mode={exec_mode}")
        self.send(P.HELLO, "\n".join(lines).encode())
        if not self._welcome.wait(timeout):
            raise BridgeError("moonray_bridge did not answer the handshake")
        if not self.connected:
            raise BridgeError("moonray_bridge closed the connection: " + "; ".join(self.errors))

    def close(self):
        if not self._sock:
            return
        try:
            self.send(P.BYE)
        except OSError:
            pass
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()
        self._sock = None
        self.connected = False

    # -- sending -----------------------------------------------------------

    def send(self, msg_type, payload=b""):
        if not self._sock:
            raise BridgeError("Not connected to moonray_bridge")
        header = P.HEADER.pack(P.MAGIC, msg_type, len(payload))
        with self._send_lock:
            self._sock.sendall(header)
            if payload:
                self._sock.sendall(payload)

    def send_rdla(self, text):
        if text:
            self.send(P.RDLA, text.encode("utf-8"))

    def start(self):
        self.complete = False
        # Drop any stale frame: it belongs to the previous scene state
        with self._frame_lock:
            stale = self._frame is not None
            self._frame = None
        if stale:
            self.send(P.ACK)
        self.send(P.START)

    def stop(self):
        self.send(P.STOP)

    # -- receiving ---------------------------------------------------------

    def take_frame(self):
        """Returns the latest frame (or None) and lets the bridge send the next one."""
        with self._frame_lock:
            frame = self._frame
            self._frame = None
            self._frame_event.clear()
        if frame is not None and self.connected:
            try:
                self.send(P.ACK)
            except OSError:
                pass
        return frame

    def wait_frame(self, timeout):
        self._frame_event.wait(timeout)
        return self.take_frame()

    def _recv_exact(self, size):
        buf = bytearray(size)
        view = memoryview(buf)
        pos = 0
        while pos < size:
            n = self._sock.recv_into(view[pos:], size - pos)
            if n == 0:
                raise ConnectionError("connection closed")
            pos += n
        return buf

    def _read_loop(self):
        try:
            while True:
                magic, msg_type, size = P.HEADER.unpack(self._recv_exact(P.HEADER.size))
                if magic != P.MAGIC:
                    raise ConnectionError("invalid reply from the bridge")
                payload = self._recv_exact(size) if size else bytearray()
                self._dispatch(msg_type, payload)
        except (OSError, ConnectionError, AttributeError) as e:
            if self._sock is not None:
                self.errors.append(f"Lost connection to moonray_bridge: {e}")
        finally:
            self.connected = False
            self._welcome.set()
            self._frame_event.set()

    def _dispatch(self, msg_type, payload):
        if msg_type == P.FRAME:
            w, h, channels, flags, progress, _ = P.FRAME_HEADER.unpack_from(payload, 0)
            pixels = np.frombuffer(payload, dtype=np.float32, offset=P.FRAME_HEADER.size, count=w * h * channels)
            frame = Frame(w, h, progress, bool(flags & P.FRAME_FLAG_COMPLETE), pixels)
            with self._frame_lock:
                self._frame = frame
            self._frame_event.set()
        elif msg_type == P.COMPLETE:
            self.complete = True
            self._frame_event.set()
        elif msg_type == P.WELCOME:
            self.version = payload.decode("utf-8", "replace")
            self._welcome.set()
        elif msg_type == P.LOG:
            self.logs.append(payload.decode("utf-8", "replace"))
            del self.logs[:-200]
        elif msg_type == P.ERROR:
            text = payload.decode("utf-8", "replace")
            print("[MoonRay] ERROR:", text)
            self.errors.append(text)


def wait_for_port(host, port, timeout):
    """Waits until something is listening on host:port."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False
