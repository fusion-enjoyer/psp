"""Media players over MPRIS (D-Bus): Spotify, browsers, VLC, mpv, ..."""
from __future__ import annotations

import threading

PREFIX = "org.mpris.MediaPlayer2."
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
OPS = {"play_pause": "PlayPause", "next": "Next", "previous": "Previous", "stop": "Stop"}

_lock = threading.Lock()
_bus = None


def _session_bus():
    global _bus
    if _bus is None:
        try:
            import dbus
        except ImportError:
            raise RuntimeError("python3-dbus kurulu değil")
        _bus = dbus.SessionBus()
    return _bus


def _pick_player(bus):
    """The playing player if any, otherwise the first one."""
    import dbus

    names = sorted(n for n in bus.list_names() if str(n).startswith(PREFIX))
    if not names:
        return None
    for name in names:
        try:
            props = dbus.Interface(bus.get_object(name, "/org/mpris/MediaPlayer2"),
                                   "org.freedesktop.DBus.Properties")
            if props.Get(PLAYER_IFACE, "PlaybackStatus") == "Playing":
                return name
        except dbus.DBusException:
            continue
    return names[0]


def control(op: str) -> None:
    import dbus

    with _lock:
        bus = _session_bus()
        name = _pick_player(bus)
        if name is None:
            raise RuntimeError("açık medya oynatıcı yok")
        player = dbus.Interface(bus.get_object(name, "/org/mpris/MediaPlayer2"), PLAYER_IFACE)
        getattr(player, OPS[op])()


def now_playing() -> dict | None:
    """{'status': 'Playing'|'Paused'|..., 'title': str, 'artist': str} or None."""
    import dbus

    with _lock:
        bus = _session_bus()
        name = _pick_player(bus)
        if name is None:
            return None
        props = dbus.Interface(bus.get_object(name, "/org/mpris/MediaPlayer2"),
                               "org.freedesktop.DBus.Properties")
        status = str(props.Get(PLAYER_IFACE, "PlaybackStatus"))
        meta = props.Get(PLAYER_IFACE, "Metadata")
        artist = meta.get("xesam:artist") or []
        return {"status": status, "title": str(meta.get("xesam:title", "")),
                "artist": str(artist[0]) if artist else ""}
