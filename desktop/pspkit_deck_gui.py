#!/usr/bin/env python3
"""pspkit Deck: desktop editor for deck.yaml.

Click a tile on the PSP-shaped preview, pick a label, color and action on the
right. Every change is saved at once and the running bridge pushes it to the
PSP within a second. "Dene" runs the action on this PC through the bridge.

  python3 desktop/pspkit_deck_gui.py [--config PATH] [--screenshot OUT.png]
"""
from __future__ import annotations

import argparse
import copy
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bridge"))

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox, QDialog,  # noqa: E402
                               QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QSpinBox, QTabBar, QVBoxLayout, QWidget)

from pspkit import control  # noqa: E402
from pspkit.deck import actions, config as deck_config  # noqa: E402
from pspkit.uinput import parse_combo  # noqa: E402

SCALE = 1.5
GLYPHS = {"up": "▲", "down": "▼", "left": "◀", "right": "▶", "triangle": "△", "circle": "○",
          "cross": "✕", "square": "□", "start": "START", "select": "SELECT"}
BUTTON_TITLES = {"up": "Yukarı", "down": "Aşağı", "left": "Sol", "right": "Sağ", "triangle": "Üçgen",
                 "circle": "Daire", "cross": "Çarpı", "square": "Kare", "start": "START", "select": "SELECT"}
ANALOG_TITLES = {"none": "Kullanma", "volume": "Ses seviyesi", "scroll": "Kaydırma (fare tekerleği)"}
PALETTE = ["#3d8bfd", "#a371f7", "#f04e4e", "#3ddc84", "#f5a524", "#14b8a6", "#8b5cf6", "#6b7280"]
BG, BAR, DIM, TEXT, MUTED = "#121419", "#1b1e25", "#2a2e37", "#eef0f4", "#8a909c"

# Same geometry as psp/apps/deck/main.c, in PSP pixels.
TILE_W, TILE_H, GAP = 64, 70, 4


def _row(r): return 26 + r * (TILE_H + GAP)
def _lcol(c): return 6 + c * (TILE_W + GAP)
def _rcol(c): return 274 + c * (TILE_W + GAP)


RECTS = {
    "up": (_lcol(1), _row(0), TILE_W, TILE_H), "down": (_lcol(1), _row(2), TILE_W, TILE_H),
    "left": (_lcol(0), _row(1), TILE_W, TILE_H), "right": (_lcol(2), _row(1), TILE_W, TILE_H),
    "triangle": (_rcol(1), _row(0), TILE_W, TILE_H), "cross": (_rcol(1), _row(2), TILE_W, TILE_H),
    "square": (_rcol(0), _row(1), TILE_W, TILE_H), "circle": (_rcol(2), _row(1), TILE_W, TILE_H),
    "select": (212, _row(0), 56, TILE_H), "start": (212, _row(2), 56, TILE_H),
}


def mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(int(ca.red() * t + cb.red() * (1 - t)), int(ca.green() * t + cb.green() * (1 - t)),
                  int(ca.blue() * t + cb.blue() * (1 - t)))


class Bus(QObject):
    """Carries results from worker threads back to the Qt thread."""
    done = Signal(object, object)  # (callback, result)


