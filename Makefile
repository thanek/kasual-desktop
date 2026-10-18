# Build .deb / .rpm packages with nfpm.
#
#   make deb     # -> dist/kasual-desktop_<version>_all.deb
#   make rpm     # -> dist/kasual-desktop-<version>.noarch.rpm
#   make arch    # -> dist/kasual-desktop-<version>-1-any.pkg.tar.zst
#   make stage   # populate build/stage/ (what gets packaged)
#   make clean
#
# Version is derived from git tags; pyproject.toml is a fallback for tarball builds.

# Version from git tag (e.g. v0.2.0 -> 0.2.0) when HEAD is tagged (official release).
# When HEAD is not tagged (development), use full git describe (e.g. 0.1.0-74-g9b3d5f9).
# Falls back to pyproject.toml when there's no tag / no git (tarball builds).
# CI overrides explicitly: `make VERSION=<tag> all`.
TAG_AT_HEAD := $(shell git tag --points-at HEAD 2>/dev/null | head -1)
ifneq ($(strip $(TAG_AT_HEAD)),)
VERSION ?= $(shell git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')
else
VERSION ?= $(shell git describe --tags 2>/dev/null | sed 's/^v//')
endif
ifeq ($(strip $(VERSION)),)
VERSION := $(shell grep -oP 'version\s*=\s*"\K[^"]+' pyproject.toml)
endif
STAGE    := build/stage
APPROOT  := $(STAGE)/usr/share/kasual-desktop
EXT_UUID := kasual-helper@consoledesktop.org
EXTROOT  := $(STAGE)/usr/share/gnome-shell/extensions/$(EXT_UUID)

# What lands under /usr/share/kasual-desktop. Excludes test/dev cruft and the
# source .ts translations (only compiled .qm ship).
RSYNC_EXCLUDES := \
	--exclude='__pycache__' \
	--exclude='*.pyc' \
	--exclude='tests' \
	--exclude='tools' \
	--exclude='*.ts' \
	--exclude='.gitignore'

.PHONY: all deb rpm arch stage clean

all: deb rpm arch

stage:
	@echo "==> Staging kasual-desktop $(VERSION)"
	rm -rf $(STAGE)
	mkdir -p $(APPROOT)
	rsync -a $(RSYNC_EXCLUDES) src apps sounds locale fonts $(APPROOT)/
	cp pyproject.toml $(APPROOT)/
	printf '%s' "$(VERSION)" > $(APPROOT)/src/_version.txt
	find $(APPROOT) -type d -exec chmod 0755 {} +
	find $(APPROOT) -type f -exec chmod 0644 {} +
	install -Dm755 packaging/kasual-desktop          $(STAGE)/usr/bin/kasual-desktop
	install -Dm644 packaging/kasual-desktop.desktop  $(STAGE)/usr/share/applications/kasual-desktop.desktop
	install -Dm644 packaging/kasual-desktop.png      $(STAGE)/usr/share/icons/hicolor/256x256/apps/kasual-desktop.png
	# evdev gamepad access — vendor udev rule, reloaded at install by postinstall.sh.
	install -Dm644 packaging/99-kasual-desktop.rules $(STAGE)/usr/lib/udev/rules.d/99-kasual-desktop.rules
	# Keeps Steam off Sunshine's virtual-pad hidraw node, which bypasses the grab.
	install -Dm644 packaging/61-kasual-desktop-sunshine.rules $(STAGE)/usr/lib/udev/rules.d/61-kasual-desktop-sunshine.rules
	# GNOME Shell companion extension; inert on other compositors, and each user
	# still has to `gnome-extensions enable $(EXT_UUID)`.
	install -Dm644 packaging/gnome-extension/$(EXT_UUID)/metadata.json $(EXTROOT)/metadata.json
	install -Dm644 packaging/gnome-extension/$(EXT_UUID)/extension.js  $(EXTROOT)/extension.js
	chmod +x $(APPROOT)/apps/*/*.sh

deb: stage
	@mkdir -p dist
	KASUAL_VERSION=$(VERSION) nfpm pkg -f nfpm.yaml -p deb -t dist/

rpm: stage
	@mkdir -p dist
	KASUAL_VERSION=$(VERSION) nfpm pkg -f nfpm.yaml -p rpm -t dist/

arch: stage
	@mkdir -p dist
	KASUAL_VERSION=$(VERSION) nfpm pkg -f nfpm.yaml -p archlinux -t dist/

clean:
	rm -rf build dist
