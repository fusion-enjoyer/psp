"""Local control socket for the desktop app and the CLI.

JSON lines over a unix socket in $XDG_RUNTIME_DIR/pspkit (user-only perms):
  {"cmd": "status"}                        bridge + connected PSP apps
  {"cmd": "run", "tile": {...}}            run an action once ("Dene" button)
  {"cmd": "sim", "layer": .., "button": ..} make the PSP act as if pressed
  {"cmd": "shot"}                          screenshot of the PSP screen
  {"cmd": "reload"}                        re-read deck.yaml now
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from pathlib import Path

log = logging.getLogger("pspkit.control")


def default_path() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/pspkit-{os.getuid()}"
    return Path(base) / "pspkit" / "bridge.sock"


async def start_server(bridge, path: Path | None = None):
    path = path or default_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        if _alive(path):
            raise RuntimeError(f"başka bir köprü zaten çalışıyor ({path})")
        path.unlink()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while line := await reader.readline():
                try:
                    reply = await _dispatch(bridge, json.loads(line))
                except Exception as e:
                    reply = {"ok": False, "error": str(e)}
                writer.write((json.dumps(reply) + "\n").encode())
                await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    server = await asyncio.start_unix_server(handle, str(path))
    os.chmod(path, 0o600)
    log.info("kontrol soketi: %s", path)
    return server


def _alive(path: Path) -> bool:
    try:
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(0.5)
            s.connect(str(path))
        return True
    except OSError:
        return False


async def _dispatch(bridge, req: dict) -> dict:
    from .deck import actions
    from .deck.config import normalize_tile

    cmd = req.get("cmd")
    if cmd == "status":
        return {"ok": True, "config": str(bridge.config_path), "config_error": bridge.config_error,
                "sessions": [s.info() for s in bridge.sessions]}
    if cmd == "run":
        tile = normalize_tile(req.get("tile") or {}, "tile", actions)
        message = await bridge.blocking(bridge.runner.run, tile)
        return {"ok": True, "message": message}
    if cmd == "sim":
        apps = bridge.apps("deck")
        if not apps:
            raise RuntimeError("bağlı Deck yok")
        for app in apps:
            app.simulate(req.get("layer", "normal"), req.get("button", ""))
        return {"ok": True}
    if cmd == "shot":
        return {"ok": True, "path": await bridge.screenshot()}
    if cmd == "reload":
        return {"ok": bridge.reload_config(), "error": bridge.config_error}
    raise ValueError(f"bilinmeyen komut: {cmd}")


def request(req: dict, path: Path | None = None, timeout: float = 10.0) -> dict:
    """Blocking client call. Raises ConnectionError when the bridge is not running."""
    path = path or default_path()
    try:
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(timeout)
            s.connect(str(path))
            s.sendall((json.dumps(req) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except (FileNotFoundError, ConnectionRefusedError) as e:
        raise ConnectionError("köprü çalışmıyor (python3 -m pspkit run)") from e
    return json.loads(buf)
