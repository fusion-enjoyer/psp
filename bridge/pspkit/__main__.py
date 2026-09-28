"""pspkit bridge command line.

  python3 -m pspkit run        start the bridge (USB + TCP)
  python3 -m pspkit doctor     check the setup and say how to fix problems
  python3 -m pspkit status     is the bridge running, which PSP apps are connected
  python3 -m pspkit shot       save a screenshot of the PSP screen
  python3 -m pspkit sim L B    make the Deck act as if button B was pressed on layer L
  python3 -m pspkit actions    list Deck actions and their parameters
  python3 -m pspkit init       write the default deck.yaml (if missing)
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import logging
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from . import __version__, control
from .deck import config as deck_config


def cmd_run(args) -> int:
    from .bridge import Bridge

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    bridge = Bridge(Path(args.config), tcp_port=args.port, usb=not args.no_usb,
                    spawn_usbhostfs=not args.no_spawn, tcp_host=args.host)

    async def serve() -> None:
        # SIGTERM (systemd stop) and Ctrl+C both end in a clean shutdown,
        # which also stops the usbhostfs_pc we may have started.
        task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, task.cancel)
        try:
            await bridge.serve()
        except asyncio.CancelledError:
            logging.getLogger("pspkit").info("kapatılıyor")

    try:
        asyncio.run(serve())
    except RuntimeError as e:
        print(f"hata: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_status(args) -> int:
    try:
        st = control.request({"cmd": "status"})
    except ConnectionError as e:
        print(e)
        return 1
    print(f"köprü çalışıyor, ayarlar: {st['config']}")
    if st.get("config_error"):
        print(f"  AYAR HATASI: {st['config_error']}")
    if not st["sessions"]:
        print("  bağlı PSP yok")
    for s in st["sessions"]:
        print(f"  {s['transport']:<4} {s['app'] or '(hello bekleniyor)':<8} {s['peer']}")
    return 0


def cmd_shot(args) -> int:
    try:
        reply = control.request({"cmd": "shot"})
    except ConnectionError as e:
        print(e)
        return 1
    print(reply.get("path") or reply.get("error"))
    return 0 if reply.get("ok") else 1


def cmd_sim(args) -> int:
    try:
        reply = control.request({"cmd": "sim", "layer": args.layer, "button": args.button})
    except ConnectionError as e:
        print(e)
        return 1
    if not reply.get("ok"):
        print(reply.get("error"))
    return 0 if reply.get("ok") else 1


def cmd_actions(args) -> int:
    from .deck.actions import CATALOG

    for spec in CATALOG.values():
        print(f"{spec.id:<8} {spec.title}: {spec.help}")
        for p in spec.params:
            extra = f" ({' | '.join(p.choices)})" if p.choices else ""
            hint = f"  {p.help}" if p.help else ""
            print(f"           {p.name}: {p.kind}, varsayılan {p.default!r}{extra}{hint}")
    return 0


def cmd_init(args) -> int:
    path = Path(args.config)
    if path.exists():
        print(f"zaten var: {path}")
    else:
        deck_config.ensure(path)
        print(f"yazıldı: {path}")
    return 0


def cmd_doctor(args) -> int:
    from .bridge import find_usbhostfs_pc

    problems = 0

    def check(ok: bool, text: str, fix: str = "") -> None:
        nonlocal problems
        print(f"  {'OK ' if ok else 'XX '} {text}")
        if not ok:
            problems += 1
            if fix:
                print(f"       -> {fix}")

    print(f"pspkit {__version__} kontrol\n")
    path = Path(args.config)
    try:
        deck_config.load(path)
        check(True, f"ayarlar geçerli: {path}")
    except deck_config.ConfigError as e:
        check(False, f"ayarlar: {e}", "python3 -m pspkit init" if not path.exists() else "dosyayı düzelt")

    check(os.access("/dev/uinput", os.W_OK), "klavye kısayolları için /dev/uinput yazılabilir",
          "echo 'KERNEL==\"uinput\", TAG+=\"uaccess\"' | sudo tee /etc/udev/rules.d/70-pspkit-uinput.rules"
          " && sudo udevadm control --reload-rules && sudo udevadm trigger /dev/uinput")
    check(bool(shutil.which("wpctl") or shutil.which("pactl")), "ses kontrolü (wpctl ya da pactl)",
          "PipeWire: sudo apt install wireplumber")
    try:
        import dbus  # noqa: F401
        check(True, "medya kontrolü (python3-dbus / MPRIS)")
    except ImportError:
        check(False, "medya kontrolü (python3-dbus / MPRIS)", "sudo apt install python3-dbus")
    check(bool(shutil.which("xdg-open")), "URL/dosya açma (xdg-open)", "sudo apt install xdg-utils")

    exe = find_usbhostfs_pc()
    check(bool(exe), f"USB için usbhostfs_pc: {exe or 'yok'}",
          "pspdev kur (docs/m0.md) ya da usbhostfs_pc'yi PATH'e ekle")
    rules = glob.glob("/etc/udev/rules.d/*psplink*") + glob.glob("/etc/udev/rules.d/*pspkit-psp*")
    check(bool(rules), "PSP USB erişimi için udev kuralı",
          f"sudo cp {Path(__file__).resolve().parents[2] / 'scripts/udev/60-pspkit-psp.rules'} /etc/udev/rules.d/"
          " && sudo udevadm control --reload-rules")
    if shutil.which("lsusb"):
        out = subprocess.run(["lsusb"], capture_output=True, text=True).stdout
        check("054c:01c9" in out, "PSP USB'de görünüyor (054c:01c9)",
              "PSP'de Deck uygulamasını aç ve kabloyu tak")

    try:
        st = control.request({"cmd": "status"}, timeout=2)
        apps = ", ".join(f"{s['app'] or 'PSP bekleniyor'}/{s['transport']}" for s in st["sessions"]) or "bağlı PSP yok"
        check(True, f"köprü çalışıyor ({apps})")
    except ConnectionError:
        check(False, "köprü çalışmıyor", "python3 -m pspkit run")

    print(f"\n{'Her şey hazır.' if not problems else f'{problems} sorun var.'}")
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pspkit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(deck_config.default_path()), help="deck.yaml yolu")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="köprüyü başlat")
    p.add_argument("--port", type=int, default=10200, help="TCP portu (PPSSPP / Wi-Fi)")
    p.add_argument("--host", default="127.0.0.1", help="TCP adresi; Wi-Fi icin 0.0.0.0")
    p.add_argument("--no-usb", action="store_true", help="USB'yi (usbhostfs_pc) kullanma")
    p.add_argument("--no-spawn", action="store_true", help="usbhostfs_pc'yi kendin başlatma")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_run)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("shot").set_defaults(fn=cmd_shot)
    p = sub.add_parser("sim")
    p.add_argument("layer", choices=deck_config.LAYERS)
    p.add_argument("button", choices=deck_config.BUTTONS)
    p.set_defaults(fn=cmd_sim)
    sub.add_parser("actions").set_defaults(fn=cmd_actions)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
