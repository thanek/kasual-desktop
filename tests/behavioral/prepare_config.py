#!/usr/bin/env python3
"""Materialise a throwaway config directory and print its KD_CONFIG_DIR export.

    eval "$(python3 tests/behavioral/prepare_config.py --seed)"
    KD_TEST_API=1 ./kasual.sh

    --seed    a provisioned catalog holding just the tiles the scenarios touch
    --empty   an unprovisioned directory (no marker) — for the onboarding flow
    --dir P   use P instead of a fresh temp directory

Only the ``export`` line goes to stdout, so the eval above is safe; everything
else is on stderr.
"""

from __future__ import annotations

import argparse
import shlex
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT, REPO_ROOT / 'src'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from domain.catalog.app import App  # noqa: E402
from domain.input.vocabulary import Trigger  # noqa: E402
from domain.provisioning.candidate import CandidateApp  # noqa: E402
from domain.provisioning.catalog import starter_candidates  # noqa: E402
from domain.provisioning.ports import AppDiscovery  # noqa: E402


class _SeedDiscovery(AppDiscovery):
    """Reports Steam present and every icon absent, so the seed never varies with
    the machine it runs on."""

    def is_available(self, command: str) -> bool:
        return command == 'steam'

    def system_icon(self, names: tuple[str, ...]) -> str | None:
        return None

    def extra_candidates(self) -> list[CandidateApp]:
        return []


def _kingdom_come() -> CandidateApp:
    return CandidateApp(
        key='Kingdom Come Deliverance',
        app=App(
            name='Kingdom Come: Deliverance',
            command='steam',
            args=('steam://rungameid/379430',),
            icon_theme='steam',
            color='#155E75',
            recall_menu_trigger=Trigger.HOLD_1S,
            env={'MANGOHUD': '1'},
            categories=('Game',),
        ),
        order=20,
        default_selected=True,
    )


def _seed_candidates() -> list[CandidateApp]:
    candidates = starter_candidates(_SeedDiscovery(), str(REPO_ROOT))
    candidates.append(_kingdom_come())
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--seed', action='store_const', const='seed', dest='mode')
    mode.add_argument('--empty', action='store_const', const='empty', dest='mode')
    parser.add_argument('--dir')
    parser.set_defaults(mode='seed')
    args = parser.parse_args()

    target = Path(args.dir) if args.dir else Path(tempfile.mkdtemp(prefix='kasual-config-'))
    target.mkdir(parents=True, exist_ok=True)

    import os
    os.environ['KD_CONFIG_DIR'] = str(target)

    if args.mode == 'seed':
        from infrastructure.common.catalog.app_config import DesktopAppProvisioning
        DesktopAppProvisioning().provision(_seed_candidates())
        print(f'seeded {target} with the scenario tiles', file=sys.stderr)
    else:
        print(f'empty {target} — first launch will run onboarding', file=sys.stderr)

    print(f'export KD_CONFIG_DIR={shlex.quote(str(target))}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
