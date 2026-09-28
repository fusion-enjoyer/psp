"""The bridge daemon: PSP sessions over USB and TCP, config, control socket.

USB: usbhostfs_pc exposes the PSP's async channel 4 as localhost:10004; we
connect to it as a client (and start usbhostfs_pc ourselves when needed).
TCP: PSP apps connect to us on port 10200 (PPSSPP, later Wi-Fi).
Both carry the same line protocol, so a Session does not care which it is.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import frames
from .deck import config as deck_config
from .deck.actions import Runner
from .deck.app import DeckApp

log = logging.getLogger("pspkit")

TCP_PORT = 10200
USB_PORT = 10004  # usbhostfs_pc base port 10000 + channel 4
APPS = {"deck": DeckApp}


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "pspkit"


def shots_dir() -> Path:
    pictures = Path(os.path.expanduser("~/Pictures"))
    return (pictures if pictures.is_dir() else data_dir()) / "pspkit"


def find_usbhostfs_pc() -> str | None:
    return shutil.which("usbhostfs_pc") or next(
        (p for p in (os.path.expanduser("~/pspdev/bin/usbhostfs_pc"),) if os.access(p, os.X_OK)), None)


class Session:
    def __init__(self, bridge: "Bridge", reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 transport: str):
        self.bridge, self.reader, self.writer, self.transport = bridge, reader, writer, transport
        self.app = None
        self.app_name = ""
        self.since = time.time()
        peer = writer.get_extra_info("peername")
        self.peer = f"{peer[0]}:{peer[1]}" if peer else transport

    def send(self, line: str) -> None:
        if not self.writer.is_closing():
            self.writer.write((line + "\n").encode())

    def info(self) -> dict:
        return {"app": self.app_name or None, "transport": self.transport, "peer": self.peer,
                "since": self.since}

    async def run(self) -> None:
        self.bridge.sessions.append(self)
        try:
            while True:
                raw = await self.reader.readline()
                if not raw:
                    break
                parts = raw.decode(errors="replace").rstrip("\r\n").split(" ")
                cmd = parts[0]
                if cmd == "hello" and len(parts) >= 2:
                    await self._hello(parts[1:])
                elif cmd == "ping" and len(parts) == 2:
                    self.send(f"pong {parts[1]}")
                elif cmd == "frame" and len(parts) == 5:
                    data = await self.reader.readexactly(int(parts[4]))
                    self.bridge.frame_received(self, int(parts[1]), int(parts[2]), int(parts[3]), data)
                elif self.app:
                    await self.app.on_line(cmd, parts[1:])
        except (ConnectionError, asyncio.IncompleteReadError, ValueError) as e:
            log.debug("session %s ended: %s", self.peer, e)
        finally:
            if self in self.bridge.sessions:
                self.bridge.sessions.remove(self)
            if self.app:
                self.app.close()
            self.writer.close()
            log.info("PSP ayrıldı (%s, %s)", self.transport, self.app_name or "hello yok")

    async def _hello(self, args: list[str]) -> None:
        name = args[0]
        if self.app:
            self.app.close()
            self.app = None
        cls = APPS.get(name)
        self.app_name = name
        if cls is None:
            log.warning("bilinmeyen PSP uygulaması: %s", name)
            return
        log.info("PSP bağlandı: %s (%s, %s)", " ".join(args), self.transport, self.peer)
        self.app = cls(self, self.bridge)
        await self.app.start(args[1:])


class Bridge:
    def __init__(self, config_path: Path, tcp_port: int = TCP_PORT, usb_port: int = USB_PORT,
                 usb: bool = True, spawn_usbhostfs: bool = True, tcp_host: str = "127.0.0.1"):
        self.config_path = config_path
        self.tcp_host, self.tcp_port, self.usb_port = tcp_host, tcp_port, usb_port
        self.usb, self.spawn_usbhostfs = usb, spawn_usbhostfs
        self.runner = Runner()
        self.executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="pspkit")
        self.sessions: list[Session] = []
        self.config: dict | None = None
        self.config_error: str | None = None
        self._config_stamp: tuple | None = None
        self._shot_waiters: list[asyncio.Future] = []
        self._usbhostfs: subprocess.Popen | None = None
        self._servers: list[asyncio.AbstractServer] = []

    # ---- helpers for apps ----

    async def blocking(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, fn, *args)

    def apps(self, name: str):
        return [s.app for s in self.sessions if s.app and s.app_name == name]

    # ---- config ----

    def _stamp(self) -> tuple | None:
        try:
            st = self.config_path.stat()
            return (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            return None

    def reload_config(self) -> bool:
        self._config_stamp = self._stamp()
        try:
            cfg = deck_config.load(self.config_path)
        except deck_config.ConfigError as e:
            self.config_error = str(e)
            log.error("ayar hatası, önceki ayarlar kullanılıyor: %s", e)
            for app in self.apps("deck"):
                app.toast(f"Ayar hatası: {e}", error=True)
            return False
        self.config, self.config_error = cfg, None
        self.runner.configure(cfg)
        for app in self.apps("deck"):
            app.push_all()
        log.info("ayarlar yüklendi: %s", self.config_path)
        return True

    async def _watch_config(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            if self._stamp() != self._config_stamp:
                self.reload_config()

    # ---- screenshots ----

    def frame_received(self, session: Session, w: int, h: int, fmt: int, data: bytes) -> None:
        path = shots_dir() / f"psp-{time.strftime('%Y%m%d-%H%M%S')}.png"
        frames.save_png(path, w, h, fmt, data)
        log.info("ekran görüntüsü: %s", path)
        waiters, self._shot_waiters = self._shot_waiters, []
        for fut in waiters:
            if not fut.done():
                fut.set_result(str(path))

    async def screenshot(self, timeout: float = 8.0) -> str:
        targets = [s for s in self.sessions if s.app]
        if not targets:
            raise RuntimeError("bağlı PSP uygulaması yok")
        fut = asyncio.get_running_loop().create_future()
        self._shot_waiters.append(fut)
        targets[0].send("shot")
        return await asyncio.wait_for(fut, timeout)

    # ---- transports ----

    async def _on_tcp(self, reader, writer) -> None:
        await Session(self, reader, writer, "tcp").run()

    def _maybe_spawn_usbhostfs(self) -> None:
        if not self.spawn_usbhostfs or (self._usbhostfs and self._usbhostfs.poll() is None):
            return
        exe = find_usbhostfs_pc()
        if not exe:
            return
        # usbhostfs_pc also serves a host0: filesystem to the PSP; give it an
        # empty folder so the PSP cannot browse the user's files.
        root = data_dir() / "host0"
        root.mkdir(parents=True, exist_ok=True)
        logfile = data_dir() / "usbhostfs_pc.log"
        log.info("usbhostfs_pc başlatılıyor (%s)", exe)
        self._usbhostfs = subprocess.Popen([exe, str(root)], stdin=subprocess.DEVNULL,
                                           stdout=open(logfile, "ab"), stderr=subprocess.STDOUT,
                                           start_new_session=True)

    async def _usb_loop(self) -> None:
        while True:
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", self.usb_port)
            except OSError:
                self._maybe_spawn_usbhostfs()
                await asyncio.sleep(2)
                continue
            log.info("usbhostfs_pc kanalına bağlandı (localhost:%d)", self.usb_port)
            await Session(self, reader, writer, "usb").run()
            await asyncio.sleep(1)

    # ---- lifecycle ----

    async def serve(self, control_path: Path | None = None) -> None:
        from . import control

        deck_config.ensure(self.config_path)
        # The control socket first: it tells us clearly if a bridge already runs.
        self._servers.append(await control.start_server(self, control_path))
        try:
            tcp = await asyncio.start_server(self._on_tcp, self.tcp_host, self.tcp_port)
        except OSError as e:
            await self.shutdown()
            raise RuntimeError(f"TCP {self.tcp_host}:{self.tcp_port} açılamadı ({e.strerror}); "
                               "başka bir program bu portu kullanıyor olabilir") from e
        self._servers.append(tcp)
        log.info("TCP dinleniyor: %s:%d (PPSSPP / Wi-Fi)", self.tcp_host, self.tcp_port)
        self.reload_config()
        tasks = [asyncio.create_task(self._watch_config())]
        if self.usb:
            tasks.append(asyncio.create_task(self._usb_loop()))
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
            await self.shutdown()

    async def shutdown(self) -> None:
        for server in self._servers:
            server.close()
        for s in list(self.sessions):
            s.writer.close()
        if self._usbhostfs and self._usbhostfs.poll() is None:
            self._usbhostfs.terminate()
        self.runner.close()
        self.executor.shutdown(wait=False, cancel_futures=True)
