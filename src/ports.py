"""Ports — the abstract capabilities the app depends on, implemented by infra
adapters (system/power.py, system/volume.py) and by the Desktop view.

This is the boundary that keeps the application/registry layer free of pactl,
systemctl and Desktop internals.
"""

from collections.abc import Callable
from typing import Protocol


class PowerControl(Protocol):
    """System power actions (suspend / reboot / power off)."""

    def suspend(self) -> None: ...
    def reboot(self) -> None: ...
    def poweroff(self) -> None: ...


class VolumeControl(Protocol):
    """Read/write the default audio sink volume as a percentage (0–100)."""

    def get(self) -> int: ...
    def set(self, percent: int) -> None: ...


class DesktopShell(Protocol):
    """The Desktop capabilities that system actions drive."""

    def open_volume_overlay(self) -> None: ...
    def pause(self) -> None: ...


class DesktopView(Protocol):
    """The Qt-side operations the app-lifecycle coordinator drives on the
    Desktop window. Keeps `AppLifecycle` free of QWidget/QDialog internals: the
    coordinator orchestrates show/hide/activate and dialog spawning through this
    narrow port, and a fake satisfying it makes the lifecycle testable."""

    def is_visible(self) -> bool: ...
    def show_fullscreen(self) -> None: ...
    def activate(self) -> None: ...
    def hide_view(self) -> None: ...
    def close_active_dialog(self) -> None: ...
    def show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None: ...
    def show_error(self, message: str) -> None: ...
    # Driven by the Desktop coordinator (show/pause/resume orchestration):
    def take_input(self) -> None: ...      # take gamepad focus (push pad handler)
    def release_input(self) -> None: ...   # give it up (pop pad handler)
    def refresh_windows(self) -> None: ...
    def pause_overlays(self) -> None: ...
    def resume_overlays(self) -> None: ...


class Scheduler(Protocol):
    """Run a callback after a delay, without coupling the application layer to a
    concrete timer (Qt's QTimer.singleShot in production)."""

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> None: ...


class Feedback(Protocol):
    """Audio cue feedback for application-driven events ('select', …). Keeps the
    use-case layer from importing the sound backend directly."""

    def play(self, cue: str) -> None: ...


class Prompts(Protocol):
    """User-facing message templates (localized). Lives behind a port so the
    application layer stays free of Qt's translation machinery; the adapter owns
    the strings and their translation context."""

    def close_confirm(self, name: str) -> str: ...
    def launch_failed(self, error: str) -> str: ...


class SessionView(Protocol):
    """Desktop visibility as the session policy drives it (the Desktop)."""

    def resume(self) -> None: ...
    def hide(self) -> None: ...


class ConnectionIndicator(Protocol):
    """Surface reflecting controller-connection state (the system tray)."""

    def set_connected(self, connected: bool) -> None: ...


class Dismissable(Protocol):
    """Something that can be dismissed if currently shown (the Home Overlay)."""

    def hide_overlay(self) -> None: ...
