import tempfile
import unittest
from pathlib import Path

from pspkit.deck import config
from pspkit.text import to_psp
from pspkit.uinput import KEYS, parse_combo


class TextTest(unittest.TestCase):
    def test_turkish_to_ascii(self):
        self.assertEqual(to_psp("Şarkı Işık Ğüzel ÇÖP"), "Sarki Isik Guzel COP")

    def test_newlines_and_limit(self):
        self.assertEqual(to_psp("bir\nüç"), "bir|uc")
        self.assertEqual(to_psp("x" * 100, 10), "x" * 10)

    def test_drops_unprintable(self):
        self.assertEqual(to_psp("a\x00b ▶ c"), "ab  c")


class ComboTest(unittest.TestCase):
    def test_modifiers_first(self):
        self.assertEqual(parse_combo("t+ctrl+shift"), [KEYS["ctrl"], KEYS["shift"], KEYS["t"]])

    def test_aliases(self):
        self.assertEqual(parse_combo("Control+Escape"), [KEYS["ctrl"], KEYS["esc"]])
        self.assertEqual(parse_combo("super"), [KEYS["super"]])

    def test_unknown_key(self):
        with self.assertRaises(ValueError):
            parse_combo("ctrl+nokta")
        with self.assertRaises(ValueError):
            parse_combo("")


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "deck.yaml"

    def tearDown(self):
        self.dir.cleanup()

    def write(self, text):
        self.path.write_text(text, encoding="utf-8")

    def test_default_is_valid(self):
        config.ensure(self.path)
        cfg = config.load(self.path)
        self.assertEqual(len(cfg["layers"]["normal"]), 10)
        self.assertEqual(cfg["analog"]["normal"], "volume")

    def test_roundtrip(self):
        config.ensure(self.path)
        cfg = config.load(self.path)
        config.save(self.path, cfg)
        self.assertEqual(config.load(self.path), cfg)

    def test_defaults_filled(self):
        self.write("layers: {normal: {up: {action: volume}}}")
        tile = config.load(self.path)["layers"]["normal"]["up"]
        self.assertEqual(tile, {"label": "", "color": "#6b7280", "action": "volume", "op": "up", "step": 5})

    def test_errors_are_readable(self):
        cases = {
            "layers: {normal: {up: {action: fly}}}": "bilinmeyen aksiyon",
            "layers: {normal: {jump: {action: none}}}": "bilinmeyen tuş",
            "layers: {normal: {up: {action: none, color: red}}}": "renk",
            "layers: {normal: {up: {action: key, keys: 'ctrl+nokta'}}}": "bilinmeyen tuş",
            "layers: {normal: {up: {action: volume, op: louder}}}": "geçersiz",
            "analog: {normal: spin}": "analog.normal",
            "layers: {normal: {up: [\n": "satir",
        }
        for text, expected in cases.items():
            self.write(text)
            with self.assertRaises(config.ConfigError) as ctx:
                config.load(self.path)
            self.assertIn(expected, str(ctx.exception).replace("satır", "satir"), text)

    def test_save_rejects_invalid(self):
        with self.assertRaises(config.ConfigError):
            config.save(self.path, {"layers": {"normal": {"up": {"action": "fly"}}}})
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
