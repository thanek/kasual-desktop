"""Windows notification source — observes Action Center toasts via WinRT.

Implements the domain `NotificationSource` port on Windows, the counterpart of
KDE's `KdeNotificationMonitor`. There is no passive "new notification" signal a
plain Win32 process can rely on (the `UserNotificationListener.NotificationChanged`
event is unreliable for unpackaged apps), so we *poll* the listener: every few
seconds we read the current toast notifications and emit the ones we have not
seen before. Polling runs on a background thread (its own asyncio loop, since the
WinRT calls are async); each new notification is hopped onto the GUI thread via a
``pyqtSignal`` — the same thread + signal-hop contract the GamepadWatcher and the
KDE monitor use, so the `EventEmitter` (and the NotificationCenter behind it) is
only ever touched on the GUI thread.

Parity with KDE — *from start onward*: the Windows Action Center already holds a
backlog when Kasual launches. Emitting that backlog would flood the top-bar badge
with stale "unread" counts, so the **first** poll is treated as a priming pass:
its notifications seed the seen-set silently and only genuinely new arrivals after
that are published. This matches KDE, which likewise captures notifications from
when Kasual starts and cannot replay history.

Requires the WinRT projection packages (winrt-Windows.UI.Notifications[.Management],
winrt-Windows.ApplicationModel); they are imported lazily inside the poll loop so
this module stays importable (and its pure parsing helpers unit-testable) on hosts
without them.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from domain.notifications.notification import Notification
from domain.notifications.source import NotificationSource
from domain.shared.event_emitter import EventEmitter, Unsubscribe
from infrastructure.common.qt._meta import ProtocolQtMeta

logger = logging.getLogger(__name__)

# The generic toast binding name (KnownNotificationBindings.ToastGeneric is just
# this string); hardcoded so the parse path needs no WinRT import.
_TOAST_GENERIC = "ToastGeneric"

# How often to re-read the Action Center. A few seconds keeps the badge responsive
# without busy-polling a COM API; the recent-notifications panel is not real-time.
_POLL_SECONDS = 4.0


# ── Pure parsing / diff helpers (no Qt, no WinRT) ───────────────────────────────

def _app_name(un) -> str:
    """Display name of the app that posted the notification ("" if unavailable)."""
    try:
        return un.app_info.display_info.display_name or ""
    except Exception:
        return ""


def _text_elements(un) -> list[str]:
    """The toast's text lines, top to bottom (title first, then body lines)."""
    try:
        binding = un.notification.visual.get_binding(_TOAST_GENERIC)
        if binding is None:
            return []
        return [el.text for el in binding.get_text_elements()]
    except Exception:
        return []


def _creation_time(un) -> datetime:
    """When the notification was posted (PyWinRT maps DateTime → datetime).

    WinRT hands back a timezone-aware UTC datetime; the rest of the app (the
    overlay's ``datetime.now()``, the KDE source) speaks naive *local* time.
    Convert to naive local so the two are comparable — otherwise computing a
    relative age subtracts offset-aware from offset-naive and raises."""
    try:
        ct = un.creation_time
        if not isinstance(ct, datetime):
            return datetime.now()
        if ct.tzinfo is not None:
            ct = ct.astimezone().replace(tzinfo=None)
        return ct
    except Exception:
        return datetime.now()


def _to_notification(un) -> Notification | None:
    """Translate a WinRT ``UserNotification`` into the domain value object.

    Returns None only if it carries no usable text at all (e.g. a pure-image or
    progress toast) — there is nothing to show in the list for those.
    """
    texts = _text_elements(un)
    if not texts:
        return None
    return Notification(
        app_name=_app_name(un) or "?",
        summary=texts[0],
        body="\n".join(texts[1:]),
        # Windows toasts expose no portable icon path/URI; the overlay falls back
        # to the app name (as it does for icon-less freedesktop notifications).
        icon=None,
        timestamp=_creation_time(un),
    )


def partition_new(
    notes: Iterable, seen: set[int], primed: bool
) -> tuple[list, set[int], bool]:
    """Split a poll's notifications into (to-emit, new-seen-set, primed).

    The first poll (``primed`` False) emits nothing — its ids only seed the
    seen-set — so the pre-existing Action Center backlog never floods the badge.
    Subsequent polls emit any id not already seen. The returned seen-set is the
    *current* one (dropping ids no longer present, so a later re-post re-emits).
    """
    notes = list(notes)
    current = {un.id for un in notes}
    if not primed:
        return [], current, True
    fresh = [un for un in notes if un.id not in seen]
    return fresh, current, True


# ── The source adapter ──────────────────────────────────────────────────────────

class WindowsNotificationSource(QObject, NotificationSource, metaclass=ProtocolQtMeta):
    """Polls the Windows Action Center and republishes new toasts as domain
    :class:`Notification`s through the `NotificationSource` port.

    A daemon thread runs an asyncio loop over the async WinRT calls; each new
    notification is delivered to the GUI thread through ``_notify_hop`` (a queued
    cross-thread signal) before reaching the `EventEmitter`."""

    # Carries a Notification from the poll thread onto the GUI thread (queued).
    _notify_hop = pyqtSignal(object)

    def __init__(self, poll_seconds: float = _POLL_SECONDS,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._emitter: EventEmitter[Notification] = EventEmitter()
        # Connect to a bound method of *this* QObject (PyQt can't weak-ref the
        # slotted EventEmitter directly); the hop then forwards to the emitter.
        self._notify_hop.connect(self._deliver)
        self._thread: threading.Thread | None = None
        self._running = False
        self._poll_seconds = poll_seconds
        self._seen: set[int] = set()
        self._primed = False

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
        """Begin polling the Action Center for incoming notifications."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="notif-listener"
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop polling (app teardown). The daemon thread unwinds on its next tick."""
        self._running = False

    # ── Poll thread ──────────────────────────────────────────────────────────

    def _run(self) -> None:
        import asyncio
        try:
            asyncio.run(self._poll_loop())
        except Exception as exc:  # pragma: no cover - defensive thread guard
            logger.warning("Notification listener stopped: %s", exc)

    async def _poll_loop(self) -> None:
        import asyncio
        try:
            from winrt.windows.ui.notifications import NotificationKinds
            from winrt.windows.ui.notifications.management import (
                UserNotificationListener,
                UserNotificationListenerAccessStatus as AccessStatus,
            )
        except Exception as exc:
            logger.warning("WinRT notifications unavailable; notifications disabled: %s", exc)
            return

        try:
            listener = UserNotificationListener.current
            status = listener.get_access_status()
            if status == AccessStatus.UNSPECIFIED:
                status = await listener.request_access_async()
            if status != AccessStatus.ALLOWED:
                logger.info("Notification access not granted (status=%s); disabled", status)
                return
        except Exception as exc:
            logger.warning("Could not access the notification listener: %s", exc)
            return

        logger.info("Notification listener started (polling every %.0fs)", self._poll_seconds)
        while self._running:
            try:
                notes = await listener.get_notifications_async(NotificationKinds.TOAST)
                self._process(notes)
            except Exception as exc:
                logger.debug("Notification poll failed: %s", exc)
            await asyncio.sleep(self._poll_seconds)

    def _process(self, notes: Iterable) -> None:
        """Diff a poll against what we have seen and emit the new ones (poll thread)."""
        fresh, self._seen, self._primed = partition_new(notes, self._seen, self._primed)
        for un in fresh:
            notification = _to_notification(un)
            if notification is not None:
                self._notify_hop.emit(notification)
