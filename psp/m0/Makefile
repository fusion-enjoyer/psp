TARGET = pspkit_m0
OBJS = main.o transport.o stubs.o

CFLAGS = -O2 -G0 -Wall
ASFLAGS = $(CFLAGS)
LIBS = -lpspusb

BUILD_PRX = 1
EXTRA_TARGETS = EBOOT.PBP
PSP_EBOOT_TITLE = pspkit M0 USB test

PSPLINKUSB = ../../third_party/psplinkusb
DIST = dist/PSP/GAME/pspkit_m0

PSPSDK = $(shell psp-config --pspsdk-path)
include $(PSPSDK)/lib/build.mak

# usbhostfs.prx is built from the pinned psplinkusb submodule and shipped
# next to the EBOOT, which loads it at startup.
$(PSPLINKUSB)/usbhostfs/usbhostfs.prx:
	$(MAKE) -C $(PSPLINKUSB)/usbhostfs PSP_FW_VERSION=271

dist: EBOOT.PBP $(PSPLINKUSB)/usbhostfs/usbhostfs.prx
	mkdir -p $(DIST)
	cp EBOOT.PBP $(PSPLINKUSB)/usbhostfs/usbhostfs.prx $(DIST)/
	@echo "Kopyala: dist/PSP -> PSP hafiza kartinin kokune"

.PHONY: dist

# Kablo olmadan test: PPSSPP (Flatpak) hafiza kartina kopyala ve calistir.
# Flatpak PPSSPP ev dizinini salt-okunur gordugu icin EBOOT kendi
# hafiza kartinda olmali. Kopru: python3 tools/m0/echo.py --listen
PPSSPP_MS ?= $(HOME)/.var/app/org.ppsspp.PPSSPP/config/ppsspp

ppsspp: dist
	mkdir -p $(PPSSPP_MS)/PSP/GAME
	cp -r $(DIST) $(PPSSPP_MS)/PSP/GAME/
	flatpak run org.ppsspp.PPSSPP --windowed $(PPSSPP_MS)/PSP/GAME/pspkit_m0/EBOOT.PBP

.PHONY: ppsspp
