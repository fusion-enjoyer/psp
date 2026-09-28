# pspkit: kök Makefile. PSP tarafı pspdev ister (docs/m0.md), PC tarafı sadece python3.
PSPDEV ?= $(HOME)/pspdev
export PSPDEV
export PATH := $(PSPDEV)/bin:$(PATH)

all: deck

deck:            ## PSP Deck uygulamasını derle -> psp/apps/deck/dist/PSP
	$(MAKE) -C psp/apps/deck dist

ppsspp:          ## Deck'i PPSSPP'de aç (köprü çalışıyor olmalı)
	$(MAKE) -C psp/apps/deck ppsspp

test:            ## köprü testleri
	cd bridge && python3 -m unittest discover -s tests -t .

install:         ## PC tarafını kur (köprü servisi + ayar uygulaması)
	scripts/install.sh

clean:
	$(MAKE) -C psp/apps/deck clean clean-lib
	$(MAKE) -C psp/m0 clean

.PHONY: all deck ppsspp test install clean
