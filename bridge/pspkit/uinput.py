"""Virtual keyboard + scroll wheel through /dev/uinput (stdlib only).

Works on X11 and Wayland alike, unlike xdotool. Key names follow physical US
key positions ("ctrl+shift+t"), which is what shortcuts refer to anyway.
"""
from __future__ import annotations

import fcntl
import os
import struct
import threading
import time

EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
SYN_REPORT = 0
REL_HWHEEL, REL_WHEEL = 0x06, 0x08

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_RELBIT = 0x40045566
UI_DEV_SETUP = 0x405C5503
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
BUS_VIRTUAL = 0x06

KEYS: dict[str, int] = {
    "esc": 1, "minus": 12, "equal": 13, "backspace": 14, "tab": 15,
    "leftbrace": 26, "rightbrace": 27, "enter": 28, "semicolon": 39,
    "apostrophe": 40, "grave": 41, "backslash": 43, "comma": 51, "dot": 52,
    "slash": 53, "space": 57, "capslock": 58, "numlock": 69, "scrolllock": 70,
    "print": 99, "sysrq": 99, "home": 102, "up": 103, "pageup": 104, "left": 105,
    "right": 106, "end": 107, "down": 108, "pagedown": 109, "insert": 110,
    "delete": 111, "mute": 113, "volumedown": 114, "volumeup": 115, "pause": 119,
    "menu": 127, "nextsong": 163, "playpause": 164, "previoussong": 165,
    "stopcd": 166, "micmute": 248,
    # modifiers
    "ctrl": 29, "shift": 42, "alt": 56, "super": 125,
    "rightctrl": 97, "rightshift": 54, "altgr": 100, "rightsuper": 126,
}
for _i, _c in enumerate("1234567890"):
    KEYS[_c] = 2 + _i
for _row, _start in (("qwertyuiop", 16), ("asdfghjkl", 30), ("zxcvbnm", 44)):
    for _i, _c in enumerate(_row):
        KEYS[_c] = _start + _i
for _i in range(10):
    KEYS[f"f{_i + 1}"] = 59 + _i
KEYS.update({"f11": 87, "f12": 88})
for _i in range(12):
    KEYS[f"f{_i + 13}"] = 183 + _i

ALIASES = {"control": "ctrl", "win": "super", "meta": "super", "cmd": "super",
           "return": "enter", "del": "delete", "escape": "esc", "pgup": "pageup",
           "pgdn": "pagedown", "printscreen": "print", "prtsc": "print", "ins": "insert",
           "-": "minus", "=": "equal", ",": "comma", ".": "dot", "/": "slash",
           ";": "semicolon", "'": "apostrophe", "`": "grave", "\\": "backslash",
           "[": "leftbrace", "]": "rightbrace", "plus": "equal"}
MODIFIERS = {"ctrl", "shift", "alt", "super", "rightctrl", "rightshift", "altgr", "rightsuper"}


def parse_combo(combo: str) -> list[int]:
    """'ctrl+shift+t' -> key codes, modifiers first. Raises ValueError."""
    names = [p.strip().lower() for p in combo.replace(" ", "").split("+") if p.strip()]
    if not names:
        raise ValueError("boş tuş kombinasyonu")
    codes = []
    for name in names:
        name = ALIASES.get(name, name)
        if name not in KEYS:
            raise ValueError(f"bilinmeyen tuş '{name}'")
        codes.append(KEYS[name])
    mods = [c for c, n in zip(codes, names) if ALIASES.get(n, n) in MODIFIERS]
    rest = [c for c in codes if c not in mods]
    return mods + rest


class VirtualInput:
    """Lazily created uinput device shared by all actions."""

    def __init__(self, path: str = "/dev/uinput"):
        self.path = path
        self.fd: int | None = None
        self.lock = threading.Lock()

    def _open(self) -> int:
        if self.fd is not None:
            return self.fd
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        except PermissionError:
            raise RuntimeError("/dev/uinput izni yok (python3 -m pspkit doctor)")
        except FileNotFoundError:
            raise RuntimeError("/dev/uinput yok (uinput modülü yüklü mü?)")
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_SYN)
        for code in set(KEYS.values()):
            fcntl.ioctl(fd, UI_SET_KEYBIT, code)
        fcntl.ioctl(fd, UI_SET_RELBIT, REL_WHEEL)
        fcntl.ioctl(fd, UI_SET_RELBIT, REL_HWHEEL)
        setup = struct.pack("HHHH80sI", BUS_VIRTUAL, 0x1209, 0x5053, 1, b"pspkit Deck", 0)
        fcntl.ioctl(fd, UI_DEV_SETUP, setup)
        fcntl.ioctl(fd, UI_DEV_CREATE)
        time.sleep(0.3)  # give the compositor a moment to pick the new device up
        self.fd = fd
        return fd

    def _emit(self, fd: int, etype: int, code: int, value: int) -> None:
        now = time.time()
        os.write(fd, struct.pack("llHHi", int(now), int(now % 1 * 1e6), etype, code, value))

    def _sync(self, fd: int) -> None:
        self._emit(fd, EV_SYN, SYN_REPORT, 0)

    def combo(self, combo: str) -> None:
        codes = parse_combo(combo)
        with self.lock:
            fd = self._open()
            for code in codes:
                self._emit(fd, EV_KEY, code, 1)
                self._sync(fd)
            time.sleep(0.02)
            for code in reversed(codes):
                self._emit(fd, EV_KEY, code, 0)
                self._sync(fd)

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        with self.lock:
            fd = self._open()
            if vertical:
                self._emit(fd, EV_REL, REL_WHEEL, vertical)
            if horizontal:
                self._emit(fd, EV_REL, REL_HWHEEL, horizontal)
            self._sync(fd)

    def close(self) -> None:
        with self.lock:
            if self.fd is not None:
                try:
                    fcntl.ioctl(self.fd, UI_DEV_DESTROY)
                finally:
                    os.close(self.fd)
                    self.fd = None
