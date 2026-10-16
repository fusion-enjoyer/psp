TARGET = pspkit_deck
LIBPSPKIT = ../../libpspkit
OBJS = main.o $(LIBPSPKIT)/transport.o $(LIBPSPKIT)/link.o $(LIBPSPKIT)/gfx.o $(LIBPSPKIT)/stubs.o

INCDIR = $(LIBPSPKIT)
CFLAGS = -O2 -G0 -Wall
ASFLAGS = $(CFLAGS)
LIBS = -lpspusb -lpsppower -lpspdebug

BUILD_PRX = 1
EXTRA_TARGETS = EBOOT.PBP
PSP_EBOOT_TITLE = pspkit Deck
PSP_EBOOT_ICON = ICON0.PNG
PSP_EBOOT_PIC1 = PIC1.PNG
VERSION = 0.1.0

PSPLINKUSB = ../../../third_party/psplinkusb
DIST = dist/PSP/GAME/pspkit_deck

PSPSDK = $(shell psp-config --pspsdk-path)
include $(PSPSDK)/lib/build.mak

# Repack when the XMB images change (scripts/make_icons.py).
EBOOT.PBP: ICON0.PNG PIC1.PNG

# usbhostfs.prx ships next to the EBOOT, which loads it at startup.
$(PSPLINKUSB)/usbhostfs/usbhostfs.prx:
	$(MAKE) -C $(PSPLINKUSB)/usbhostfs PSP_FW_VERSION=271

dist: EBOOT.PBP $(PSPLINKUSB)/usbhostfs/usbhostfs.prx
	mkdir -p $(DIST)
	cp EBOOT.PBP $(PSPLINKUSB)/usbhostfs/usbhostfs.prx $(DIST)/
	@echo "Kopyala: dist/PSP -> PSP hafiza kartinin kokune"

# Hafiza kartinin kokune acilacak zip: PSP/GAME/pspkit_deck/...
release: dist
	rm -f pspkit-deck-$(VERSION).zip
	cd dist && zip -qr ../pspkit-deck-$(VERSION).zip PSP
	@echo "pspkit-deck-$(VERSION).zip hazir"

# Kablo olmadan test: PPSSPP (Flatpak) hafiza kartina kopyala ve calistir.
# tcp.cfg USB denemesini atlatir. Kopru: python3 -m pspkit (bridge/ icinde)
PPSSPP_MS ?= $(HOME)/.var/app/org.ppsspp.PPSSPP/config/ppsspp

ppsspp: dist
	mkdir -p $(PPSSPP_MS)/PSP/GAME
	cp -r $(DIST) $(PPSSPP_MS)/PSP/GAME/
	echo "127.0.0.1 10200" > $(PPSSPP_MS)/PSP/GAME/pspkit_deck/tcp.cfg
	flatpak run org.ppsspp.PPSSPP --windowed $(PPSSPP_MS)/PSP/GAME/pspkit_deck/EBOOT.PBP

clean-lib:
	rm -f $(LIBPSPKIT)/*.o

.PHONY: dist release ppsspp clean-lib
