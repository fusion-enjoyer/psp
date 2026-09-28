# İş Planı

Kaynak: [docs/designs/pspkit-design.md](docs/designs/pspkit-design.md) (2026-09-28 /office-hours oturumu).
Kararlar: Yaklaşım D (ayrı uygulamalar + ortak `libpspkit` + tek köprü). USB ve Linux (Pi dahil) ile başlanıyor. Referans cihaz PSP-2000. Printer v1'e dört paketin hepsi giriyor.

## M0: USB spike (her şeyden önce)
Mimarinin tamamı bu adımın sonucuna bağlı.
- [ ] PSP-2006'da CFW sürümünü doğrula (ARK-4 / PRO / LME, 6.61)
- [ ] `pspdev` toolchain'i kur (ya da `pspdev/pspdev` Docker imajını kullan)
- [ ] `pspdev/psplinkusb`'yi derle: `usbhostfs.prx` + `usbhostfs_pc` (Linux)
- [ ] `psplinkusb` lisansını kontrol et: gömülü mü kullanılacak, bağımlılık olarak mı?
- [ ] Sony VID:PID'yi `lsusb` ile doğrula (tahmin `054c:01c9`)
- [ ] Minimal EBOOT: async kanala "ping" yazsın, "pong" okusun
- [ ] Host tarafında 20 satırlık Python: `usbhostfs_pc` TCP portuna bağlanıp echo yapsın
- [ ] Soru: async kanallar user-mode EBOOT'tan çağrılabiliyor mu, yoksa kernel PRX mi gerekiyor?
- [ ] Aynı EBOOT PPSSPP'de TCP soketiyle pong alsın
- [ ] Veri hızını ölç (kamera için ~250KB/s gerekiyor)

## M1: Çekirdek + ilk ekran
- [ ] Repo iskeleti: `psp/libpspkit/`, `psp/apps/printer/`, `bridge/`, `docs/`
- [ ] Protokol v0: `hello`, `state`, `cmd`, `ack/err`, ikili `frame`; `proto_version` alanı
- [ ] libpspkit: taşıma katmanı (USB / TCP otomatik seçim), çerçeveleme (cJSON), handshake
- [ ] libpspkit: durum makinesi (bekleniyor → bağlı → koptu → yeniden bağlan)
- [ ] libpspkit: bölgeye duyarlı ○/✕ tuş ipuçları (sistem ayarından okunur)
- [ ] libpspkit widget'ları: durum çubuğu, ipucu çubuğu, progress, gauge, liste, toast, onay, basılı-tut
- [ ] EBOOT: 64MB için large-memory flag (PSP-1000'de 32MB ile düzgün çalışmaya devam etsin)
- [ ] Köprü çekirdeği (Python asyncio): bağlantı, `hello` üzerinden eklenti yönlendirme
- [ ] Printer arayüzü + Moonraker adaptörü (websocket aboneliği)
- [ ] Sahte Moonraker: kayıt/tekrar test fikstürü
- [ ] mDNS keşfi (`python-zeroconf`), seçimin `~/.config/pspkit/` altında hatırlanması
- [ ] Tel kafesteki 3 ekran: bekleme, yazıcı listesi, günlük ekran
- [ ] Tak-çalıştır: udev kuralı ile systemd user servisi, `usbhostfs_pc`'nin otomatik başlaması
- [ ] `pspkit-bridge doctor` teşhis komutu

## M2: Göz
- [ ] Köprü: ffmpeg ile MJPEG akışını 480x272'ye küçült ve ikili frame olarak yolla
- [ ] PSP: sceJpeg donanım çözücüsüyle 5-10 FPS kamera görünümü
- [ ] Timelapse'i PSP uyumlu H.264 MP4'e çevir (profil/seviye araştırılacak), Media Engine ile oynat
- [ ] Baskı bitti / hata alarmı (ses ve ekran)
- [ ] Obico entegrasyonu (spaghetti algılama → alarm → tek tuşla duraklatma)
- [ ] **Reddit teaser videosu** (erken ilgiyi ölçmek için)

## M3: Eller
- [ ] Köprüde güvenlik kuralları: hareket sadece boşta/duraklatılmışken, baby-step toplam ±0.5mm, iptal için basılı tut + onay
- [ ] L/R ile baby-step (0.01mm), kamera açıkken
- [ ] Analog çubukla X/Y, d-pad ile Z; home; extrude
- [ ] Preheat presetleri (PLA/PETG/ABS), Klipper makro listesi
- [ ] Moonraker power device ile aç/kapa

## M4: Dosya ve filament
- [ ] Thumbnail'li G-code tarayıcı, onaylı baskı başlatma
- [ ] Spoolman: kalan filament, "bu baskıya yetmiyor" uyarısı
- [ ] Geçmiş ve istatistik

## M5: PSP GPU
- [ ] GU ile 3D bed mesh (analog çubukla döndürme)
- [ ] 3D katman önizleme (köprü geometriyi sadeleştirip gönderir)
- [ ] Sıcaklık grafiği (son 10 dk)
- [ ] Çiftlik görünümü (2x2 karo, L/R ile geçiş)
- [ ] Ambient mod (saat, son baskının fotoğrafı, ekranı kısma)
- [ ] PSP-1000 (32MB) bellek testi: sığmayan özellik otomatik kapansın

## Lansman (v1)
- [ ] İkinci adaptör: OctoPrint (durum ve temel kontrol)
- [ ] CI: pspdev Docker ile EBOOT build'i, pytest, tag'de otomatik GitHub Release
- [ ] `install.sh` (x86_64 + aarch64/Pi): udev, systemd, köprü kurulumu
- [ ] Proje adı (`pspkit` yer tutucu), çakışma kontrolü
- [ ] 30 saniyelik video ve paylaşım: r/PSP, r/klippers, r/3Dprinting

## Sonrası (talebe göre)
- [ ] Adaptörler: PrusaLink, Home Assistant (her şeyi kapsayan yol), Bambu (LAN-only + Developer Mode)
- [ ] Deck (Companion Satellite + yerel makrolar), Media (MPRIS), MIDI (python-rtmidi), Dev (CI/metrikler)
- [ ] Wi-Fi taşıma katmanı (stok firmware'de WPA2-PSK desteği doğrulanacak)
- [ ] Windows (Zadig/WCID)
- [ ] Generic server-driven uygulama
