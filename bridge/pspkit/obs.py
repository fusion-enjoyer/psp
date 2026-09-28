"""Minimal obs-websocket v5 client (stdlib only): OBS 28+ has the server built in.

Enable it in OBS: Tools -> WebSocket Server Settings.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time

RETRY_AFTER_S = 5.0


class OBSError(RuntimeError):
    pass


class _WebSocket:
    """Just enough RFC 6455 for a text-frame JSON protocol."""

    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                           "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: obswebsocket.json\r\n\r\n")
                          .encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise OBSError("OBS bağlantıyı kapattı")
            head += chunk
        head, self.pending = head.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise OBSError("OBS websocket el sıkışması başarısız")

    def _recv_exact(self, n: int) -> bytes:
        while len(self.pending) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise OBSError("OBS bağlantıyı kapattı")
            self.pending += chunk
        out, self.pending = self.pending[:n], self.pending[n:]
        return out

    def send_text(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def recv_text(self) -> str:
        while True:
            b0, b1 = self._recv_exact(2)
            opcode, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                (n,) = struct.unpack(">H", self._recv_exact(2))
            elif n == 127:
                (n,) = struct.unpack(">Q", self._recv_exact(8))
            mask = self._recv_exact(4) if b1 & 0x80 else None
            data = self._recv_exact(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 0x1:
                return data.decode()
            if opcode == 0x8:
                raise OBSError("OBS bağlantıyı kapattı")
            if opcode == 0x9:  # ping -> pong
                self.sock.sendall(bytes([0x8A, 0x80 | len(data)]) + b"\0\0\0\0" + data)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class OBSClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 4455, password: str = ""):
        self.host, self.port, self.password = host, port, password
        self.ws: _WebSocket | None = None
        self.lock = threading.Lock()
        self.next_try = 0.0
        self.seq = 0

    def configure(self, host: str, port: int, password: str) -> None:
        with self.lock:
            if (host, port, password) != (self.host, self.port, self.password):
                self.host, self.port, self.password = host, port, password
                self._drop()
                self.next_try = 0.0

    def _drop(self) -> None:
        if self.ws:
            self.ws.close()
        self.ws = None

    def _connect(self) -> _WebSocket:
        if self.ws:
            return self.ws
        if time.monotonic() < self.next_try:
            raise OBSError("OBS'e bağlanılamadı (birazdan tekrar denenecek)")
        ws = None
        try:
            ws = _WebSocket(self.host, self.port)
            hello = json.loads(ws.recv_text())
            if hello.get("op") != 0:
                raise OBSError("beklenmeyen OBS mesajı")
            identify = {"rpcVersion": 1, "eventSubscriptions": 0}
            auth = hello["d"].get("authentication")
            if auth:
                if not self.password:
                    raise OBSError("OBS şifre istiyor (Deck ayarları > OBS)")
                secret = base64.b64encode(hashlib.sha256((self.password + auth["salt"]).encode()).digest())
                identify["authentication"] = base64.b64encode(
                    hashlib.sha256(secret + auth["challenge"].encode()).digest()).decode()
            ws.send_text(json.dumps({"op": 1, "d": identify}))
            reply = json.loads(ws.recv_text())
            if reply.get("op") != 2:
                raise OBSError("OBS kimlik doğrulaması başarısız")
        except (OSError, ValueError, KeyError, OBSError) as e:
            if ws:
                ws.close()
            self.next_try = time.monotonic() + RETRY_AFTER_S
            if isinstance(e, OBSError):
                raise
            raise OBSError(f"OBS'e bağlanılamadı ({self.host}:{self.port})") from e
        ws.sock.settimeout(3.0)
        self.ws = ws
        return ws

    def request(self, request_type: str, data: dict | None = None) -> dict:
        with self.lock:
            for attempt in (1, 2):
                ws = self._connect()
                self.seq += 1
                req_id = f"pspkit-{self.seq}"
                try:
                    ws.send_text(json.dumps({"op": 6, "d": {"requestType": request_type,
                                                            "requestId": req_id,
                                                            "requestData": data or {}}}))
                    while True:
                        msg = json.loads(ws.recv_text())
                        if msg.get("op") == 7 and msg["d"].get("requestId") == req_id:
                            break
                except (OSError, OBSError, ValueError):
                    self._drop()
                    if attempt == 2:
                        raise OBSError("OBS bağlantısı koptu")
                    continue
                status = msg["d"]["requestStatus"]
                if not status.get("result"):
                    raise OBSError(status.get("comment") or f"OBS isteği başarısız ({status.get('code')})")
                return msg["d"].get("responseData") or {}
        raise OBSError("OBS isteği başarısız")

    def close(self) -> None:
        with self.lock:
            self._drop()
