"""Bridge side of the Deck app: sends tiles, runs actions, pushes live state."""
from __future__ import annotations

import asyncio
import logging

from ..text import to_psp
from .config import BUTTONS, LAYERS

log = logging.getLogger("pspkit.deck")

STATE_PERIOD_S = 1.0
OK, ERR, INFO = "3ddc84", "f04e4e", "8a909c"
ANALOG_LABELS = {"none": "-", "volume": "Ses", "scroll": "Kaydır"}


class DeckApp:
    def __init__(self, session, bridge):
        self.session = session
        self.bridge = bridge
        self.sent: dict[tuple[str, str], str] = {}
        self._poll_task: asyncio.Task | None = None
        self._refresh_lock = asyncio.Lock()
        self._analog_busy = False

    # ---- lifecycle ----

    async def start(self, hello_args: list[str]) -> None:
        self.push_all()
        if self.bridge.config_error:
            self.toast(f"Ayar hatası: {self.bridge.config_error}", error=True)
        self._poll_task = asyncio.create_task(self._poll_loop())

    def close(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()

    # ---- output ----

    @staticmethod
    def tile_line(layer: str, button: str, tile: dict, active: bool = False, label: str | None = None) -> str:
        text = to_psp(label if label is not None else tile["label"], 40) or "-"
        return f"tile {layer} {button} {tile['color'].lstrip('#')} {1 if active else 0} {text}"

    def toast(self, text: str, error: bool = False, color: str | None = None) -> None:
        text = " ".join(text.replace("|", " ").split())  # toasts are a single line
        self.session.send(f"toast {color or (ERR if error else OK)} {to_psp(text, 58)}")

    def push_all(self) -> None:
        cfg = self.bridge.config
        if cfg is None:
            return
        self.session.send("clear")
        self.session.send(f"title {to_psp(cfg['title'], 24)}")
        self.sent = {}
        for layer in LAYERS:
            self.session.send(f"analog {layer} {to_psp(ANALOG_LABELS[cfg['analog'][layer]], 20)}")
            for button, tile in cfg["layers"][layer].items():
                if tile["action"] == "none" and not tile["label"]:
                    continue
                line = self.tile_line(layer, button, tile)
                self.sent[(layer, button)] = line
                self.session.send(line)
        asyncio.get_running_loop().create_task(self.refresh_states())

    # ---- input ----

    async def on_line(self, cmd: str, args: list[str]) -> None:
        if cmd == "press" and len(args) >= 2:
            if len(args) >= 3:
                self.session.send(f"ack {args[2]}")  # before running, so latency = link only
            await self.press(args[0], args[1])
        elif cmd == "analog" and len(args) == 3:
            await self.analog(args[0], int(args[1]), int(args[2]))

    async def press(self, layer: str, button: str) -> None:
        cfg = self.bridge.config
        tile = cfg["layers"].get(layer, {}).get(button) if cfg else None
        if tile is None or tile["action"] == "none":
            return
        log.info("basıldı: %s/%s -> %s", layer, button, tile["action"])
        try:
            message = await self.bridge.blocking(self.bridge.runner.run, tile)
        except Exception as e:  # any action failure is shown on the PSP
            log.warning("aksiyon hatası %s/%s: %s", layer, button, e)
            self.toast(f"{tile['label'].replace('|', ' ') or tile['action']}: {e}", error=True)
            return
        if message:
            self.toast(message)
        if self.bridge.runner.state_key(tile):
            await asyncio.sleep(0.15)  # let the desktop settle, then show the new state
            await self.refresh_states()

    async def analog(self, layer: str, x: int, y: int) -> None:
        cfg = self.bridge.config
        mode = cfg["analog"].get(layer, "none") if cfg else "none"
        if mode == "none" or self._analog_busy:
            return  # drop samples while the previous one still runs
        self._analog_busy = True
        try:
            await self.bridge.blocking(self.bridge.runner.analog, mode, x, y)
        except Exception as e:
            self.toast(f"Analog: {e}", error=True)
        finally:
            self._analog_busy = False

    # ---- live state ----

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(STATE_PERIOD_S)
            await self.refresh_states()

    async def refresh_states(self) -> None:
        cfg = self.bridge.config
        if cfg is None or self._refresh_lock.locked():
            return
        runner = self.bridge.runner
        async with self._refresh_lock:
            tiles = [(layer, button, tile) for layer in LAYERS
                     for button, tile in cfg["layers"][layer].items() if runner.state_key(tile)]
            raw: dict[tuple, object] = {}
            for key in {runner.state_key(t) for _, _, t in tiles}:
                try:
                    raw[key] = await self.bridge.blocking(runner.read_state, key)
                except Exception as e:  # e.g. OBS closed: show the plain tile
                    log.debug("durum okunamadı %s: %s", key, e)
                    raw[key] = None
            if self.bridge.config is not cfg:
                return  # config changed meanwhile; push_all started over
            for layer, button, tile in tiles:
                active, label = runner.present(tile, raw[runner.state_key(tile)])
                line = self.tile_line(layer, button, tile, active, label)
                if self.sent.get((layer, button)) != line:
                    self.sent[(layer, button)] = line
                    self.session.send(line)

    def simulate(self, layer: str, button: str) -> None:
        """Asks the PSP to act as if the button was pressed (for testing)."""
        if layer not in LAYERS or button not in BUTTONS:
            raise ValueError("geçersiz katman/tuş")
        self.session.send(f"sim {layer} {button}")
