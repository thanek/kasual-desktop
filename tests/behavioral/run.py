#!/usr/bin/env python3
"""Run the behavioral scenarios against a live Kasual Desktop session.

    python3 tests/behavioral/run.py            run them all, one after another
    python3 tests/behavioral/run.py kcd        run one
    python3 tests/behavioral/run.py --list     what there is, and what each one needs

Kasual Desktop has to be up first, with the test API on. Point it at a seeded
throwaway catalog so the tiles the scenarios need are there regardless of the
machine's own config:

    eval "$(python3 tests/behavioral/prepare_config.py --seed)"
    KD_TEST_API=1 ./kasual.sh

It waits there off screen — with no controller connected it shows nothing — until
the run creates its virtual pad, which is what brings it up.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT, REPO_ROOT / 'src'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tests.behavioral.harness import progress, requirements  # noqa: E402
from tests.behavioral.harness.session import Scenario  # noqa: E402


def _discover() -> dict[str, Scenario]:
    import tests.behavioral.scenarios as package

    found: dict[str, Scenario] = {}
    for module in pkgutil.iter_modules(package.__path__):
        loaded = importlib.import_module(f'{package.__name__}.{module.name}')
        scenario = getattr(loaded, 'SCENARIO', None)
        if scenario is not None:
            found[scenario.name] = scenario
    return dict(sorted(found.items()))


def _print_list(scenarios: dict[str, Scenario]) -> None:
    for scenario in scenarios.values():
        print(f'\n{scenario.name} — {scenario.title}')
        for requirement in requirements.BASE + scenario.requires:
            mark = ' ' if requirement.verify else '!'
            print(f'  [{mark}] {requirement.description}')
    print('\n  [!] cannot be verified by the harness — confirm it yourself.')


def _run_all(scenarios: dict[str, Scenario]) -> int:
    outcomes = {name: scenario.run() for name, scenario in scenarios.items()}
    print('\n' + '─' * 72)
    for name, code in outcomes.items():
        print(f'{"OK    " if code == 0 else "FAILED"}  {name}')
    return 0 if all(code == 0 for code in outcomes.values()) else 1


def main() -> int:
    scenarios = _discover()
    parser = argparse.ArgumentParser(
        description='Behavioral scenarios for Kasual Desktop, against the live Wayland '
                    'session (KDE, GNOME, Hyprland or Sway). With no arguments, runs '
                    'them all.')
    parser.add_argument('scenario', nargs='?', choices=sorted(scenarios),
                        help='run only this one')
    parser.add_argument('--list', action='store_true',
                        help='list the scenarios and what each one needs, and run nothing')
    parser.add_argument('--notify', action='store_true',
                        help='raise a desktop notification when a long wait begins, so a '
                             'watcher away from the terminal can decide to wait or abort')
    args = parser.parse_args()

    progress.configure(notify=args.notify)

    if args.list:
        _print_list(scenarios)
        return 0
    if args.scenario is not None:
        return scenarios[args.scenario].run()
    return _run_all(scenarios)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)   # the session's teardown still tore the game and Steam down