class PspPad(QWidget):
    """PSP-shaped preview; click a tile to select it."""
    selected = Signal(str)

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.w = window
        self.setFixedSize(int(480 * SCALE), int(272 * SCALE))
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.hover: str | None = None

    def rect_of(self, button: str) -> QRect:
        x, y, w, h = RECTS[button]
        return QRect(int(x * SCALE), int(y * SCALE), int(w * SCALE), int(h * SCALE))

    def button_at(self, pos: QPoint) -> str | None:
        return next((b for b in deck_config.BUTTONS if self.rect_of(b).contains(pos)), None)

    def mouseMoveEvent(self, e):
        hover = self.button_at(e.position().toPoint())
        if hover != self.hover:
            self.hover = hover
            self.update()

    def mousePressEvent(self, e):
        b = self.button_at(e.position().toPoint())
        if b:
            self.selected.emit(b)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        s = SCALE
        p.fillRect(QRect(0, 0, self.width(), int(22 * s)), QColor(BAR))
        p.setPen(QColor(TEXT))
        p.setFont(QFont("monospace", 10))
        p.drawText(QRect(int(8 * s), 0, 300, int(22 * s)), Qt.AlignVCenter, self.w.cfg["title"])
        layer = self.w.layer
        for i, name in enumerate(("L", "R")):
            on = (layer in ("l", "lr")) if name == "L" else (layer in ("r", "lr"))
            r = QRect(int((420 + i * 28) * s), int(4 * s), int(24 * s), int(14 * s))
            p.fillRect(r, QColor(TEXT if on else DIM))
            p.setPen(QColor("#101010" if on else MUTED))
            p.drawText(r, Qt.AlignCenter, name)

        tiles = self.w.cfg["layers"][layer]
        for b in deck_config.BUTTONS:
            self._tile(p, b, tiles.get(b))

        mid = QRect(int(212 * s), int(_row(1) * s), int(56 * s), int(TILE_H * s))
        p.setPen(QPen(QColor(DIM), 1))
        p.drawRect(mid)
        p.setPen(QColor(MUTED))
        p.setFont(QFont("monospace", 8))
        p.drawText(mid.adjusted(0, 8, 0, -40), Qt.AlignHCenter, "katman")
        p.setPen(QColor(TEXT))
        p.setFont(QFont("monospace", 13, QFont.Bold))
        p.drawText(mid.adjusted(0, 20, 0, 0), Qt.AlignCenter, deck_config.LAYER_TITLES[layer].upper())

        stick = QRect(int(_lcol(1) * s), int(_row(1) * s), int(TILE_W * s), int(TILE_H * s))
        p.setPen(QPen(QColor("#4a505c"), 2))
        c = QPoint(stick.center().x(), stick.top() + int(24 * s))
        p.drawEllipse(c, int(12 * s), int(12 * s))
        p.drawEllipse(c, int(5 * s), int(5 * s))
        p.setPen(QColor(MUTED))
        p.setFont(QFont("monospace", 8))
        label = {"none": "-", "volume": "Ses", "scroll": "Kaydır"}[self.w.cfg["analog"][layer]]
        p.drawText(stick.adjusted(0, int(40 * s), 0, 0), Qt.AlignHCenter, label)

        p.fillRect(QRect(0, int(250 * s), self.width(), self.height()), QColor(BAR))
        p.setPen(QColor(MUTED))
        p.drawText(QRect(int(8 * s), int(250 * s), self.width(), int(22 * s)), Qt.AlignVCenter,
                   "Bir karoya tıkla ve sağdan düzenle. Değişiklikler PSP'ye anında gider.")

    def _tile(self, p: QPainter, b: str, tile: dict | None):
        r = self.rect_of(b)
        sel = b == self.w.button
        if tile is None:
            p.setPen(QPen(QColor("#ffffff" if sel else (MUTED if b == self.hover else DIM)), 3 if sel else 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r.adjusted(1, 1, -1, -1))
            p.setPen(QColor("#4a505c"))
            p.setFont(QFont("sans", 16 if len(GLYPHS[b]) == 1 else 8))
            p.drawText(r, Qt.AlignCenter, GLYPHS[b])
            return
        color = tile["color"]
        p.fillRect(r, mix(color, BG, 0.25 if b != self.hover else 0.4))
        p.setPen(QPen(QColor("#ffffff" if sel else color), 4 if sel else 3))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(1, 1, -1, -1))
        p.setPen(QColor(color))
        glyph = GLYPHS[b]
        if len(glyph) == 1:
            p.setFont(QFont("sans", 11))
            p.drawText(r.adjusted(6, 3, 0, 0), Qt.AlignLeft | Qt.AlignTop, glyph)
        else:
            p.setFont(QFont("sans", 7))
            p.drawText(r.adjusted(0, 4, 0, 0), Qt.AlignHCenter | Qt.AlignTop, glyph)
        p.setPen(QColor(TEXT))
        p.setFont(QFont("monospace", 9))
        text = "\n".join(part.strip() for part in tile["label"].split("|")) or "-"
        p.drawText(r.adjusted(4, int(20 * SCALE), -4, -4), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, text)


