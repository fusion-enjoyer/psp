# İş Planı

Kaynak: [docs/designs/pspkit-design.md](docs/designs/pspkit-design.md) (2026-09-28 /office-hours oturumu ve aynı gün yapılan revizyon).
Kararlar: Yaklaşım D (ayrı uygulamalar + ortak `libpspkit` + tek köprü). USB ve Linux (Pi dahil) ile başlanıyor. Referans cihaz PSP-2000. **Sıra: Deck → Printer** (test edilebilecek yazıcı yok, PSP ve Linux PC var). Deck'in ayar uygulaması PySide6 ile yazılacak.

## M0: USB spike (her şeyden önce)
Mimarinin tamamı bu adımın sonucuna bağlı.
Test rehberi: [docs/m0.md](docs/m0.md)
- [ ] PSP-2006'da CFW sürümünü doğrula (ARK-4 / PRO / LME, 6.61)
- [x] `pspdev` toolchain'i kur (`~/pspdev`, release v20260901, psp-gcc 15.2; `usbhostfs_pc` pakette hazır geliyor)
- [x] `usbhostfs.prx`'i pinlenmiş `third_party/psplinkusb` submodule'ünden derle (commit `8cc9876`)
- [x] `psplinkusb` lisansı BSD-3-Clause. Submodule olarak kullanılıyor, `usbhostfs.prx` EBOOT'un yanında dağıtılacak
- [x] VID:PID kaynak kodda `054c:01c9` (`usbhostfs.h`); gerçek cihazda `lsusb` ile teyit bekleniyor
- [x] EBOOT (`psp/m0`): usbhostfs.prx'i KUBridge ile yükler, USB'yi başlatır, kanal 4'e ping yollar, pong ile RTT ölçer, async ve bulk hızını ölçer
- [x] PC tarafı `tools/m0/echo.py`: localhost:10004, pong/ack/rate, PC → PSP mesaj (sahte soketle test edildi)
- [ ] **PSP-2006 üzerinde çalıştır** ve sonuçları kaydet
- [ ] Soru: user-mode EBOOT'tan usbhostfs'e geç bağlanma çalışıyor mu (KUBridge + late-link)? Çalışmıyorsa plan B: küçük bir kernel PRX
- [ ] Gecikmeyi ölç (Deck hedefi: tuşa basıştan aksiyona < 100ms)
- [x] M0b: Taşıma katmanı (`transport.c`: USB → 15 sn içinde PC gelmezse TCP'ye geçiş, `tcp.cfg` ile zorlama). PPSSPP 1.20.4 (Flatpak) üzerinde uçtan uca çalıştı: ping/pong, tuş ack, stream/bulk, öz-test raporu
- [x] PPSSPP'de KUBridge + usbhostfs.prx yüklemesi ve sonradan bağlanma (late-link) çalışıyor. Gerçek donanımda hâlâ doğrulanmalı
- [x] Köprü üzerinden ekran görüntüsü (`shot` → `frame` → PNG); gerçek PSP'de de işe yarar
- [x] `make -C psp/m0 ppsspp`: kablo olmadan tek komutla test

## Deck MVP (2026-09-28): PPSSPP'de uçtan uca çalışıyor, 21 test
Rehber: [docs/deck.md](docs/deck.md)

### Yapıldı
- [x] Repo iskeleti: `psp/libpspkit/`, `psp/apps/deck/`, `bridge/pspkit/`, `desktop/`, `scripts/`
- [x] libpspkit: USB/TCP taşıma (otomatik seçim, `tcp.cfg`), saniyede bir yeniden bağlanma, satır protokolü, ekran görüntüsü (`shot`/`frame`)
- [x] libpspkit: çift tamponlu yazılım çizimi (dikdörtgen, çizgi, daire, üçgen, 8x8 font, △○✕□ ve ok sembolleri)
- [x] Deck EBOOT: kumanda şeklinde yerleşim, 10 tuş × 4 katman (L, R, L+R), analog çubuk, canlı durum, bildirimler, gecikme göstergesi, uyku engelleme (`scePowerTick`)
- [x] Protokol v1: `hello`/`press`/`analog`/`ping` ↔ `clear`/`tile`/`analog`/`title`/`toast`/`ack`/`shot`/`sim`
- [x] Köprü (asyncio, stdlib + PyYAML): TCP 10200 + USB (localhost:10004, `usbhostfs_pc`'yi kendisi başlatıyor, host0 = boş klasör), SIGTERM ile temiz kapanma
- [x] `deck.yaml`: doğrulama, okunur hata mesajları, canlı yenileme; bozuk dosyada önceki ayarı koruyup hatayı PSP'de gösterme
- [x] Aksiyonlar: klavye (saf Python uinput, X11 + Wayland), komut, aç (xdg-open), medya (MPRIS), ses ve mikrofon (wpctl/pactl), OBS (stdlib websocket v5, kimlik doğrulamalı)
- [x] Canlı durum: ses %, sessiz, mikrofon kapalı, çalan parça, aktif OBS sahnesi, REC/CANLI
- [x] Kontrol soketi + CLI: `run`, `status`, `shot`, `sim`, `actions`, `init`, `doctor`
- [x] PySide6 ayar uygulaması: PSP şeklinde önizleme, katman sekmeleri, aksiyon formları katalogdan, renk paleti, analog ataması, OBS ayarı, "Dene", PSP ekran görüntüsü, otomatik kaydetme, dosya dışarıdan değişince yeniden yükleme
- [x] `scripts/install.sh`: komutlar, systemd user servisi, menü girişi, `--uninstall`; udev kuralı `uaccess` ile
- [x] Testler: 21 unittest (metin, ayar, tuş ayrıştırma, sahte OBS sunucusu, sahte PSP ile uçtan uca köprü)

### Kalan
- [ ] **Gerçek PSP-2006'da USB ile çalıştır** (M0'daki açık sorular burada da geçerli)
- [ ] Analog çubuk gerçek cihazda: ölü bölge / hız ayarı (protokol testte doğrulandı, PPSSPP'de elle denenmedi)
- [ ] Gerçek OBS ile deneme (şimdilik sahte sunucuyla test edildi)
- [ ] İmleçli ızgara modu (Select'e uzun basınca) ve sayfalar
- [ ] Karo ikonları (köprü küçük bitmap gönderir)
- [ ] Hazır profiller: yayıncı, geliştirici, müzik
- [ ] PSP-1000 (32MB) testi
- [ ] Companion Satellite eklentisi, Home Assistant aksiyonu, çok adımlı makrolar
- [ ] **Reddit teaser videosu** (r/PSP, r/linux, r/streaming)

## Printer (Deck'ten sonra)
- [ ] P1: Printer arayüzü + Moonraker adaptörü, sahte Moonraker test fikstürü, mDNS keşfi, tel kafesteki 3 ekran
- [ ] P2 Göz: ffmpeg ile MJPEG akışı ve sceJpeg; H.264 timelapse; bitti/hata alarmı; Obico
- [ ] P3 Eller: köprüde güvenlik kuralları; L/R ile baby-step; jog; preheat; makrolar; güç kontrolü
- [ ] P4 Dosya ve filament: thumbnail'li G-code tarayıcı, Spoolman, geçmiş
- [ ] P5 PSP GPU: 3D bed mesh, 3D katman önizleme, sıcaklık grafiği, çiftlik görünümü, ambient mod
- [ ] OctoPrint adaptörü (durum ve temel kontrol)

## Lansman (v1)
- [ ] CI: pspdev Docker ile EBOOT build'i, pytest, tag'de otomatik GitHub Release
- [ ] `install.sh` (x86_64 + aarch64/Pi): udev, systemd, köprü ve masaüstü uygulaması kurulumu
- [ ] Proje adı (`pspkit` yer tutucu), çakışma kontrolü
- [ ] 30 saniyelik video ve paylaşım

## Sonrası (talebe göre)
- [ ] Deck: Companion Satellite eklentisi, Home Assistant, çok adımlı makrolar, sayfalar
- [ ] Adaptörler: PrusaLink, Home Assistant, Bambu (LAN-only + Developer Mode)
- [ ] Media (MPRIS tam ekran uygulama), MIDI (python-rtmidi), Dev (CI/metrikler)
- [ ] Wi-Fi taşıma katmanı (stok firmware'de WPA2-PSK desteği doğrulanacak)
- [ ] Windows (Zadig/WCID; PySide6 uygulaması aynı kodla çalışır)
- [ ] Generic server-driven uygulama
