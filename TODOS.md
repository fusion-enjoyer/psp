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
- [ ] M0b: Aynı EBOOT PPSSPP'de TCP soketiyle pong alsın (PPSSPP kurulumu gerekli)

## Deck D1: çekirdek + ilk çalışan tuş
- [ ] Repo iskeleti: `psp/libpspkit/`, `psp/apps/deck/`, `bridge/`, `desktop/`, `docs/`
- [ ] Protokol v0: `hello`, `state`, `cmd`, `ack/err`, ikili `frame`; `proto_version` alanı
- [ ] libpspkit: taşıma katmanı (USB / TCP otomatik seçim), çerçeveleme (cJSON), handshake
- [ ] libpspkit: durum makinesi (bekleniyor → bağlı → koptu → yeniden bağlan)
- [ ] libpspkit: bölgeye duyarlı ○/✕ (sistem ayarından okunur)
- [ ] libpspkit widget'ları: durum çubuğu, ipucu çubuğu, karo ızgarası, toast
- [ ] EBOOT: large-memory flag (PSP-1000'de 32MB ile de düzgün çalışsın)
- [ ] Köprü çekirdeği (Python asyncio): bağlantı, `hello` üzerinden eklentiye yönlendirme
- [ ] `deck.yaml` şeması ve yükleyici (`~/.config/pspkit/deck.yaml`), dosya izleme ve canlı yenileme
- [ ] Deck EBOOT: fiziksel tuş modu (4x3 karo, her karoda tuş işareti)
- [ ] Aksiyon eklenti arayüzü (köprü)
- [ ] Aksiyon: klavye kısayolu, uinput sanal klavye (python-evdev) ile. X11 ve Wayland'de test
- [ ] Aksiyon: komut çalıştır, uygulama/URL aç
- [ ] Tak-çalıştır: udev kuralı (PSP + `/dev/uinput` izni) ile systemd user servisi, `usbhostfs_pc`'nin otomatik başlaması

## Deck D2: katmanlar + canlı durum
- [ ] L, R ve L+R katmanları
- [ ] Analog çubuk çevirme düğmesi (ses, scroll), ölü bölge ve ivme ayarı
- [ ] İki yönlü durum: köprü karoya renk/etiket/ikon güncellemesi yollar
- [ ] Aksiyon: medya (MPRIS / D-Bus), şu an çalan parçanın karoda gösterimi
- [ ] Aksiyon: ses seviyesi ve mikrofon mute (`wpctl`/`pactl`), mute durumunun karoda gösterimi
- [ ] Aksiyon: OBS (obs-websocket v5) ile sahne, kayıt/yayın, kaynak; aktif sahne ve REC durumu

## Deck D3: masaüstü ayar uygulaması (PySide6)
- [ ] Daemon ↔ uygulama yerel soket API'si (yapılandırmayı oku/yaz, bağlantı durumu, aksiyon kataloğu)
- [ ] PSP ekranı önizlemesi (4x3, tuş işaretleri) ve katman sekmeleri (Normal / L / R / L+R) + analog ataması
- [ ] Kategorili aksiyon seçici, eklentilerden otomatik doldurulan
- [ ] İkon, renk ve etiket seçimi; ikonları PSP'ye uygun boyuta dönüştürme
- [ ] "PSP bağlı" göstergesi, kaydedince canlı güncelleme
- [ ] `.desktop` dosyası ve uygulama menüsü girişi

## Deck D4: cila + teaser
- [ ] İmleçli ızgara modu (Select'e uzun basınca)
- [ ] Varsayılan ikon paketi ve örnek `deck.yaml` (yayıncı, geliştirici, müzik profilleri)
- [ ] `pspkit-bridge doctor` teşhis komutu
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
