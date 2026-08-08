#!/usr/bin/env python3
"""Spike — does this compositor hand out its window list over
wlr-foreign-toplevel-management, and with what app ids?

The one command to run on a new target (Raspberry Pi OS / labwc, wayfire, river)
before starting Kasual Desktop: it prints the globals the compositor advertises,
then every toplevel it reports, with the pid Kasual Desktop would resolve for it.

    python3 tools/spike_foreign_toplevel.py [seconds]

An app id printed with pid 0 is a window Kasual Desktop cannot attribute to a
process — the tile bar still shows it, but "minimize when leaving the app" will
not reach it. Watching for a few seconds also shows whether title and state
changes arrive at all.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PyQt6.QtCore import QCoreApplication, QTimer

from infrastructure.linux.wayland.client import WaylandClient, WaylandError
from infrastructure.linux.wayland.pid_lookup import AppIdPidResolver
from infrastructure.wlroots.wayland.foreign_toplevel import (
    MANAGER_INTERFACE, ForeignToplevelManager,
)

_DEFAULT_SECONDS = 5


def main() -> int:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_SECONDS
    app = QCoreApplication(sys.argv)

    try:
        client = WaylandClient()
    except WaylandError as exc:
        print(f"No Wayland connection: {exc}")
        return 1

    print("Globals advertised:")
    for interface, (name, version) in sorted(client.globals().items()):
        print(f"  {interface:<45} v{version} (name {name})")

    if not ForeignToplevelManager.available(client):
        print(f"\n{MANAGER_INTERFACE} is NOT offered — no window management here.")
        return 2

    pids = AppIdPidResolver()
    toplevels = ForeignToplevelManager(client)
    client.start()

    def report() -> None:
        snapshot = toplevels.snapshot()
        resolved = pids.resolve([t.app_id for t in snapshot])
        print(f"\n{len(snapshot)} toplevel(s):")
        for info in snapshot:
            flags = ",".join(flag for flag, on in (
                ("activated", info.activated), ("fullscreen", info.fullscreen),
                ("minimized", info.minimized), ("maximized", info.maximized),
            ) if on) or "-"
            print(f"  [{info.handle}] app_id={info.app_id!r} pid={resolved[info.app_id]} "
                  f"{flags}\n      title={info.title!r}")

    timer = QTimer()
    timer.timeout.connect(report)
    timer.start(1000)
    QTimer.singleShot(seconds * 1000, app.quit)
    app.exec()
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
