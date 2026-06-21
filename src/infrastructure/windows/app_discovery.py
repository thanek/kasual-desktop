"""Discover installed apps by scanning the Start Menu — first-run onboarding source.

Walks the all-users and per-user Start Menu for ``.lnk`` shortcuts, resolves each
to its target (one batched PowerShell/WScript.Shell call — no pywin32), curates
out the noise (uninstallers, help/website links, duplicates by target), and builds
a short, screen-friendly list of :class:`CandidateApp` for the onboarding picker.

Each candidate's ``command`` is the ``.lnk`` path (WindowsAppManager launches it
via the shell) and its ``wm_class`` is the target's exe basename, so the resulting
tile matches its running window (reads as running, restores instead of duplicating).
"""

import base64
import logging
import os
import re
import subprocess
from pathlib import Path

from domain.catalog.app import App
from domain.catalog.game_heuristic import looks_like_game
from domain.provisioning.candidate import CandidateApp

logger = logging.getLogger(__name__)

# Shortcut display-names that are not apps.
_SKIP_NAME = re.compile(
    r"uninstall|deinstal|read\s*me|help|manual|documentation|\bdocs\b|website|"
    r"home\s*page|on the web|release notes|changelog|licen[cs]e|repair|modify|"
    r"report a|feedback|getting started|what's new|examples?",
    re.IGNORECASE,
)
# Target exe basenames that are installers/system noise, never app tiles.
_SKIP_TARGET = frozenset({
    "unins000", "uninstall", "setup", "install", "installer", "update", "updater",
    "rundll32", "regsvr32", "msiexec", "control", "cmd", "powershell",
})
# Start Menu subfolders that hold system/admin tools, not user apps.
_SKIP_FOLDER = re.compile(
    r"\\(Administrative Tools|System Tools|Accessibility|Windows PowerShell|"
    r"Windows Administrative Tools|Windows System)\\",
    re.IGNORECASE,
)

# Resolve every Start Menu shortcut's target in one PowerShell pass.
_PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$sh = New-Object -ComObject WScript.Shell
$dirs = @(
    (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs')
)
foreach ($d in $dirs) {
    if (Test-Path -LiteralPath $d) {
        Get-ChildItem -LiteralPath $d -Recurse -Filter *.lnk -File -ErrorAction SilentlyContinue | ForEach-Object {
            $t = ''
            try { $t = $sh.CreateShortcut($_.FullName).TargetPath } catch {}
            [Console]::Out.WriteLine($_.BaseName + "`t" + $_.FullName + "`t" + $t)
        }
    }
}
"""


def discover_candidates(limit: int | None = None) -> list[CandidateApp]:
    """Curated starter candidates discovered from the Start Menu (may be empty).

    All curated apps are listed (the onboarding picker scrolls); games / known
    gaming launchers are pre-selected and sorted first, then the rest by prominence
    (top-level shortcut first) and name. ``limit`` caps the count if given.
    """
    rows = _scan_start_menu()
    if not rows:
        logger.info("Start Menu scan found no shortcuts")
        return []

    by_target: dict[str, tuple[int, str, str]] = {}  # target_basename -> (depth, name, lnk)
    for name, lnk, target in rows:
        if _SKIP_NAME.search(name) or _SKIP_FOLDER.search(lnk):
            continue
        if not target.lower().endswith(".exe"):
            continue
        base = os.path.splitext(os.path.basename(target))[0].lower()
        if not base or base in _SKIP_TARGET:
            continue
        depth = _depth(lnk)
        prev = by_target.get(base)
        # Keep the shallowest (most prominent) shortcut for a given target.
        if prev is None or depth < prev[0]:
            by_target[base] = (depth, name, lnk)

    # Build apps, flag games, and order: games first, then prominence, then name.
    entries = [
        (App(name=name, command=lnk, wm_class=base), depth, base)
        for base, (depth, name, lnk) in by_target.items()
    ]
    entries.sort(key=lambda e: (not looks_like_game(e[0]), e[1], e[0].name.lower()))
    if limit is not None:
        entries = entries[:limit]

    candidates = [
        CandidateApp(
            key=_slug(app.name) or base,
            order=i,
            default_selected=looks_like_game(app),
            app=app,
        )
        for i, (app, _depth_, base) in enumerate(entries)
    ]
    n_games = sum(c.default_selected for c in candidates)
    logger.info("Discovered %d candidate app(s) from Start Menu (%d pre-selected as games)",
                len(candidates), n_games)
    return candidates


def _scan_start_menu() -> list[tuple[str, str, str]]:
    """Return (name, lnk_path, target_path) for every Start Menu shortcut."""
    encoded = base64.b64encode(_PS_SCRIPT.encode("utf-16-le")).decode("ascii")
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        logger.warning("Start Menu scan failed: %s", exc)
        return []
    out = proc.stdout.decode("utf-8", errors="replace")
    rows: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].strip():
            rows.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return rows


def _depth(lnk_path: str) -> int:
    """How deep under a 'Programs' folder the shortcut sits (top-level = 0)."""
    parts = Path(lnk_path).parts
    try:
        i = max(idx for idx, p in enumerate(parts) if p.lower() == "programs")
    except ValueError:
        return 99
    return len(parts) - i - 2  # parts after Programs, excluding the file itself


_SLUG_STRIP = re.compile(r"[^a-z0-9._-]+")


def _slug(text: str) -> str:
    return _SLUG_STRIP.sub("-", text.strip().lower()).strip("-")
