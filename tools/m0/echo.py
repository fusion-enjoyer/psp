#!/usr/bin/env python3
"""pspkit M0 PC side: echo server for the link spike.

USB (default): connects to usbhostfs_pc's TCP port for async channel 4
(localhost:10004). TCP (--listen): waits for the PSP app to connect, which is
how PPSSPP (and later Wi-Fi) reaches the bridge (port 10200).

Answers pings and button presses, measures bulk throughput, prints the PSP's
self-test report and saves screenshots as PNG.

Type a line and press Enter to show it on the PSP; type /shot for a screenshot.
"""
import argparse
import select
import socket
import struct
import sys
import time
import zlib
from pathlib import Path

W, H = 480, 272


def connect(host: str, port: int) -> socket.socket:
    while True:
        try:
            sock = socket.create_connection((host, port), timeout=2)
            sock.settimeout(None)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print(f"[m0] {host}:{port} baglandi", flush=True)
            return sock
        except OSError as e:
            print(f"[m0] {host}:{port} bekleniyor ({e.strerror}); usbhostfs_pc calisiyor mu?", flush=True)
            time.sleep(1)


def listen(host: str, port: int):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(1)
    print(f"[m0] {host}:{port} dinleniyor; PSP/PPSSPP baglantisi bekleniyor", flush=True)
    while True:
        sock, peer = srv.accept()
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"[m0] PSP baglandi: {peer[0]}:{peer[1]}", flush=True)
        yield sock