class ObsDialog(QDialog):
    def __init__(self, parent, obs: dict):
        super().__init__(parent)
        self.setWindowTitle("OBS bağlantısı")
        form = QFormLayout(self)
        self.host = QLineEdit(obs["host"])
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(obs["port"])
        self.password = QLineEdit(obs["password"])
        self.password.setEchoMode(QLineEdit.Password)
        form.addRow(QLabel("OBS'te: Araçlar > WebSocket Sunucu Ayarları"))
        form.addRow("Adres", self.host)
        form.addRow("Port", self.port)
        form.addRow("Şifre", self.password)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self) -> dict:
        return {"host": self.host.text().strip() or "127.0.0.1", "port": self.port.value(),
                "password": self.password.text()}


class MainWindow(QMainWindow):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        deck_config.ensure(path)
        self.cfg = deck_config.load(path)
        self.layer, self.button = "normal", "triangle"
        self._stamp = self._file_stamp()
        self._loading = False
        self.bus = Bus()
        self.bus.done.connect(lambda cb, result: cb(result))

        self.setWindowTitle("pspkit Deck")
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        left = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("Başlık"))
        self.title = QLineEdit(self.cfg["title"])
        self.title.textEdited.connect(self._title_changed)
        top.addWidget(self.title, 1)
        obs = QPushButton("OBS...")
        obs.clicked.connect(self._edit_obs)
        top.addWidget(obs)
        shot = QPushButton("PSP ekran görüntüsü")
        shot.clicked.connect(self._screenshot)
        top.addWidget(shot)
        left.addLayout(top)

        self.tabs = QTabBar()
        for layer in deck_config.LAYERS:
            hint = {"normal": "", "l": " (L basılı)", "r": " (R basılı)", "lr": " (L+R basılı)"}[layer]
            self.tabs.addTab(deck_config.LAYER_TITLES[layer] + hint)
        self.tabs.currentChanged.connect(self._layer_changed)
        left.addWidget(self.tabs)

        self.pad = PspPad(self)
        self.pad.selected.connect(self._select)
        left.addWidget(self.pad)

        analog = QHBoxLayout()
        analog.addWidget(QLabel("Analog çubuk (bu katmanda):"))
        self.analog = QComboBox()
        for mode in deck_config.ANALOG_MODES:
            self.analog.addItem(ANALOG_TITLES[mode], mode)
        self.analog.currentIndexChanged.connect(self._analog_changed)
        analog.addWidget(self.analog, 1)
        left.addLayout(analog)
        left.addStretch(1)
        root.addLayout(left)

        self.editor = QGroupBox()
        self.editor.setMinimumWidth(340)
        ed = QVBoxLayout(self.editor)
        form = QFormLayout()
        self.label = QLineEdit()
        self.label.setPlaceholderText("örnek: Sahne|Kamera  ( | = alt satır )")
        self.label.textEdited.connect(self._tile_changed)
        form.addRow("Etiket", self.label)

        colors = QHBoxLayout()
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(QSize(44, 26))
        self.color_btn.clicked.connect(self._pick_color)
        colors.addWidget(self.color_btn)
        for c in PALETTE:
            sw = QPushButton()
            sw.setFixedSize(QSize(22, 22))
            sw.setStyleSheet(f"background:{c}; border:1px solid #222;")
            sw.clicked.connect(lambda _=False, c=c: self._set_color(c))
            colors.addWidget(sw)
        colors.addStretch(1)
        form.addRow("Renk", colors)

        self.action = QComboBox()
        for spec in actions.CATALOG.values():
            self.action.addItem(spec.title, spec.id)
        self.action.currentIndexChanged.connect(self._action_changed)
        form.addRow("Aksiyon", self.action)
        ed.addLayout(form)
        self.help = QLabel()
        self.help.setWordWrap(True)
        self.help.setStyleSheet(f"color:{MUTED};")
        ed.addWidget(self.help)
        self.params_box = QWidget()
        self.params_form = QFormLayout(self.params_box)
        self.params_form.setContentsMargins(0, 0, 0, 0)
        ed.addWidget(self.params_box)
        self.error = QLabel()
        self.error.setStyleSheet("color:#f04e4e;")
        self.error.setWordWrap(True)
        ed.addWidget(self.error)
        row = QHBoxLayout()
        self.try_btn = QPushButton("Dene (PC'de çalıştır)")
        self.try_btn.clicked.connect(self._try)
        row.addWidget(self.try_btn)
        clear = QPushButton("Temizle")
        clear.clicked.connect(self._clear_tile)
        row.addWidget(clear)
        ed.addLayout(row)
        ed.addStretch(1)
        root.addWidget(self.editor)

        self.status = QLabel()
        self.statusBar().addPermanentWidget(self.status)
        quit_action = QAction("Çıkış", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

        self._save_timer = QTimer(self, singleShot=True, interval=350, timeout=self._save)
        self._poll = QTimer(self, interval=2000, timeout=self._poll_bridge)
        self._poll.start()
        self._poll_bridge()
        self._select(self.button)

    # ---- helpers ----

    def _file_stamp(self):
        try:
            st = self.path.stat()
            return (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            return None

    def _tile(self) -> dict | None:
        return self.cfg["layers"][self.layer].get(self.button)

    def _in_thread(self, fn, callback):
        def run():
            try:
                result = fn()
            except Exception as e:  # shown in the UI
                result = e
            self.bus.done.emit(callback, result)
        threading.Thread(target=run, daemon=True).start()

    # ---- selection / editor ----

    def _layer_changed(self, index: int):
        self.layer = deck_config.LAYERS[index]
        self._select(self.button)

    def _select(self, button: str):
        self.button = button
        self._loading = True
        tile = self._tile()
        layer_title = deck_config.LAYER_TITLES[self.layer]
        glyph = f"{GLYPHS[button]} " if len(GLYPHS[button]) == 1 else ""
        self.editor.setTitle(f"{glyph}{BUTTON_TITLES[button]}  -  {layer_title} katmanı")
        self.label.setText(tile["label"] if tile else "")
        self._show_color(tile["color"] if tile else PALETTE[0])
        idx = self.action.findData(tile["action"] if tile else "none")
        self.action.setCurrentIndex(idx)
        self.analog.setCurrentIndex(self.analog.findData(self.cfg["analog"][self.layer]))
        self._build_params()
        self._loading = False
        self.error.clear()
        self.pad.update()

    def _show_color(self, color: str):
        self._color = color
        self.color_btn.setStyleSheet(f"background:{color}; border:2px solid #ddd;")

    def _build_params(self):
        while self.params_form.rowCount():
            self.params_form.removeRow(0)
        spec = actions.CATALOG[self.action.currentData()]
        self.help.setText(spec.help)
        tile = self._tile() or {}
        self.param_widgets = {}
        for param in spec.params:
            value = tile.get(param.name, param.default) if tile.get("action") == spec.id else param.default
            if param.kind == "choice":
                w = QComboBox()
                for choice in param.choices:
                    w.addItem(choice, choice)
                w.setCurrentIndex(max(0, w.findData(value)))
                w.currentIndexChanged.connect(self._tile_changed)
            elif param.kind == "int":
                w = QSpinBox()
                w.setRange(-1000, 1000)
                w.setValue(int(value))
                w.valueChanged.connect(self._tile_changed)
            else:
                w = QLineEdit(str(value))
                w.setPlaceholderText(param.help)
                w.textEdited.connect(self._tile_changed)
            if param.help:
                w.setToolTip(param.help)
            self.param_widgets[param.name] = w
            self.params_form.addRow(param.title, w)

    def _collect(self) -> dict:
        tile = {"label": self.label.text(), "color": self._color, "action": self.action.currentData()}
        for name, w in self.param_widgets.items():
            if isinstance(w, QComboBox):
                tile[name] = w.currentData()
            elif isinstance(w, QSpinBox):
                tile[name] = w.value()
            else:
                tile[name] = w.text()
        return tile

    # ---- edits ----

    def _tile_changed(self, *_):
        if self._loading:
            return
        tile = self._collect()
        if tile["action"] == "key":
            try:
                parse_combo(tile["keys"])
            except ValueError as e:
                self.error.setText(f"Tuşlar: {e}")
                return
        self.error.clear()
        self.cfg["layers"][self.layer][self.button] = tile
        self._schedule_save()

    def _action_changed(self, *_):
        if self._loading:
            return
        self._build_params()
        if not self.label.text():
            self.label.setText(self.action.currentText().split(" ")[0])
        self._tile_changed()

    def _set_color(self, color: str):
        self._show_color(color)
        self._tile_changed()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Karo rengi")
        if c.isValid():
            self._set_color(c.name())

    def _clear_tile(self):
        self.cfg["layers"][self.layer].pop(self.button, None)
        self._select(self.button)
        self._schedule_save()

    def _title_changed(self, text: str):
        self.cfg["title"] = text
        self._schedule_save()

    def _analog_changed(self, *_):
        if self._loading:
            return
        self.cfg["analog"][self.layer] = self.analog.currentData()
        self._schedule_save()

    def _edit_obs(self):
        dlg = ObsDialog(self, self.cfg["obs"])
        if dlg.exec():
            self.cfg["obs"] = dlg.value()
            self._schedule_save()

    def _schedule_save(self):
        self.pad.update()
        self._save_timer.start()

    def _save(self):
        try:
            deck_config.save(self.path, self.cfg)
        except deck_config.ConfigError as e:
            self.error.setText(str(e))
            return
        self._stamp = self._file_stamp()
        self.statusBar().showMessage("Kaydedildi, PSP güncelleniyor", 2500)

    # ---- bridge ----

    def _poll_bridge(self):
        # The file may also have been edited by hand: follow it.
        stamp = self._file_stamp()
        if stamp != self._stamp and not self._save_timer.isActive():
            self._stamp = stamp
            try:
                self.cfg = deck_config.load(self.path)
                self.title.setText(self.cfg["title"])
                self._select(self.button)
                self.statusBar().showMessage("Dosya dışarıdan değişti, yeniden yüklendi", 3000)
            except deck_config.ConfigError as e:
                self.error.setText(f"deck.yaml: {e}")
        self._in_thread(lambda: control.request({"cmd": "status"}, timeout=1), self._show_status)

    def _show_status(self, st):
        if isinstance(st, Exception):
            self.status.setText("  Köprü çalışmıyor: python3 -m pspkit run  ")
            self.status.setStyleSheet("color:#f04e4e;")
            return
        decks = [s for s in st["sessions"] if s["app"] == "deck"]
        if decks:
            self.status.setText("  Köprü çalışıyor  -  PSP bağlı (" + ", ".join(s["transport"] for s in decks) + ")  ")
            self.status.setStyleSheet("color:#3ddc84;")
        else:
            self.status.setText("  Köprü çalışıyor  -  PSP bağlı değil  ")
            self.status.setStyleSheet(f"color:{MUTED};")

    def _try(self):
        tile = self._collect()
        self.try_btn.setEnabled(False)

        def done(reply):
            self.try_btn.setEnabled(True)
            if isinstance(reply, Exception):
                self.error.setText(str(reply))
            elif not reply.get("ok"):
                self.error.setText(reply.get("error", "hata"))
            else:
                self.error.clear()
                self.statusBar().showMessage(reply.get("message") or "Çalıştı", 2500)
        self._in_thread(lambda: control.request({"cmd": "run", "tile": tile}), done)

    def _screenshot(self):
        def done(reply):
            if isinstance(reply, Exception) or not reply.get("ok"):
                msg = str(reply) if isinstance(reply, Exception) else reply.get("error")
                QMessageBox.warning(self, "Ekran görüntüsü", msg)
                return
            dlg = QDialog(self)
            dlg.setWindowTitle(reply["path"])
            lay = QVBoxLayout(dlg)
            img = QLabel()
            img.setPixmap(QPixmap(reply["path"]).scaled(960, 544, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lay.addWidget(img)
            lay.addWidget(QLabel(reply["path"]))
            dlg.exec()
        self._in_thread(lambda: control.request({"cmd": "shot"}), done)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=deck_config.default_path())
    ap.add_argument("--screenshot", type=Path, help="pencereyi PNG olarak kaydet ve çık (dokümantasyon/test)")
    ap.add_argument("--layer", choices=deck_config.LAYERS, default="normal")
    ap.add_argument("--button", choices=deck_config.BUTTONS, default="triangle")
    args = ap.parse_args()

    app = QApplication(sys.argv[:1])
    app.setApplicationName("pspkit Deck")
    app.setStyle("Fusion")
    win = MainWindow(args.config)
    win.tabs.setCurrentIndex(deck_config.LAYERS.index(args.layer))
    win._select(args.button)
    win.show()
    if args.screenshot:
        def grab():
            win.grab().save(str(args.screenshot))
            app.quit()
        QTimer.singleShot(1500, grab)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
