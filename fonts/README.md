# Bundled fonts

Genuine **Font Awesome 5 Free** (5.15.4) webfonts plus the matching qtawesome
charmaps, vendored from the upstream [`qtawesome`](https://github.com/spyder-ide/qtawesome)
wheel.

They are bundled (and re-registered at runtime — see `infrastructure/qt/icons.py`
and `apps/file_browser/src/fa_icons.py`) because Debian/Ubuntu's
`python3-qtawesome` (`+dfsg`) substitutes *Fork Awesome* (a Font Awesome 4.7
fork) for the FA5 webfonts while keeping the FA5 charmap, which makes FA5-only
glyphs render as unrelated fallback characters.

## Licenses

- **Font Awesome 5 Free** fonts (`*.ttf`): [SIL OFL 1.1](https://scripts.sil.org/OFL) —
  © Fonticons, Inc. <https://fontawesome.com>
- **Charmaps** (`*-charmap-*.json`): MIT, from qtawesome.
