"""deck.yaml: the Deck layout. The bridge and the desktop app both use this.

A tile is a mapping with label, color, action and the action's own params
flattened next to them, so the file stays easy to edit by hand:

    layers:
      normal:
        up: {label: "Ses +", color: "#3d8bfd", action: volume, op: up, step: 5}
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

LAYERS = ("normal", "l", "r", "lr")
LAYER_TITLES = {"normal": "Normal", "l": "L", "r": "R", "lr": "L+R"}
BUTTONS = ("up", "down", "left", "right", "triangle", "circle", "cross", "square", "start", "select")
ANALOG_MODES = ("none", "volume", "scroll")
TILE_KEYS = ("label", "color", "action")
COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


class ConfigError(ValueError):
    pass


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "pspkit" / "deck.yaml"


DEFAULT_YAML = """\
# pspkit Deck ayarları. Masaüstü uygulaması (desktop/pspkit_deck_gui.py) bu
# dosyayı yazar; elle de düzenleyebilirsin, köprü kaydettiğin an PSP'yi günceller.
#
# Katmanlar: normal, l (L basılı), r (R basılı), lr (ikisi birden)
# Tuşlar: up down left right triangle circle cross square start select
# Aksiyonlar ve parametreleri: python3 -m pspkit actions
version: 1
title: pspkit Deck

# Analog çubuk her katmanda: none, volume (ses), scroll (kaydırma)
analog: {normal: volume, l: none, r: scroll, lr: none}

obs: {host: 127.0.0.1, port: 4455, password: ""}

layers:
  normal:
    up:       {label: "Ses +", color: "#3d8bfd", action: volume, op: up, step: 5}
    down:     {label: "Ses -", color: "#3d8bfd", action: volume, op: down, step: 5}
    left:     {label: "Önceki", color: "#a371f7", action: media, op: previous}
    right:    {label: "Sonraki", color: "#a371f7", action: media, op: next}
    circle:   {label: "Oynat", color: "#a371f7", action: media, op: play_pause}
    triangle: {label: "Mikrofon", color: "#f04e4e", action: mic, op: toggle}
    cross:    {label: "Terminal", color: "#3ddc84", action: key, keys: "ctrl+alt+t"}
    square:   {label: "pspkit|GitHub", color: "#f5a524", action: open, target: "https://github.com/fusion-enjoyer/psp"}
    select:   {label: "Sessiz", color: "#6b7280", action: volume, op: mute}
    start:    {label: "Ekran|Resmi", color: "#14b8a6", action: key, keys: "print"}
  l:
    up:       {label: "Sahne|Kamera", color: "#8b5cf6", action: obs, op: scene, scene: "Kamera"}
    right:    {label: "Sahne|Ekran", color: "#8b5cf6", action: obs, op: scene, scene: "Ekran"}
    down:     {label: "Sahne|Ara", color: "#8b5cf6", action: obs, op: scene, scene: "Ara"}
    triangle: {label: "KAYIT", color: "#f04e4e", action: obs, op: record}
    circle:   {label: "YAYIN", color: "#f04e4e", action: obs, op: stream}
    square:   {label: "OBS Mic", color: "#f5a524", action: obs, op: mute_input, input: "Mic/Aux"}
  r:
    up:       {label: "Geri Al", color: "#3d8bfd", action: key, keys: "ctrl+z"}
    down:     {label: "Yinele", color: "#3d8bfd", action: key, keys: "ctrl+shift+z"}
    left:     {label: "Kopyala", color: "#14b8a6", action: key, keys: "ctrl+c"}
    right:    {label: "Yapıştır", color: "#14b8a6", action: key, keys: "ctrl+v"}
    triangle: {label: "Pencere|ler", color: "#a371f7", action: key, keys: "super"}
    circle:   {label: "Sekme|Kapat", color: "#f04e4e", action: key, keys: "ctrl+w"}
    cross:    {label: "Yeni|Sekme", color: "#3ddc84", action: key, keys: "ctrl+t"}
    square:   {label: "Tümünü|Seç", color: "#6b7280", action: key, keys: "ctrl+a"}
    start:    {label: "Kaydet", color: "#3ddc84", action: key, keys: "ctrl+s"}
    select:   {label: "Bul", color: "#f5a524", action: key, keys: "ctrl+f"}
  lr:
    triangle: {label: "Ekranı|Kilitle", color: "#f04e4e", action: command, cmd: "loginctl lock-session"}
    circle:   {label: "Dosyalar", color: "#f5a524", action: open, target: "~"}
    square:   {label: "Sistem|İzleyici", color: "#3d8bfd", action: command, cmd: "gnome-system-monitor"}
