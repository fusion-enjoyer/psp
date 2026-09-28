"""End to end: a fake PSP Deck talks to a real Bridge over TCP."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pspkit import bridge as bridge_mod
from pspkit import control


class FakePSP:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer

    @classmethod
    async def connect(cls, port):
        for _ in range(50):
            try:
                return cls(*await asyncio.open_connection("127.0.0.1", port))
            except OSError:
                await asyncio.sleep(0.05)
        raise RuntimeError("bridge did not start")

    def send(self, line):
        self.writer.write((line + "\n").encode())

    async def expect(self, prefix, timeout=3.0):
        async def find():
            while True:
                line = (await self.reader.readline()).decode().rstrip("\n")
                if not line:
                    raise ConnectionError("closed")
                if line.startswith(prefix):
                    return line
        return await asyncio.wait_for(find(), timeout)


class BridgeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.marker = d / "pressed.txt"
        self.cfg = d / "deck.yaml"
        self.cfg.write_text(f"""
title: Test Deck
analog: {{normal: scroll, l: none}}
layers:
  normal:
    cross:  {{label: "Çalıştır|Komut", color: "#3ddc84", action: command, cmd: "echo ok >> {self.marker}"}}
    circle: {{label: "Bozuk", color: "#f04e4e", action: command, cmd: ""}}
  l:
    up:     {{label: "L Up", color: "#8b5cf6", action: none}}
""", encoding="utf-8")
        self.sock = d / "bridge.sock"
        self.shots = d / "shots"
        self.bridge = bridge_mod.Bridge(self.cfg, tcp_port=0, usb=False)
        # port 0: find the real one once the server is up
        self.patch = mock.patch.object(bridge_mod, "shots_dir", return_value=self.shots)
        self.patch.start()
        self.task = asyncio.create_task(self.bridge.serve(self.sock))
        for _ in range(100):
            tcp = [s for s in self.bridge._servers if s.sockets and s.sockets[0].family.name == "AF_INET"]
            if tcp:
                self.port = tcp[0].sockets[0].getsockname()[1]
                break
            await asyncio.sleep(0.02)
        self.psp = await FakePSP.connect(self.port)
        self.psp.send("hello deck 1 tcp fw=06610010 circle=1")

    async def asyncTearDown(self):
        self.psp.writer.close()
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        self.patch.stop()
        self.tmp.cleanup()

    async def ctl(self, req):
        return await asyncio.to_thread(control.request, req, self.sock, 5)

    async def test_tiles_press_and_errors(self):
        self.assertEqual(await self.psp.expect("clear"), "clear")
        self.assertEqual(await self.psp.expect("title"), "title Test Deck")
        tile = await self.psp.expect("tile normal cross")
        self.assertEqual(tile, "tile normal cross 3ddc84 0 Calistir|Komut")  # ASCII for the PSP font

        self.psp.send("press normal cross 123456")
        self.assertEqual(await self.psp.expect("ack"), "ack 123456")
        for _ in range(50):
            if self.marker.exists():
                break
            await asyncio.sleep(0.05)
        self.assertEqual(self.marker.read_text().strip(), "ok")

        self.psp.send("press normal circle 1")
        toast = await self.psp.expect("toast")
        self.assertTrue(toast.startswith("toast f04e4e Bozuk: komut bos"), toast)

    async def test_ping_and_unassigned_press(self):
        self.psp.send("ping 42")
        self.assertEqual(await self.psp.expect("pong"), "pong 42")
        self.psp.send("press lr triangle 1")  # nothing there: no crash, still answers
        self.assertEqual(await self.psp.expect("ack"), "ack 1")

    async def test_live_reload_and_bad_config(self):
        await self.psp.expect("tile normal cross")
        text = self.cfg.read_text(encoding="utf-8").replace("Test Deck", "Yeni Baslik")
        self.cfg.write_text(text, encoding="utf-8")
        self.assertEqual(await self.psp.expect("title"), "title Yeni Baslik")

        self.cfg.write_text("layers: [\n", encoding="utf-8")
        toast = await self.psp.expect("toast")
        self.assertIn("Ayar hatasi", toast)
        self.assertEqual(self.bridge.config["title"], "Yeni Baslik")  # previous config kept

    async def test_analog_uses_layer_mode(self):
        self.assertEqual(await self.psp.expect("analog normal"), "analog normal Kaydir")  # sent before tiles
        with mock.patch.object(self.bridge.runner, "analog") as analog:
            self.psp.send("analog normal 10 -127")
            self.psp.send("analog l 0 127")  # mode none on L: ignored
            self.psp.send("ping 1")
            await self.psp.expect("pong")
            await asyncio.sleep(0.1)
        analog.assert_called_once_with("scroll", 10, -127)

    async def test_control_socket(self):
        await self.psp.expect("tile normal cross")
        st = await self.ctl({"cmd": "status"})
        self.assertEqual([s["app"] for s in st["sessions"]], ["deck"])

        run = await self.ctl({"cmd": "run", "tile": {"action": "command", "cmd": f"echo gui >> {self.marker}"}})
        self.assertTrue(run["ok"])
        bad = await self.ctl({"cmd": "run", "tile": {"action": "fly"}})
        self.assertFalse(bad["ok"])

        self.assertTrue((await self.ctl({"cmd": "sim", "layer": "l", "button": "up"}))["ok"])
        self.assertEqual(await self.psp.expect("sim"), "sim l up")

    async def test_screenshot(self):
        await self.psp.expect("tile normal cross")
        shot = asyncio.create_task(self.ctl({"cmd": "shot"}))
        self.assertEqual(await self.psp.expect("shot"), "shot")
        pixels = bytes([255, 0, 0, 255]) * (480 * 272)
        self.psp.writer.write(f"frame 480 272 3 {len(pixels)}\n".encode() + pixels)
        reply = await shot
        self.assertTrue(reply["ok"], reply)
        self.assertTrue(Path(reply["path"]).read_bytes().startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
