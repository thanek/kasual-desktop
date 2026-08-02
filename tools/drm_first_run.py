"""Run the real Kasual Desktop first-run flow with Widevine pretended missing.

Usage:
    KD_CONFIG_DIR=/tmp/kd-drm-test python3 drm_first_run.py

Onboarding appears (fresh config dir), and because Netflix is offered with
``requires_cdm`` the setup checklist follows once you tick it and confirm.

The CDM is reported absent until the marker file below exists, so the wizard's
"Check again" loop can be driven for real: with the card open, run

    touch /tmp/kd-drm-test-cdm

in another terminal and press Check again — the steps tick, the state turns
READY and "Verify playback" becomes clickable against the actual module.

Re-running needs an empty config dir: rm -rf "$KD_CONFIG_DIR" first, or
onboarding is skipped because the catalog counts as provisioned.
"""

import os
import sys
from pathlib import Path

REPO = Path("/home/xis/projekty/kasual-desktop")
sys.path.insert(0, str(REPO / "src"))

MARKER = Path("/tmp/kd-drm-test-cdm")

if not os.environ.get("KD_CONFIG_DIR"):
    print("Refusing to run against your real config — set KD_CONFIG_DIR first.")
    raise SystemExit(2)

from infrastructure.linux.drm.facts import LinuxSystemFacts   # noqa: E402

_real_cdm_path = LinuxSystemFacts.cdm_path


def _pretend_cdm_path(self):
    return _real_cdm_path(self) if MARKER.exists() else None


LinuxSystemFacts.cdm_path = _pretend_cdm_path

import main   # noqa: E402

print(f"config dir : {os.environ['KD_CONFIG_DIR']}")
print(f"CDM marker : {MARKER} ({'present' if MARKER.exists() else 'absent'})")
main.main()
