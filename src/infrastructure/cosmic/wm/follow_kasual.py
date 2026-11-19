from __future__ import annotations

import logging

from collections.abc import Callable
from dataclasses import dataclass, field

from PyQt6.QtGui import QGuiApplication

from infrastructure.common.qt.ui.target_screen import target_screen
from infrastructure.cosmic.wm import protocol
from infrastructure.cosmic.wm.toplevels import CosmicToplevels, Toplevel
from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import WaylandClient

logger = logging.getLogger(__name__)


@dataclass
class _Group:
    outputs: set[int] = field(default_factory=set)
    workspaces: set[int] = field(default_factory=set)


class CosmicOutputsAndWorkspaces:
    def __init__(self, client: WaylandClient) -> None:
        self._client = client
        self._names: dict[int, str] = {}
        self._groups: dict[int, _Group] = {}
        self._active: set[int] = set()
        client.bind_all(protocol.OUTPUT, protocol.OUTPUT_VERSION,
                        lambda output: lambda op, rd: self._on_output_event(output, op, rd))
        client.bind(protocol.WORKSPACES, protocol.WORKSPACES_VERSION,
                    self._on_workspaces_event)

    @staticmethod
    def available(client: WaylandClient) -> bool:
        return client.has_global(protocol.WORKSPACES) and client.has_global(protocol.OUTPUT)

    def output_named(self, name: str) -> int | None:
        return next((output for output, named in self._names.items() if named == name),
                    None)

    def shown_workspace_on(self, output: int) -> int | None:
        for group in self._groups.values():
            if output in group.outputs:
                return next(iter(group.workspaces & self._active), None)
        return None

    def _on_output_event(self, output: int, opcode: int, reader: wire.Reader) -> None:
        if opcode == protocol.OUTPUT_EVENT_NAME:
            self._names[output] = reader.string()

    def _on_workspaces_event(self, opcode: int, reader: wire.Reader) -> None:
        if opcode == protocol.WORKSPACES_EVENT_GROUP:
            group = reader.new_id()
            self._groups[group] = _Group()
            self._client.set_handler(
                group, lambda op, rd: self._on_group_event(group, op, rd))
        elif opcode == protocol.WORKSPACES_EVENT_WORKSPACE:
            workspace = reader.new_id()
            self._client.set_handler(
                workspace, lambda op, rd: self._on_workspace_event(workspace, op, rd))

    def _on_group_event(self, group_id: int, opcode: int, reader: wire.Reader) -> None:
        group = self._groups.get(group_id)
        if group is None:
            return
        if opcode == protocol.GROUP_EVENT_OUTPUT_ENTER:
            group.outputs.add(reader.object_id())
        elif opcode == protocol.GROUP_EVENT_OUTPUT_LEAVE:
            group.outputs.discard(reader.object_id())
        elif opcode == protocol.GROUP_EVENT_WORKSPACE_ENTER:
            group.workspaces.add(reader.object_id())
        elif opcode == protocol.GROUP_EVENT_WORKSPACE_LEAVE:
            group.workspaces.discard(reader.object_id())
        elif opcode == protocol.GROUP_EVENT_REMOVED:
            del self._groups[group_id]
            self._client.forget(group_id)

    def _on_workspace_event(self, workspace: int, opcode: int, reader: wire.Reader) -> None:
        if opcode == protocol.WORKSPACE_EVENT_STATE:
            if reader.uint() & protocol.WORKSPACE_STATE_ACTIVE:
                self._active.add(workspace)
            else:
                self._active.discard(workspace)
        elif opcode == protocol.WORKSPACE_EVENT_REMOVED:
            self._active.discard(workspace)
            for group in self._groups.values():
                group.workspaces.discard(workspace)
            self._client.forget(workspace)


class CosmicWindowsFollowKasual:
    def __init__(self, client: WaylandClient, toplevels: CosmicToplevels,
                 paused: Callable[[], bool], own_app_id: str) -> None:
        self._toplevels = toplevels
        self._paused = paused
        self._own_app_id = own_app_id
        self._screens = CosmicOutputsAndWorkspaces(client)
        self._placed: set[str] = set()
        self._fullscreen: set[str] = set()
        client.roundtrip()
        self._open_before = {t.identifier for t in toplevels.toplevels()}
        logger.info("COSMIC: windows follow Kasual Desktop to its screen")

    def apply(self) -> None:
        toplevels = [t for t in self._toplevels.toplevels()
                     if t.identifier and t.app_id and t.outputs]
        for toplevel in toplevels:
            arrived = (toplevel.identifier not in self._placed
                       and toplevel.identifier not in self._open_before)
            self._open_before.discard(toplevel.identifier)
            went_fullscreen = (toplevel.fullscreen
                               and toplevel.identifier not in self._fullscreen)
            self._placed.add(toplevel.identifier)
            if toplevel.fullscreen:
                self._fullscreen.add(toplevel.identifier)
            else:
                self._fullscreen.discard(toplevel.identifier)
            if arrived or went_fullscreen:
                self._follow(toplevel)
        live = {t.identifier for t in self._toplevels.toplevels()}
        self._placed &= live
        self._fullscreen &= live
        self._open_before &= live

    def _follow(self, toplevel: Toplevel) -> None:
        if toplevel.app_id == self._own_app_id:
            return
        name = self._target_name()
        if name is None:
            return
        output = self._screens.output_named(name)
        if output is None or output in toplevel.outputs:
            return
        workspace = self._screens.shown_workspace_on(output)
        handle = self._toplevels.handle_for(toplevel.identifier)
        if workspace is None or handle is None:
            return
        logger.info("moving %r (%s) to %s, where Kasual Desktop is",
                    toplevel.title, toplevel.app_id, name)
        self._toplevels.move_to_workspace(handle, workspace, output)

    def _target_name(self) -> str | None:
        if self._paused() or len(QGuiApplication.screens()) < 2:
            return None
        screen = target_screen()
        return screen.name() if screen is not None else None
