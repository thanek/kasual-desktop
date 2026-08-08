"""freedesktop notification source — observes `Notify` calls on the bus.

Implements the domain `NotificationSource` port over the freedesktop notification
protocol, so it works under any DE running a notification daemon (Plasma, GNOME,
…). A notification arrives as a `Notify` *method call* to
`org.freedesktop.Notifications` (the service the active daemon owns); there is no
"new notification" signal to connect to, and a second process cannot own that
service. So to observe them passively we monitor the session bus.

PyQt6's `QtDBus` has no clean API for receiving monitored method calls, so the
plumbing here reads `dbus-monitor` from a background thread (its stdout, parsed
by the pure `parse_notify_blocks` in this module) and hops each notification onto
the GUI thread via a `pyqtSignal` — the same thread + signal-hop pattern the
`GamepadWatcher` uses for evdev. Reading the subprocess off a dedicated thread
(rather than spawning it via `QProcess` on the GUI thread) keeps the process
launch off the Wayland event loop entirely.

Limitation: this captures notifications from when Kasual starts onward — Plasma's
persisted history is not read (Plasma 6 does not expose it cleanly over D-Bus).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from domain.notifications.notification import Notification
from domain.notifications.source import NotificationSource
from domain.shared.event_emitter import EventEmitter, Unsubscribe
from infrastructure.common.qt._meta import ProtocolQtMeta

logger = logging.getLogger(__name__)


# Watch only the notification deliveries on the session bus.
_MATCH = "interface='org.freedesktop.Notifications',member='Notify'"

# dbus-monitor prints one message per block; a block starts at one of these
# (non-indented) header lines and runs until the next header. Note the SPACES:
# dbus-monitor writes "method call" / "method return", not underscores.
_HEADERS = ("method call", "method return", "signal", "error")
_NOTIFY_HEADER = "method call"

# Defensive cap: a single notification block is tiny, so if the buffer ever
# grows past this without resolving, something is wrong — drop it rather than
# let _on_output re-parse an ever-growing string on the GUI thread.
_MAX_BUFFER = 256 * 1024


@dataclass(frozen=True)
class _NotifyArgs:
    """The fields we lift out of a `Notify` method call."""

    app_name: str
    app_icon: str
    summary:  str
    body:     str


def _unquote(token: str) -> str:
    """Extract the text of a dbus-monitor ``string "..."`` token."""
    i = token.find('"')
    j = token.rfind('"')
    return token[i + 1:j] if i != -1 and j > i else ""


# The `Notify` signature is ``(s u s s s as a{sv} i)``: app_name, replaces_id,
# app_icon, summary, body, actions, hints, expire_timeout — exactly 8 top-level
# args, of which 6 are scalars (the two arrays contribute none at depth 0). So a
# block is fully streamed once its 6th depth-0 scalar (the trailing int32) lands.
_NOTIFY_SCALAR_COUNT = 6


def _top_level_scalars(arg_lines: list[str]) -> list[str]:
    """Collect the *top-level* (depth 0) scalar values of a `Notify` block, in
    order — arrays/dicts (actions, hints) are skipped by depth tracking, so their
    nested strings never pollute the positions."""
    depth = 0
    scalars: list[str] = []
    for raw in arg_lines:
        s = raw.strip()
        if not s:
            continue
        if s in ("]", ")"):
            depth -= 1
            continue
        opens = s.endswith("[") or s.endswith("(")   # 'array [' or 'dict entry('
        if depth == 0 and not opens:
            scalars.append(s)
        if opens:
            depth += 1
    return scalars


def _parse_notify_args(arg_lines: list[str]) -> _NotifyArgs | None:
    """Pull (app_name, app_icon, summary, body) from the arg lines of a `Notify`
    block — app_name at 0, app_icon at 2, summary at 3, body at 4."""
    scalars = _top_level_scalars(arg_lines)
    if len(scalars) < 5:
        return None
    return _NotifyArgs(
        app_name=_unquote(scalars[0]),
        app_icon=_unquote(scalars[2]),
        summary=_unquote(scalars[3]),
        body=_unquote(scalars[4]),
    )


def _is_complete_notify(arg_lines: list[str]) -> bool:
    """Whether a `Notify` block has fully streamed — its trailing (6th) top-level
    scalar has arrived — so it can be emitted without waiting for the next
    D-Bus message to prove it complete."""
    return len(_top_level_scalars(arg_lines)) >= _NOTIFY_SCALAR_COUNT


def parse_notify_blocks(text: str) -> tuple[list[_NotifyArgs], str]:
    """Parse complete `Notify` blocks from streamed dbus-monitor output.

    Returns the notifications found plus the unparsed tail to prepend to the
    next chunk. A block followed by another header is proven complete by that
    header; the trailing block has no follower yet, so it's only emitted once
    it has structurally streamed in full (see :func:`_is_complete_notify`) —
    otherwise a lone final notification would sit in the buffer forever.
    """
    lines = text.split("\n")
    header_idxs = [
        i for i, l in enumerate(lines)
        if l[:1] not in (" ", "\t") and l.startswith(_HEADERS)
    ]
    if not header_idxs:
        return [], text

    def notify_args(start: int, end: int) -> _NotifyArgs | None:
        header = lines[start]
        if not (header.startswith(_NOTIFY_HEADER) and "member=Notify" in header):
            return None
        return _parse_notify_args(lines[start + 1:end])

    results: list[_NotifyArgs] = []
    for k in range(len(header_idxs) - 1):
        parsed = notify_args(header_idxs[k], header_idxs[k + 1])
        if parsed is not None:
            results.append(parsed)

    last = header_idxs[-1]
    tail = lines[last + 1:]
    header = lines[last]
    is_notify = header.startswith(_NOTIFY_HEADER) and "member=Notify" in header
    if is_notify and _is_complete_notify(tail):
        parsed = _parse_notify_args(tail)
        if parsed is not None:
            results.append(parsed)
        return results, ""

    leftover = "\n".join(lines[last:])
    return results, leftover


class FreedesktopNotificationMonitor(QObject, NotificationSource, metaclass=ProtocolQtMeta):
    """Observes freedesktop notifications via ``dbus-monitor`` and republishes
    them as domain :class:`Notification`s through the `NotificationSource` port.

    A background thread reads the subprocess; each parsed notification is handed
    to the GUI thread through ``_notify_hop`` (a queued cross-thread signal), so
    the `EventEmitter` (and the NotificationCenter behind it) is only ever
    touched on the GUI thread — exactly the GamepadWatcher contract."""

    # Carries a Notification from the reader thread onto the GUI thread (queued).
    _notify_hop = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._emitter: EventEmitter[Notification] = EventEmitter()
        # Connect to a bound method of *this* QObject (PyQt can't weak-ref the
        # slotted EventEmitter directly); the hop then forwards to the emitter.
        self._notify_hop.connect(self._deliver)
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._running = False
        self._seen_any = False

    # ── NotificationSource port ──────────────────────────────────────────────

    def on_notification(
        self, handler: Callable[[Notification], None]
    ) -> Unsubscribe:
        return self._emitter.subscribe(handler)

    def _deliver(self, notification: Notification) -> None:
        """GUI-thread slot for the hop signal: fan out to subscribers."""
        self._emitter.emit(notification)

    # ── Lifecycle (driven by the composition root) ───────────────────────────

    def start(self) -> None:
        """Begin monitoring the session bus for incoming notifications."""
        if self._running:
            return
        if shutil.which("dbus-monitor") is None:
            logger.warning("dbus-monitor not found; notifications disabled")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="notif-monitor"
        )
        self._thread.start()
        logger.info("Notification monitor started")

    def stop(self) -> None:
        """Stop monitoring (app teardown)."""
        self._running = False
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception as exc:
                logger.debug("Terminating the notification monitor failed: %s", exc)
            self._proc = None

    # ── Reader thread ────────────────────────────────────────────────────────

    def _run(self) -> None:
        exe = shutil.which("dbus-monitor")
        try:
            self._proc = subprocess.Popen(
                [exe, "--session", _MATCH],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1,
            )
        except Exception as exc:
            logger.warning("Could not start dbus-monitor: %s", exc)
            return

        buffer = ""
        for line in self._proc.stdout:        # blocks until a line or EOF
            if not self._running:
                break
            buffer += line
            found, buffer = parse_notify_blocks(buffer)
            if len(buffer) > _MAX_BUFFER:
                logger.warning("Notification buffer overflow; dropping")
                buffer = ""
            for args in found:
                if not self._seen_any:
                    self._seen_any = True
                    logger.info("Receiving notifications (first from: %s)", args.app_name)
                self._notify_hop.emit(
                    Notification(
                        app_name=args.app_name or "?",
                        summary=args.summary,
                        body=args.body,
                        # freedesktop app_icon hint (theme name or path); the
                        # overlay resolves it to a QIcon, falling back to app_name.
                        icon=args.app_icon or None,
                        timestamp=datetime.now(),
                    )
                )
