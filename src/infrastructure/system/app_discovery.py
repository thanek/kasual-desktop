"""Detect which system apps are installed — the :class:`AppDiscovery` adapter.

Backs the provisioning catalog's availability filtering. ``shutil.which`` is
enough for the system starter apps (Steam, Heroic) which ship CLI launchers on
``PATH``. A later enhancement could also scan the XDG ``applications`` dirs (as
``window_icons._xdg_app_dirs`` does) for ``.desktop`` matches.
"""

import shutil

from domain.provisioning.ports import AppDiscovery


class WhichAppDiscovery(AppDiscovery):
    def is_available(self, command: str) -> bool:
        return shutil.which(command) is not None