def to_rgb(pixels: bytes, fmt: int) -> bytes:
    """PSP framebuffer (little endian, R in the low bits) to packed RGB."""
    if fmt == 3:  # 8888: bytes are R, G, B, A
        out = bytearray(len(pixels) // 4 * 3)
        out[0::3], out[1::3], out[2::3] = pixels[0::4], pixels[1::4], pixels[2::4]
        return bytes(out)
    out = bytearray()
    for (v,) in struct.iter_unpack("<H", pixels):
        if fmt == 0:    # 565
            r, g, b = v & 0x1F, (v >> 5) & 0x3F, (v >> 11) & 0x1F
            out += bytes((r * 255 // 31, g * 255 // 63, b * 255 // 31))
        elif fmt == 1:  # 5551
            r, g, b = v & 0x1F, (v >> 5) & 0x1F, (v >> 10) & 0x1F
            out += bytes((r * 255 // 31, g * 255 // 31, b * 255 // 31))
        else:           # 4444
            r, g, b = v & 0xF, (v >> 4) & 0xF, (v >> 8) & 0xF
            out += bytes((r * 17, g * 17, b * 17))
    return bytes(out)


def write_png(path: Path, w: int, h: int, rgb: bytes) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))


class Session:
    def __init__(self, sock: socket.socket, shot_dir: Path):
        self.sock = sock
        self.shot_dir = shot_dir
        self.buf = b""
        self.pings = 0
        # Pending binary payload after a "bulk" or "frame" header.
        self.payload_kind = ""
        self.payload_meta: tuple = ()
        self.payload_left = self.payload_total = 0
        self.payload = bytearray()
        self.payload_start = 0.0

    def send(self, line: str) -> None:
        self.sock.sendall((line + "\n").encode())

    def expect_payload(self, kind: str, size: int, meta: tuple = ()) -> None:
        self.payload_kind, self.payload_meta = kind, meta
        self.payload_left = self.payload_total = size
        self.payload = bytearray()
        self.payload_start = time.monotonic()

    def feed(self, data: bytes) -> None:
        self.buf += data
        while self.buf:
            if self.payload_left:
                take = min(self.payload_left, len(self.buf))
                if self.payload_kind == "frame":
                    self.payload += self.buf[:take]
                self.buf = self.buf[take:]
                self.payload_left -= take
                if not self.payload_left:
                    self.finish_payload()
                continue
            nl = self.buf.find(b"\n")
            if nl < 0:
                return
            line, self.buf = self.buf[:nl].decode(errors="replace"), self.buf[nl + 1:]
            self.handle(line)

    def handle(self, line: str) -> None:
        parts = line.split()
        if not parts:
            return
        cmd = parts[0]
        if cmd == "ping" and len(parts) == 3:
            self.send(f"pong {parts[1]} {parts[2]}")
            self.pings += 1
            if self.pings % 20 == 0:
                print(f"[m0] {self.pings} ping cevaplandi", flush=True)
        elif cmd == "btn" and len(parts) == 3:
            self.send(f"ack {parts[1]} {parts[2]}")
            print(f"[m0] tus: {parts[1]}", flush=True)
        elif cmd == "bulk" and len(parts) == 3:
            self.expect_payload("bulk", int(parts[2]), (parts[1],))
        elif cmd == "frame" and len(parts) == 5:
            w, h, fmt, size = map(int, parts[1:])
            self.expect_payload("frame", size, (w, h, fmt))
        elif cmd == "hello":
            print(f"[m0] PSP: {line}", flush=True)
        elif cmd == "report":
            print(f"[m0] OZ-TEST RAPORU: {' '.join(parts[1:])}", flush=True)
        else:
            print(f"[m0] bilinmeyen: {line!r}", flush=True)

    def finish_payload(self) -> None:
        ms = max((time.monotonic() - self.payload_start) * 1000, 0.001)
        if self.payload_kind == "frame":
            w, h, fmt = self.payload_meta
            self.shot_dir.mkdir(parents=True, exist_ok=True)
            path = self.shot_dir / f"psp-{time.strftime('%Y%m%d-%H%M%S')}.png"
            write_png(path, w, h, to_rgb(bytes(self.payload), fmt))
            print(f"[m0] ekran goruntusu: {path} ({ms:.0f} ms)", flush=True)
            return
        (mode,) = self.payload_meta
        kbs = self.payload_total / 1024 / (ms / 1000)
        print(f"[m0] {mode}: {self.payload_total} B, {ms:.0f} ms, {kbs:.0f} KB/s", flush=True)
        self.send(f"rate {mode} {self.payload_total} B {ms:.0f} ms {kbs:.0f} KB/s")

    def request_shot(self) -> None:
        self.send("shot")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, help="default: 10004 (USB), 10200 (--listen)")
    ap.add_argument("--listen", action="store_true", help="TCP mode: wait for the PSP/PPSSPP to connect")
    ap.add_argument("--shots", type=Path, default=Path("shots"), help="screenshot folder (default: ./shots)")
    ap.add_argument("--shot-after", type=float, metavar="SEC",
                    help="request one screenshot SEC seconds after the PSP connects")
    args = ap.parse_args()

    if args.listen:
        incoming = listen(args.host, args.port or 10200)
        next_sock = lambda: next(incoming)
    else:
        next_sock = lambda: connect(args.host, args.port or 10004)

    inputs = [sys.stdin]
    while True:
        session = Session(next_sock(), args.shots)
        shot_at = time.monotonic() + args.shot_after if args.shot_after is not None else None
        try:
            while True:
                timeout = max(shot_at - time.monotonic(), 0) if shot_at else None
                ready, _, _ = select.select([session.sock] + inputs, [], [], timeout)
                if shot_at and time.monotonic() >= shot_at:
                    session.request_shot()
                    shot_at = None
                if session.sock in ready:
                    data = session.sock.recv(65536)
                    if not data:
                        print("[m0] baglanti kapandi, yeniden deneniyor", flush=True)
                        break
                    session.feed(data)
                if sys.stdin in ready:
                    text = sys.stdin.readline()
                    if not text:
                        inputs = []  # stdin closed (e.g. run in the background); keep serving
                        continue
                    if text.strip() == "/shot":
                        session.request_shot()
                    else:
                        session.send("msg " + text.strip()[:60])
        except (ConnectionError, OSError) as e:
            print(f"[m0] baglanti hatasi: {e}", flush=True)
        finally:
            session.sock.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
