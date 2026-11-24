"""The port over the popups the desktop environment shows for notifications."""

from typing import Protocol


class NotificationPopups(Protocol):
    def expire_without_keyboard_or_mouse(self) -> None: ...
    def wait_for_keyboard_or_mouse(self) -> None: ...
    def dismiss_all(self) -> None: ...


class UncontrolledPopups(NotificationPopups):
    def expire_without_keyboard_or_mouse(self) -> None:
        pass

    def wait_for_keyboard_or_mouse(self) -> None:
        pass

    def dismiss_all(self) -> None:
        pass
