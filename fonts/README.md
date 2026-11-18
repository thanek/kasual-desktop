# Bundled fonts

Genuine **Font Awesome 5 Free** (5.15.4) webfonts plus the matching qtawesome
charmaps, vendored from the upstream [`qtawesome`](https://github.com/spyder-ide/qtawesome)
wheel.

They are bundled (and installed at runtime as qtawesome's font set — see
`src/infrastructure/common/qt/icons.py` and `apps/file_browser/src/fa_icons.py`)
because distro packages of qtawesome break the FA5 fonts:

- Debian/Ubuntu's `python3-qtawesome` (`+dfsg`) substitutes *Fork Awesome* (a
  Font Awesome 4.7 fork) for the FA5 webfonts while keeping the FA5 charmap,
  which makes FA5-only glyphs render as unrelated fallback characters.
- Fedora's `python3-QtAwesome` symlinks the FA5/FA6 fonts to
  `/usr/share/fontawesome/webfonts/*.ttf`, which `fontawesome-fonts-web` no
  longer ships, so qtawesome crashes loading its own font set. Unreadable
  qtawesome fonts are skipped, which leaves the `fa6*` prefixes unavailable there.

## Licenses

- **Font Awesome 5 Free** fonts (`*.ttf`): [SIL OFL 1.1](https://scripts.sil.org/OFL) —
  © Fonticons, Inc. <https://fontawesome.com>
- **Charmaps** (`*-charmap-*.json`): MIT, from qtawesome.
