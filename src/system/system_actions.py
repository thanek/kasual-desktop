"""Shared system action definitions used by Desktop and HomeOverlay."""

from PyQt6.QtCore import QT_TRANSLATE_NOOP

# Mapping: action type → (confirmation question, system command or None)
# None as command means the "hide_desktop" action (handled by the caller).
# Questions marked with QT_TRANSLATE_NOOP — translation happens at the point of use
# via QCoreApplication.translate("Kasual", question).
SYSTEM_ACTION_SPECS: dict[str, tuple[str, list[str] | None]] = {
    "sleep":        (QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to sleep?"),            ["systemctl", "suspend"]),
    "restart":      (QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to restart?"),          ["systemctl", "reboot"]),
    "shutdown":     (QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to shut down?"),        ["systemctl", "poweroff"]),
    "hide_desktop": (QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to minimize Desktop?"), None),
}
