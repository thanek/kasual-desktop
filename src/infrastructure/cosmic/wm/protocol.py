"""Wire vocabulary of the toplevel protocols cosmic-comp implements.

Opcodes are positional in the protocol XML, so every constant below is the
declaration index of its request or event:

* ``ext-foreign-toplevel-list-v1`` (wayland-protocols staging) — the window list,
  with title, app_id and a session-stable identifier.
* ``cosmic-toplevel-info-unstable-v1`` — per-window state, reached by upgrading an
  ext handle to a cosmic one.
* ``cosmic-toplevel-management-unstable-v1`` — the control requests, of which
  cosmic-comp advertises close, activate, maximize, minimize and the moves to a
  workspace. Fullscreen is not among them; :mod:`.fullscreen` asks over X11 instead.
* ``ext-workspace-v1`` (wayland-protocols staging) — the workspaces a window can be
  moved to, grouped per output.
* ``wl_output`` — only for its connector name, which is what Qt calls a screen.
"""

from __future__ import annotations

import enum

FOREIGN_LIST = "ext_foreign_toplevel_list_v1"
FOREIGN_HANDLE = "ext_foreign_toplevel_handle_v1"
INFO = "zcosmic_toplevel_info_v1"
HANDLE = "zcosmic_toplevel_handle_v1"
MANAGER = "zcosmic_toplevel_manager_v1"
SEAT = "wl_seat"
OUTPUT = "wl_output"
WORKSPACES = "ext_workspace_manager_v1"

FOREIGN_LIST_VERSION = 1
INFO_VERSION = 3
MANAGER_VERSION = 4
OUTPUT_VERSION = 4
WORKSPACES_VERSION = 1

INFO_GET_COSMIC_TOPLEVEL = 1

MANAGER_CLOSE = 1
MANAGER_ACTIVATE = 2
MANAGER_SET_MINIMIZED = 5
MANAGER_UNSET_MINIMIZED = 6
MANAGER_MOVE_TO_EXT_WORKSPACE = 13

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

# zcosmic_toplevel_handle_v1 events. Only `state` and the outputs are read; the
# rest are named so the dispatch below reads as the protocol does.
HANDLE_EVENT_CLOSED = 0
HANDLE_EVENT_DONE = 1
HANDLE_EVENT_OUTPUT_ENTER = 4
HANDLE_EVENT_OUTPUT_LEAVE = 5
HANDLE_EVENT_STATE = 8

OUTPUT_EVENT_NAME = 4

WORKSPACES_EVENT_GROUP = 0
WORKSPACES_EVENT_WORKSPACE = 1

GROUP_EVENT_OUTPUT_ENTER = 1
GROUP_EVENT_OUTPUT_LEAVE = 2
GROUP_EVENT_WORKSPACE_ENTER = 3
GROUP_EVENT_WORKSPACE_LEAVE = 4
GROUP_EVENT_REMOVED = 5

WORKSPACE_EVENT_STATE = 3
WORKSPACE_EVENT_REMOVED = 5

WORKSPACE_STATE_ACTIVE = 1


class State(enum.IntEnum):
    MAXIMIZED = 0
    MINIMIZED = 1
    ACTIVATED = 2
    FULLSCREEN = 3
    STICKY = 4
