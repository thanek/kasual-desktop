"""Wire vocabulary of the toplevel protocols cosmic-comp implements.

Opcodes are positional in the protocol XML, so the event tuples below must keep
their declaration order:

* ``ext-foreign-toplevel-list-v1`` (wayland-protocols staging) — the window list,
  with title, app_id and a session-stable identifier.
* ``cosmic-toplevel-info-unstable-v1`` — per-window state, reached by upgrading an
  ext handle to a cosmic one.
* ``cosmic-toplevel-management-unstable-v1`` — the control requests, of which
  cosmic-comp advertises close, activate, maximize, minimize and move_to_workspace.
  Fullscreen is deliberately not among them.
"""

from __future__ import annotations

import enum

from infrastructure.linux.wayland.client import Event, Interface

FOREIGN_LIST = "ext_foreign_toplevel_list_v1"
FOREIGN_HANDLE = "ext_foreign_toplevel_handle_v1"
INFO = "zcosmic_toplevel_info_v1"
HANDLE = "zcosmic_toplevel_handle_v1"
MANAGER = "zcosmic_toplevel_manager_v1"
SEAT = "wl_seat"

FOREIGN_LIST_VERSION = 1
INFO_VERSION = 3
MANAGER_VERSION = 4

INFO_GET_COSMIC_TOPLEVEL = 1

MANAGER_CLOSE = 1
MANAGER_ACTIVATE = 2
MANAGER_SET_MINIMIZED = 5
MANAGER_UNSET_MINIMIZED = 6

HANDLE_DESTROY = 0
FOREIGN_HANDLE_DESTROY = 0


class State(enum.IntEnum):
    MAXIMIZED = 0
    MINIMIZED = 1
    ACTIVATED = 2
    FULLSCREEN = 3
    STICKY = 4


INTERFACES = (
    Interface(FOREIGN_LIST, (
        Event("toplevel", "n", creates=FOREIGN_HANDLE),
        Event("finished"),
    )),
    Interface(FOREIGN_HANDLE, (
        Event("closed"),
        Event("done"),
        Event("title", "s"),
        Event("app_id", "s"),
        Event("identifier", "s"),
    )),
    Interface(INFO, (
        Event("toplevel", "n", creates=HANDLE),
        Event("finished"),
        Event("done"),
    )),
    Interface(HANDLE, (
        Event("closed"),
        Event("done"),
        Event("title", "s"),
        Event("app_id", "s"),
        Event("output_enter", "o"),
        Event("output_leave", "o"),
        Event("workspace_enter", "o"),
        Event("workspace_leave", "o"),
        Event("state", "a"),
        Event("geometry", "oiiii"),
        Event("ext_workspace_enter", "o"),
        Event("ext_workspace_leave", "o"),
    )),
    Interface(MANAGER, (
        Event("capabilities", "a"),
    )),
    Interface(SEAT, ()),
)
