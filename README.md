# pspkit (çalışma adı)

PSP'yi masanda gerçekten iş gören bir kontrol paneline çevirir. PSP'yi USB ile Linux PC'ye ya da Raspberry Pi'a takarsın, XMB'den uygulamayı açarsın, çalışır.

İlk uygulama **Deck**: Stream Deck tarzı makro paneli. Her karo bir PSP tuşuna bağlı, L/R ile katmanlar, analog çubuk çevirme düğmesi gibi çalışıyor. Karolar bir masaüstü uygulamasıyla (PySide6) ayarlanıyor. Sonra **Printer** (3D yazıcı paneli) gelecek, ardından Media, MIDI ve Dev.

> Durum: M0 (USB testi) kodu hazır, gerçek PSP üzerinde test bekliyor. Rehber: [docs/m0.md](docs/m0.md)

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
