#!/usr/bin/env python3
"""pspkit M0 PC side: echo server for the USB spike.

Connects to usbhostfs_pc's TCP port for async channel 4 (localhost:10004),
answers pings and button presses, and measures bulk throughput.
Type a line and press Enter to show it on the PSP screen.
"""
import argparse
import select
import socket
import sys
import time


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


class Session:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = b""
        self.bulk_left = 0
        self.bulk_mode = ""
        self.bulk_total = 0
        self.bulk_start = 0.0
        self.pings = 0

    def send(self, line: str) -> None:
        self.sock.sendall((line + "\n").encode())

    def feed(self, data: bytes) -> None:
        self.buf += data
        while self.buf:
            if self.bulk_left:
                take = min(self.bulk_left, len(self.buf))
                self.buf = self.buf[take:]
                self.bulk_left -= take
                if not self.bulk_left:
                    self.finish_bulk()
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
            self.bulk_mode, self.bulk_total = parts[1], int(parts[2])
            self.bulk_left = self.bulk_total
            self.bulk_start = time.monotonic()
        elif cmd == "hello":
            print(f"[m0] PSP: {line}", flush=True)
        else:
            print(f"[m0] bilinmeyen: {line!r}", flush=True)

    def finish_bulk(self) -> None:
        ms = max((time.monotonic() - self.bulk_start) * 1000, 0.001)
        kbs = self.bulk_total / 1024 / (ms / 1000)
        print(f"[m0] {self.bulk_mode}: {self.bulk_total} B, {ms:.0f} ms, {kbs:.0f} KB/s", flush=True)
        self.send(f"rate {self.bulk_mode} {self.bulk_total} B {ms:.0f} ms {kbs:.0f} KB/s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=10004)
    args = ap.parse_args()

    while True:
        session = Session(connect(args.host, args.port))
        try:
            while True:
                ready, _, _ = select.select([session.sock, sys.stdin], [], [])
                if session.sock in ready:
                    data = session.sock.recv(65536)
                    if not data:
                        print("[m0] baglanti kapandi, yeniden deneniyor", flush=True)
                        break
                    session.feed(data)
                if sys.stdin in ready:
                    text = sys.stdin.readline()
                    if not text:
                        return 0
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
