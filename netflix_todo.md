# Netflix app — road to shipping in a KD release

Status: working proof of concept on `netflix` branch (verified 2026-08-01 on
Fedora 44 aarch64, VM on Apple Silicon M1: login + DRM playback both work).
This file lists what stands between the PoC and a distributable feature.

## Packaging

- [ ] Nothing structural: `make stage` rsyncs the whole `apps/` tree and
      `chmod +x`'s `apps/*/*.sh`, so `apps/netflix/` ships in deb/rpm/arch
      with zero packaging changes.
- [ ] No new hard dependencies: netflix.py uses the same stack as yt.py
      (PyQt6 WebEngine + evdev), already in `depends` for all three formats.
- [ ] Update `nfpm.yaml` `description` — it currently says "Bundles the File
      Browser and YouTube couch apps".
- [ ] Consider `recommends` (rpm) / `suggests` (deb) for the CDM providers
      (`widevine-installer` on Fedora, `google-chrome-stable` elsewhere).
      Note: nfpm drops these fields for arch packages anyway (see the
      `brightnessctl` comment in nfpm.yaml).

## Widevine CDM (the real distribution problem)

The CDM is a proprietary Google blob with no redistribution rights — it can
never be inside the package nor be a hard dependency. It must remain a
**runtime-detected** component (already implemented: `_find_cdm()` + an
instruction page when missing). Acquisition differs per platform:

| Platform | How the user gets the CDM |
|---|---|
| Fedora aarch64 (incl. Asahi) | `dnf install widevine-installer && sudo widevine-installer` |
| Other distros aarch64 | widevine-installer script from GitHub (needs glibc ≥ 2.36; 16K page size on Apple Silicon is handled by Asahi, elsewhere varies) |
| x86_64 any distro | install Google Chrome (CDM lands in `/opt/google/chrome`) or copy from a Chrome profile |
| Windows | Qt WebEngine auto-detects Chrome's CDM — Chrome must be installed |

- [ ] Document the per-platform setup steps in the README.

## DRM setup wizard (reusable beyond Netflix)

Idea: a KD-guided wizard that prepares the system for Widevine-based apps.
Any future DRM streaming app (Canal+, HBO Max, …) has the same prerequisite,
so this should be a shared "DRM readiness" flow, not a Netflix feature:

- [ ] Detect: arch (x86_64 vs aarch64), distro, CDM present/absent
      (reuse/extract `_find_cdm()` into shared code instead of a per-app copy).
- [ ] Guide: show the right acquisition path for the detected platform;
      where a privileged install step is needed (`sudo widevine-installer`),
      display the command rather than running it.
- [ ] Verify: after install, re-detect and confirm EME
      (`com.widevine.alpha`) actually resolves in a QtWebEngine probe.
- [ ] Legal note in the wizard: the user downloads Google's blob themselves
      and accepts its license — KD only points the way.

## Starter catalog registration

- [ ] Netflix is deliberately NOT in `src/domain/provisioning/catalog.py`
      yet. When registering, gate the candidate on CDM presence (analogous
      to `discovery.is_available("steam")`) — or offer it always and route
      the no-CDM case into the wizard above, which is the nicer UX.
- [ ] Add `"netflix.sh": "kasual-netflix"` to `BUNDLED_WM_CLASS`.

## Known open problems (app itself)

- [ ] **UA tradeoff / re-login on aarch64**: login (reCAPTCHA Enterprise)
      only passes with a Firefox UA, but playback with the ChromeOS-extracted
      arm64 CDM requires a CrOS UA (else license server returns E100). The
      code picks the playback UA, so re-login on aarch64 will likely fail.
      Mitigations: per-phase UA switching (Firefox on /login, CrOS after),
      or the `KASUAL_NETFLIX_UA` env override as a manual escape hatch.
- [ ] **720p cap**: Widevine L3 (software) — inherent, document it, don't
      chase it.
- [ ] **Gamepad untested**: PadListener maps A/B/D-pad but no controller was
      available during the PoC. Verify spatial navigation actually walks the
      desktop site's tiles.
- [ ] **Play/pause mapping**: needs KEY_SPACE, which means touching all
      identical `keyinput.py` copies (yt, file_browser, netflix) — repo
      convention keeps them byte-identical.
- [ ] **x86_64 path untested**: Firefox UA + Chrome CDM should be the simple
      case, but it has never actually run. Test before calling this
      distributable.
- [ ] **Windows path untested**: relies on Qt auto-detecting Chrome's CDM;
      completely unverified.

## Codec caveat

Qt WebEngine codec support varies per distro build. Fedora 44 aarch64 was
verified empirically (H.264/AAC/VP9/AV1 in canPlayType + MSE); Debian and
Arch link full ffmpeg so they should be fine — but this is exactly the area
`nfpm.yaml` already flags ("verify on a real target"). Test H.264 playback
on a real Debian before publishing the .deb.
