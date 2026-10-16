# Gerçek PSP'de ilk deneme: kontrol listesi

Bu listeyi PSP ve USB kablosu yanındayken sırayla uygula. Her adımda ne görmen gerektiği yazıyor. Bir adım tutmazsa orada dur ve "Bana gönder" kısmındakileri ilet. Toplamda yaklaşık 15 dakika sürer.

## 0. Hazırlık (PC, bir kere)

**0.1** PSP'nin USB erişimi için udev kuralını kur. Bu adım sudo ister:

```bash
sudo cp ~/Desktop/psp/scripts/udev/60-pspkit-psp.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules
```

**0.2** Kurulumu kontrol et:

```bash
pspkit doctor
```

✅ Beklenen: sadece "PSP USB'de görünüyor" satırı hatalı. PSP henüz takılı olmadığı için bu normal.

**0.3** Hafıza kartına kopyalanacak zip'i hazırla:

```bash
cd ~/Desktop/psp && make release
```

✅ Beklenen: `psp/apps/deck/pspkit-deck-0.1.0.zip hazir`

## 1. PSP'ye kopyalama

**1.1** PSP'de XMB'den **Ayarlar → USB Bağlantısı**'nı aç ve kabloyu tak.

**1.2** Zip'i hafıza kartının köküne aç. Kartta `PSP/GAME/pspkit_deck/EBOOT.PBP` ve `usbhostfs.prx` oluşmalı.

**1.3** USB bağlantı modundan çık (○ ya da ✕). Kablo takılı kalabilir.

✅ Beklenen: **Oyun → Memory Stick** altında mavi/mor/kırmızı/yeşil karolu "pspkit Deck" ikonu.

## 2. İlk açılış

**2.1** "pspkit Deck"i aç.

✅ Beklenen: Siyah ekranda "pspkit Deck" yazısı ve altında birkaç log satırı:
- `usb: kuKernelLoadModule 0x...` (pozitif bir sayı)
- `usb: PC bekleniyor (15 sn)...`

Birkaç saniye içinde de kumanda şeklindeki karo ekranı gelmeli. Üst barda yeşil nokta ve `usb` yazmalı.

❌ Uygulama hiç açılmadan XMB'ye dönüyorsa: CFW'de KUBridge yok demektir. Bu durumda M0'ın plan B'sine geçeriz.
❌ `kuKernelLoadModule` satırı negatif bir değer gösteriyorsa: kodu not al.
❌ 15 saniye sonra `USB yok, TCP deneniyor` yazıyorsa: köprü PSP'yi göremedi, 3. adıma geç.

## 3. Bağlantı kurulmazsa

PC'de şunları çalıştır:

```bash
lsusb | grep 054c
```

```bash
pspkit status
```

```bash
journalctl --user -u pspkit-bridge -n 30 --no-pager
```

```bash
cat ~/.local/share/pspkit/usbhostfs_pc.log | tail -20
```

✅ Beklenen:
- `lsusb` çıktısında `054c:01c9`
- `pspkit status` çıktısında `usb  deck`

## 4. Tuşlar

| Dene | Beklenen |
|---|---|
| △ | Mikrofon kapanır, karo kırmızı yanar ve altında "KAPALI" yazar. Tekrar bas, açılır |
| ↑ / ↓ | Bilgisayarın sesi değişir, karoda yüzde güncellenir |
| ✕ | Terminal açılır (GNOME'da `ctrl+alt+t`) |
| □ | Tarayıcıda proje sayfası açılır |
| R basılı tut + → | "Yapıştır" (`ctrl+v`) |
| L basılı tut | Ekran OBS katmanına geçer. OBS kapalıysa bir tuşa basınca altta kırmızı "OBS'e bağlanılamadı" çıkar, bu normal |
| Analog çubuk yukarı/aşağı | Ses seviyesi değişir |
| R basılıyken analog | Sayfa kaydırılır |

✅ Üst barda `usb  N ms` görünür. Bu, tuşa basıştan köprünün cevabına kadar geçen süre. Hedef 100 ms'nin altı.

## 5. Ayar uygulaması

**5.1** Uygulamayı aç:

```bash
pspkit-deck
```

**5.2** Bir karoya tıkla, etiketini değiştir.

✅ PSP ekranı 1 saniye içinde güncellenir.

**5.3** "PSP ekran görüntüsü" butonuna bas.

✅ PSP ekranının görüntüsü açılır. Bu görüntü USB üzerinden geldi.

## 6. Kablo çek / tak

PSP açıkken kabloyu çek ve 5 saniye sonra geri tak.

✅ Altta kırmızı "Kopru baglantisi yok" yazar, sonra kendiliğinden düzelir.

## Bana gönder

- Hangi adıma kadar geldin, nerede takıldın
- `pspkit status` ve `pspkit doctor` çıktısı
- `journalctl --user -u pspkit-bridge -n 50 --no-pager` çıktısı
- PSP ekranının fotoğrafı ya da `pspkit shot` ile alınan görüntü
- Üst bardaki gecikme (ms)
- CFW adı ve sürümü (XMB → Ayarlar → Sistem Ayarları → Sistem Bilgisi)
