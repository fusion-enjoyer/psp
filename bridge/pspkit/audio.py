"""Output volume and microphone through PipeWire (wpctl), PulseAudio as fallback."""
from __future__ import annotations

import re
import shutil
import subprocess

SINK, SOURCE = "@DEFAULT_AUDIO_SINK@", "@DEFAULT_AUDIO_SOURCE@"
_PA = {SINK: "@DEFAULT_SINK@", SOURCE: "@DEFAULT_SOURCE@"}


def _run(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=3, check=True).stdout
    except FileNotFoundError:
        raise RuntimeError(f"{args[0]} bulunamadı")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"{args[0]}: {(e.stderr or e.stdout).strip()[:80]}")


def _wpctl() -> bool:
    return shutil.which("wpctl") is not None


def change_volume(step: int, node: str = SINK) -> None:
    """step in percent, positive or negative; capped at 100%."""
    if _wpctl():
        _run(["wpctl", "set-volume", "-l", "1.0", node, f"{abs(step)}%{'+' if step > 0 else '-'}"])
    else:
        kind = "sink" if node == SINK else "source"
        _run(["pactl", f"set-{kind}-volume", _PA[node], f"{step:+d}%"])


def set_mute(node: str, mode: str) -> None:
    """mode: 'toggle', 'mute' or 'unmute'."""
    if _wpctl():
        _run(["wpctl", "set-mute", node, {"toggle": "toggle", "mute": "1", "unmute": "0"}[mode]])
    else:
        kind = "sink" if node == SINK else "source"
        _run(["pactl", f"set-{kind}-mute", _PA[node], {"toggle": "toggle", "mute": "1", "unmute": "0"}[mode]])


def state(node: str = SINK) -> tuple[int, bool]:
    """(volume percent, muted)."""
    if _wpctl():
        out = _run(["wpctl", "get-volume", node])
        m = re.search(r"Volume:\s*([\d.]+)", out)
        return (round(float(m.group(1)) * 100) if m else 0, "[MUTED]" in out)
    kind = "sink" if node == SINK else "source"
    vol = _run(["pactl", f"get-{kind}-volume", _PA[node]])
    mute = _run(["pactl", f"get-{kind}-mute", _PA[node]])
    m = re.search(r"(\d+)%", vol)
    return (int(m.group(1)) if m else 0, "yes" in mute)
