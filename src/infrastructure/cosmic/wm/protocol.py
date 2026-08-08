"""Wire vocabulary of the toplevel protocols cosmic-comp implements.

Opcodes are positional in the protocol XML, so every constant below is the
declaration index of its request or event:

* ``ext-foreign-toplevel-list-v1`` (wayland-protocols staging) — the window list,
  with title, app_id and a session-stable identifier.
* ``cosmic-toplevel-info-unstable-v1`` — per-window state, reached by upgrading an
  ext handle to a cosmic one.
* ``cosmic-toplevel-management-unstable-v1`` — the control requests, of which
  cosmic-comp advertises close, activate, maximize, minimize and move_to_workspace.
  Fullscreen is not among them; :mod:`.fullscreen` asks over X11 instead.
"""

from __future__ import annotations

import enum

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

# ext_foreign_toplevel_list_v1 events
LIST_EVENT_TOPLEVEL = 0
LIST_EVENT_FINISHED = 1

# ext_foreign_toplevel_handle_v1 events
FOREIGN_EVENT_CLOSED = 0
FOREIGN_EVENT_DONE = 1
FOREIGN_EVENT_TITLE = 2
FOREIGN_EVENT_APP_ID = 3
FOREIGN_EVENT_IDENTIFIER = 4

# zcosmic_toplevel_handle_v1 events. Only `state` is read; the rest are named so
# the dispatch below reads as the protocol does.
HANDLE_EVENT_CLOSED = 0
HANDLE_EVENT_DONE = 1
HANDLE_EVENT_STATE = 8


class State(enum.IntEnum):
    MAXIMIZED = 0
    MINIMIZED = 1
    ACTIVATED = 2
    FULLSCREEN = 3
    STICKY = 4
