"""One-time hint that Kasual is up, and off screen on purpose."""

from typing import Protocol

from domain.notifications.notifier import DesktopNotifier
from domain.shared.i18n import translate
from domain.shared.scheduler import Scheduler


class BackgroundHintMemory(Protocol):
    def was_ever_shown(self) -> bool: ...
    def mark_shown(self) -> None: ...


class DesktopPresence(Protocol):
    def is_visible(self) -> bool: ...


_PAD_DETECTION_GRACE_MS = 3000


class BackgroundHint:
    """Tells the user once that Kasual is waiting in the background."""

    def __init__(
        self,
        notifier: DesktopNotifier,
        memory: BackgroundHintMemory,
        desktop: DesktopPresence,
        scheduler: Scheduler,
    ) -> None:
        self._notifier = notifier
        self._memory = memory
        self._desktop = desktop
        self._scheduler = scheduler

    def offer(self) -> None:
        if self._memory.was_ever_shown():
            return
        self._scheduler.call_later(
            _PAD_DETECTION_GRACE_MS, self._show_unless_desktop_surfaced,
        )

    def _show_unless_desktop_surfaced(self) -> None:
        if self._desktop.is_visible():
            return
        self._notifier.notify(
            translate("Kasual Desktop", "Kasual Desktop is running in the background"),
            translate("Kasual Desktop",
                      "The full desktop appears when you turn on a gamepad "
                      "or use the system tray icon"),
        )
        self._memory.mark_shown()
