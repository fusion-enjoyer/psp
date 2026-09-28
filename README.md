# pspkit (çalışma adı)

PSP'yi masanda gerçekten iş gören bir kontrol paneline çevirir. PSP'yi USB ile Linux PC'ye ya da Raspberry Pi'a takarsın, XMB'den uygulamayı açarsın, çalışır.

İlk uygulama **Printer**: 3D yazıcı paneli. Canlı kamera, ilk katmanda L/R ile Z ayarı, dosya/filament yönetimi ve PSP'nin GPU'suyla 3D bed mesh içerir. Sonra sırayla Deck, Media, MIDI ve Dev gelecek.

> Durum: tasarım aşaması, henüz kod yok.

- Tasarım: [docs/designs/pspkit-design.md](docs/designs/pspkit-design.md)
- Tel kafes: [docs/designs/printer-flow-wireframe.png](docs/designs/printer-flow-wireframe.png)
- İş planı: [TODOS.md](TODOS.md)

## Mimari (kısaca)

```
PSP (ayrı EBOOT'lar + libpspkit)
  │  USB: usbhostfs async kanalı   │  PPSSPP: TCP
  ▼                                ▼
usbhostfs_pc ──localhost TCP──► köprü (Python, Linux/Pi) ──► Moonraker / OctoPrint / ... adaptörleri
```

Gereken: CFW'li bir PSP (ARK-4 / PRO / LME) ve Linux. Windows ve Wi-Fi desteği talebe göre sonra gelecek.
