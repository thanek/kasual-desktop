# Kasual Desktop Pad (Firefox extension, proof of concept)

Gamepad navigation for streaming services opened by Kasual Desktop in a Firefox kiosk window. Only Netflix is supported so far.

The extension reads the pad through the Gamepad API inside the page, so a page sees the pad only after the first button press. Netflix is a single-page app, so this matters only after a full page load.

## Controls

Intents carry the same names as the Kasual Desktop input vocabulary (`src/domain/input/vocabulary.py`), so the buttons keep their meaning across the system.

| Pad | Browsing | Watching | Player controls |
|---|---|---|---|
| D-pad / left stick | move focus | ←/→ seek 10 s, ↑/↓ show controls | move focus |
| A | activate | play / pause | activate |
| B | close dialog, go back | leave player | hide controls |
| X | search (opens the on-screen keyboard) | – | – |
| Y | – | skip intro / recap, next episode | skip intro / recap, next episode |
| LB / RB | previous / next page of the row | seek 30 s | – |
| LT / RT | previous / next section (navigation bar, billboard, each carousel) | volume | volume |

The on-screen keyboard also opens when A is pressed on a text field. On it: A types the selected key, X deletes, Y adds a space, LT switches to Polish letters (a→ą, z→ż, x→ź…), B closes it.

A hint bar styled after the Kasual Desktop one shows the buttons available on the current screen. While watching, it hides after a few seconds without input. Labels come from `_locales/`.

Navigation plays the Kasual Desktop feedback cues. `make firefox-extension` copies them from the repository's `sounds/` (Firefox does not serve symlinks leading out of an extension). The background script plays them, which keeps them clear of the page's CSP and autoplay policy.

For the 8BitDo Ultimate, Firefox on Linux reports the top face button (Y) as standard index 2 and the left one (X) as 3, the reverse of the W3C layout. The extension follows what Firefox reports: index 2 is Actions (Y), index 3 is Close (X).

F9 on a keyboard toggles a diagnostics panel with the pad id, mapping, pressed button indices, axes and the resulting intents.

## Loading during development

1. Copy the feedback cues once: `make firefox-extension`.
2. Start the kiosk profile without `--kiosk`:
   `firefox --no-remote --profile ~/.cache/kd-vod-test https://www.netflix.com`
3. Open `about:debugging#/runtime/this-firefox`, choose "Load Temporary Add-on…" and pick `manifest.json`.
4. Go back to the Netflix tab and press F11.
5. After editing the code, press "Reload" next to the extension in `about:debugging` and reload the page.

A temporary add-on disappears when Firefox closes.

When Kasual Desktop is running, it grabs the physical pad and forwards it as `kasual-vpad`, but it also reacts to the pad in its own interface. Test either with Kasual Desktop closed or with Firefox launched from a Kasual Desktop tile.

## Permanent installation

`make stage` puts the extension, with its sounds, under `/usr/share/mozilla/extensions/{ec8030f7-c20a-464f-9b0e-13a3a9e97384}/`, the system scope of every Firefox profile. Fedora builds Firefox with unsigned add-ons allowed there; other distributions require the add-on to be signed through addons.mozilla.org (unlisted self-distribution).

Being system-wide, the extension also runs on Netflix in an ordinary Firefox window. It zooms the page to the 1920 px TV layout only while the window is fullscreen, and only for that tab.

The Netflix tile runs `apps/vod/vod.sh`, which keeps a dedicated profile in `~/.local/share/kasual-desktop/vod-profile`, rewrites its `user.js` (DRM, no first-run pages, sideloaded extensions enabled) and starts Firefox in kiosk mode with the `kasual-vod` window name.
