"""D-Bus client for the Kasual Helper GNOME Shell extension.

The extension exports ``org.consoledesktop.GnomeHelper`` and does the work Mutter
gives us no protocol for: reporting the window list (with PIDs), the window
operations, and pinning Kasual's own surfaces above a fullscreen app. This module
is the thin session-bus caller shared by the GNOME window-manager, surface and
overlay adapters.
"""

from __future__ import annotations

import logging

from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PyQt6.QtGui import QGuiApplication

logger = logging.getLogger(__name__)

SERVICE = "org.consoledesktop.GnomeHelper"
OBJECT_PATH = "/org/consoledesktop/GnomeHelper"
INTERFACE = "org.consoledesktop.GnomeHelper"

EXTENSION_UUID = "kasual-helper@consoledesktop.org"

_DEFAULT_APP_ID = "kasual-desktop"

_iface: QDBusInterface | None = None


def _interface() -> QDBusInterface:
    global _iface
    if _iface is None:
        _iface = QDBusInterface(
            SERVICE, OBJECT_PATH, INTERFACE, QDBusConnection.sessionBus())
    return _iface


def call(method: str, *args) -> QDBusMessage:
    return _interface().call(method, *args)


def _succeeded(reply: QDBusMessage) -> bool:
    return reply.type() == QDBusMessage.MessageType.ReplyMessage


def helper_present() -> bool:
    """True if the extension is loaded and answering on the session bus."""
    return _succeeded(call("Ping"))


def app_id() -> str:
    """Kasual's Wayland app_id — the ``wm_class`` the extension pins by. Set from
    ``QGuiApplication.setDesktopFileName`` in the composition root."""
    return QGuiApplication.desktopFileName() or _DEFAULT_APP_ID


def list_windows_json() -> str | None:
    """Raw JSON from ``ListWindows``, or None if the call failed."""
    reply = call("ListWindows")
    if not _succeeded(reply):
        logger.debug("ListWindows failed: %s", reply.errorMessage())
        return None
    arguments = reply.arguments()
    return arguments[0] if arguments else "[]"


def simulate_user_activity() -> None:
    """Reset GNOME's idle time (unblanks the screen; a locked shield stays locked).
    Fire-and-forget: without the extension the message is a harmless no-op."""
    msg = QDBusMessage.createMethodCall(
        SERVICE, OBJECT_PATH, INTERFACE, "SimulateUserActivity")
    QDBusConnection.sessionBus().asyncCall(msg)


def set_surface_role(title: str, layer: int, anchors: int, keyboard: int) -> None:
    """Declare what a Kasual window is, keyed by its window title.

    Mutter lets no client size or place its own top-levels, offers no layer concept,
    and focuses whatever window it maps — so the layer-shell vocabulary is handed to
    the extension, which applies it compositor-side: anchors become geometry, the
    layer becomes the stacking order among Kasual's pinned surfaces, and a surface
    that wants no keyboard is kept off the focus. An extension predating the keyboard
    argument rejects the call, and keeps the role it always had."""
    reply = call("SetSurfaceRole", title, int(layer), int(anchors), int(keyboard))
    if not _succeeded(reply):
        call("SetSurfaceRole", title, int(layer), int(anchors))


def activate_surface(title: str) -> None:
    """Focus and raise one of Kasual's own windows, by title."""
    call("ActivateSurface", title)


def show_overlay() -> None:
    """Pin Kasual's surfaces above everything (incl. fullscreen) and drop
    Mutter's unredirect so they actually paint over a scanned-out fullscreen app."""
    call("ShowOverlay", app_id())


def cede_overlay() -> None:
    """Yield the screen to the launched app while keeping Kasual's surfaces
    mapped just below it — so closing the app reveals the Desktop with no remap.
    The Qt side keeps the window shown."""
    call("CedeOverlay", app_id())


def hide_overlay() -> None:
    """Release the pin; hiding the surfaces themselves is the Qt side's job."""
    call("HideOverlay", app_id())


def is_sunk() -> bool:
    """Whether the ceded surfaces sit under the app's ordinary windows. The extension
    decides that from the focus, so Kasual cannot answer it on its own."""
    reply = call("IsSunk")
    if not _succeeded(reply):
        logger.debug("IsSunk failed: %s", reply.errorMessage())
        return False
    arguments = reply.arguments()
    return bool(arguments[0]) if arguments else False
