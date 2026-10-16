# pspkit: kök Makefile. PSP tarafı pspdev ister (docs/m0.md), PC tarafı sadece python3.
PSPDEV ?= $(HOME)/pspdev
export PSPDEV
export PATH := $(PSPDEV)/bin:$(PATH)

all: deck

deck:            ## PSP Deck uygulamasını derle -> psp/apps/deck/dist/PSP
	$(MAKE) -C psp/apps/deck dist

release:         ## hafıza kartına açılacak zip -> psp/apps/deck/pspkit-deck-*.zip
	$(MAKE) -C psp/apps/deck release

ppsspp:          ## Deck'i PPSSPP'de aç (köprü çalışıyor olmalı)
	$(MAKE) -C psp/apps/deck ppsspp

test:            ## köprü testleri
	cd bridge && python3 -m unittest discover -s tests -t .

install:         ## PC tarafını kur (köprü servisi + ayar uygulaması)
	scripts/install.sh

clean:
	$(MAKE) -C psp/apps/deck clean clean-lib
	$(MAKE) -C psp/m0 clean

.PHONY: all deck release ppsspp test install clean