"""


def normalize(data: dict) -> dict:
    """Validates a parsed config and fills defaults. Raises ConfigError."""
    from . import actions  # late import: actions imports this module's constants

    if not isinstance(data, dict):
        raise ConfigError("dosya bir YAML sözlüğü olmalı")
    out = {
        "version": 1,
        "title": str(data.get("title") or "pspkit Deck"),
        "analog": {},
        "obs": {"host": "127.0.0.1", "port": 4455, "password": ""},
        "layers": {layer: {} for layer in LAYERS},
    }

    analog = data.get("analog") or {}
    if not isinstance(analog, dict):
        raise ConfigError("analog bir sözlük olmalı")
    for layer in LAYERS:
        mode = analog.get(layer, "none") or "none"
        if mode not in ANALOG_MODES:
            raise ConfigError(f"analog.{layer}: '{mode}' geçersiz ({', '.join(ANALOG_MODES)})")
        out["analog"][layer] = mode

    obs = data.get("obs") or {}
    if not isinstance(obs, dict):
        raise ConfigError("obs bir sözlük olmalı")
    out["obs"].update({k: obs[k] for k in ("host", "port", "password") if k in obs})
    try:
        out["obs"]["port"] = int(out["obs"]["port"])
    except (TypeError, ValueError):
        raise ConfigError("obs.port bir sayı olmalı")

    layers = data.get("layers") or {}
    if not isinstance(layers, dict):
        raise ConfigError("layers bir sözlük olmalı")
    for layer, tiles in layers.items():
        if layer not in LAYERS:
            raise ConfigError(f"bilinmeyen katman '{layer}' ({', '.join(LAYERS)})")
        if tiles is None:
            continue
        if not isinstance(tiles, dict):
            raise ConfigError(f"layers.{layer} bir sözlük olmalı")
        for button, tile in tiles.items():
            where = f"layers.{layer}.{button}"
            if button not in BUTTONS:
                raise ConfigError(f"{where}: bilinmeyen tuş ({', '.join(BUTTONS)})")
            if tile is None:
                continue
            out["layers"][layer][button] = normalize_tile(tile, where, actions)
    return out


def normalize_tile(tile: dict, where: str, actions) -> dict:
    if not isinstance(tile, dict):
        raise ConfigError(f"{where}: bir sözlük olmalı")
    action = tile.get("action", "none")
    spec = actions.CATALOG.get(action)
    if spec is None:
        raise ConfigError(f"{where}: bilinmeyen aksiyon '{action}'")
    color = str(tile.get("color") or "#6b7280")
    if not COLOR_RE.match(color):
        raise ConfigError(f"{where}: renk '#rrggbb' biçiminde olmalı")
    out = {"label": str(tile.get("label") or ""), "color": "#" + color.lstrip("#").lower(), "action": action}
    for param in spec.params:
        value = tile.get(param.name, param.default)
        out[param.name] = param.coerce(value, where)
    if action == "key":
        try:
            actions.validate_keys(out["keys"])
        except ValueError as e:
            raise ConfigError(f"{where}.keys: {e}")
    return out


def load(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"{path} bulunamadı")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" satır {mark.line + 1}" if mark else ""
        raise ConfigError(f"YAML hatası{where}: {getattr(e, 'problem', None) or e}")
    return normalize(data or {})


def ensure(path: Path) -> None:
    """Writes the default config when there is none yet."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_YAML, encoding="utf-8")


HEADER = """\
# pspkit Deck ayarları. Masaüstü uygulaması bu dosyayı yazar; elle de
# düzenleyebilirsin, köprü kaydettiğin an PSP'yi günceller.
# Aksiyonlar ve parametreleri: python3 -m pspkit actions
"""


def save(path: Path, cfg: dict) -> None:
    """Validates and writes atomically, so the bridge never reads half a file."""
    cfg = normalize(cfg)
    layers = {layer: tiles for layer, tiles in cfg["layers"].items() if tiles}
    body = yaml.safe_dump({**cfg, "layers": layers}, allow_unicode=True, sort_keys=False, width=100)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(HEADER + body, encoding="utf-8")
    os.replace(tmp, path)
