"""Deck actions: what a tile does on the PC, and the live state it shows.

CATALOG drives validation (config.py), the desktop editor's forms and
`python3 -m pspkit actions`. Runner executes actions; it is called from
worker threads, never from the asyncio loop.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any

from .. import audio, mpris
from ..obs import OBSClient
from ..uinput import VirtualInput, parse_combo


@dataclass
class Param:
    name: str
    kind: str  # "str", "int" or "choice"
    default: Any
    title: str
    choices: tuple = ()
    help: str = ""

    def coerce(self, value: Any, where: str) -> Any:
        from .config import ConfigError

        if value is None:
            value = self.default
        if self.kind == "int":
            try:
                return int(value)
            except (TypeError, ValueError):
                raise ConfigError(f"{where}.{self.name}: sayı olmalı")
        if self.kind == "choice":
            if value not in self.choices:
                raise ConfigError(f"{where}.{self.name}: '{value}' geçersiz ({', '.join(self.choices)})")
            return value
        return str(value)


@dataclass
class ActionSpec:
    id: str
    title: str
    help: str
    params: list[Param] = field(default_factory=list)


CATALOG: dict[str, ActionSpec] = {spec.id: spec for spec in [
    ActionSpec("none", "Boş", "Hiçbir şey yapmaz."),
    ActionSpec("key", "Klavye kısayolu", "Tuş kombinasyonu gönderir (X11 ve Wayland).", [
        Param("keys", "str", "ctrl+c", "Tuşlar", help="örnek: ctrl+shift+t, super, f5, print, playpause"),
    ]),
    ActionSpec("command", "Komut çalıştır", "Kabukta bir komut çalıştırır.", [
        Param("cmd", "str", "", "Komut", help="örnek: gnome-terminal, ~/bin/deploy.sh"),
    ]),
    ActionSpec("open", "Aç (URL / dosya / klasör)", "Varsayılan uygulamayla açar (xdg-open).", [
        Param("target", "str", "https://", "Hedef", help="URL, dosya ya da klasör yolu"),
    ]),
    ActionSpec("media", "Medya", "Çalan oynatıcıyı kontrol eder (MPRIS). Oynat karosu çalan parçayı gösterir.", [
        Param("op", "choice", "play_pause", "İşlem", ("play_pause", "next", "previous", "stop")),
    ]),
    ActionSpec("volume", "Ses", "Hoparlör sesi. Karo ses seviyesini ya da sessiz durumunu gösterir.", [
        Param("op", "choice", "up", "İşlem", ("up", "down", "mute")),
        Param("step", "int", 5, "Adım (%)"),
    ]),
    ActionSpec("mic", "Mikrofon", "Varsayılan mikrofonu kapatır/açar. Kapalıyken karo yanar.", [
        Param("op", "choice", "toggle", "İşlem", ("toggle", "mute", "unmute")),
    ]),
    ActionSpec("obs", "OBS", "OBS Studio (websocket). Aktif sahne, kayıt ve yayın karoda görünür.", [
        Param("op", "choice", "scene", "İşlem", ("scene", "record", "stream", "mute_input")),
        Param("scene", "str", "", "Sahne adı", help="op: scene için"),
        Param("input", "str", "", "Kaynak adı", help="op: mute_input için, örnek: Mic/Aux"),
    ]),
]}

ACTION_TITLES = {k: v.title for k, v in CATALOG.items()}


def validate_keys(keys: str) -> None:
    parse_combo(keys)


class Runner:
    def __init__(self) -> None:
        self.input = VirtualInput()
        self.obs = OBSClient()

    def configure(self, cfg: dict) -> None:
        obs = cfg["obs"]
        self.obs.configure(obs["host"], obs["port"], obs["password"])

    def close(self) -> None:
        self.input.close()
        self.obs.close()

    # ---- running ----

    def run(self, tile: dict) -> str | None:
        """Runs a tile's action. Returns an optional message; raises on failure."""
        action = tile["action"]
        if action == "none":
            return None
        if action == "key":
            self.input.combo(tile["keys"])
        elif action == "command":
            if not tile["cmd"].strip():
                raise RuntimeError("komut boş")
            _spawn(["sh", "-c", tile["cmd"]])
        elif action == "open":
            target = os.path.expanduser(tile["target"].strip())
            if not target:
                raise RuntimeError("hedef boş")
            _spawn(["xdg-open", target])
        elif action == "media":
            mpris.control(tile["op"])
        elif action == "volume":
            if tile["op"] == "mute":
                audio.set_mute(audio.SINK, "toggle")
            else:
                audio.change_volume(tile["step"] if tile["op"] == "up" else -tile["step"])
        elif action == "mic":
            audio.set_mute(audio.SOURCE, tile["op"])
        elif action == "obs":
            return self._obs(tile)
        return None

    def _obs(self, tile: dict) -> str | None:
        op = tile["op"]
        if op == "scene":
            if not tile["scene"]:
                raise RuntimeError("sahne adı boş")
            self.obs.request("SetCurrentProgramScene", {"sceneName": tile["scene"]})
            return f"Sahne: {tile['scene']}"
        if op == "record":
            active = self.obs.request("ToggleRecord").get("outputActive")
            return "Kayıt başladı" if active else "Kayıt durdu"
        if op == "stream":
            active = self.obs.request("ToggleStream").get("outputActive")
            return "Yayın başladı" if active else "Yayın durdu"
        if not tile["input"]:
            raise RuntimeError("kaynak adı boş")
        self.obs.request("ToggleInputMute", {"inputName": tile["input"]})
        return None

    def analog(self, mode: str, x: int, y: int) -> None:
        """x, y in -127..127 (y down). Called about 10 times a second while held."""
        if mode == "volume":
            step = round(-y / 127 * 4)
            if step:
                audio.change_volume(step)
        elif mode == "scroll":
            v, h = round(-y / 127 * 3), round(x / 127 * 3)
            if v or h:
                self.input.scroll(v, h)

    # ---- live state ----

    @staticmethod
    def state_key(tile: dict) -> tuple | None:
        """Identity of the state a tile shows; None when it shows none."""
        action, op = tile["action"], tile.get("op")
        if action == "media" and op == "play_pause":
            return ("media",)
        if action == "volume":
            return ("volume",)
        if action == "mic":
            return ("mic",)
        if action == "obs":
            return ("obs", op, tile.get("scene") if op == "scene" else tile.get("input") if op == "mute_input" else "")
        return None

    def read_state(self, key: tuple) -> Any:
        """Fetches the raw state for a state_key (may raise)."""
        kind = key[0]
        if kind == "media":
            return mpris.now_playing()
        if kind == "volume":
            return audio.state(audio.SINK)
        if kind == "mic":
            return audio.state(audio.SOURCE)
        op, name = key[1], key[2]
        if op == "scene":
            data = self.obs.request("GetCurrentProgramScene")
            return (data.get("currentProgramSceneName") or data.get("sceneName")) == name
        if op == "record":
            return bool(self.obs.request("GetRecordStatus").get("outputActive"))
        if op == "stream":
            return bool(self.obs.request("GetStreamStatus").get("outputActive"))
        return bool(self.obs.request("GetInputMute", {"inputName": name}).get("inputMuted"))

    @staticmethod
    def present(tile: dict, raw: Any) -> tuple[bool, str]:
        """Turns raw state into (active, label) for the PSP tile."""
        label, action, op = tile["label"], tile["action"], tile.get("op")
        if raw is None:
            return False, label
        if action == "media":
            title = raw["title"] or label
            return raw["status"] == "Playing", title if raw["status"] == "Playing" else f"II {title}"
        if action == "volume":
            vol, muted = raw
            if op == "mute":
                return muted, f"{label}|ACIK" if not muted else f"{label}|KAPALI"
            return False, f"{label}|{vol}%"
        if action == "mic":
            _, muted = raw
            return muted, f"{label}|KAPALI" if muted else label
        if action == "obs":
            if op == "record" and raw:
                return True, f"{label}|REC"
            if op == "stream" and raw:
                return True, f"{label}|CANLI"
            return bool(raw), label
        return False, label


def _spawn(args: list[str]) -> None:
    if not shutil.which(args[0]):
        raise RuntimeError(f"{args[0]} bulunamadı")
    proc = subprocess.Popen(args, start_new_session=True, cwd=os.path.expanduser("~"),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Reap it in the background so a long-running bridge leaves no zombies.
    threading.Thread(target=proc.wait, daemon=True).start()
