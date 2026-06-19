# Build .deb / .rpm packages with nfpm.
#
#   make deb     # -> dist/kasual-desktop_<version>_all.deb
#   make rpm     # -> dist/kasual-desktop-<version>.noarch.rpm
#   make arch    # -> dist/kasual-desktop-<version>-1-any.pkg.tar.zst
#   make stage   # populate build/stage/ (what gets packaged)
#   make clean
#
# Version is the single source of truth from pyproject.toml.

# Version's source of truth is the git tag (e.g. v0.2.0 -> 0.2.0). Falls back to
# pyproject.toml when there's no tag / no git (tarball builds). CI overrides this
# explicitly with the release tag: `make VERSION=<tag> all`.
VERSION  ?= $(shell git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')
ifeq ($(strip $(VERSION)),)
VERSION  := $(shell grep -oP 'version\s*=\s*"\K[^"]+' pyproject.toml)
endif
STAGE    := build/stage
APPROOT  := $(STAGE)/usr/share/kasual-desktop

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
	rsync -a $(RSYNC_EXCLUDES) src apps sounds locale $(APPROOT)/
	printf '%s' "$(VERSION)" > $(APPROOT)/src/_version.txt
	find $(APPROOT) -type d -exec chmod 0755 {} +
	find $(APPROOT) -type f -exec chmod 0644 {} +
	install -Dm755 packaging/kasual-desktop          $(STAGE)/usr/bin/kasual-desktop
	install -Dm644 packaging/kasual-desktop.desktop  $(STAGE)/usr/share/applications/kasual-desktop.desktop
	install -Dm644 packaging/kasual-desktop.png      $(STAGE)/usr/share/icons/hicolor/256x256/apps/kasual-desktop.png
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
