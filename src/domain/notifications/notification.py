"""A system notification — the platform-agnostic value object.

Pure Python — no Qt, no D-Bus. The desktop-environment translation (KDE's
`org.freedesktop.Notifications.Notify` arguments → `Notification`) stays in the
infrastructure adapter; this is just what a notification *is* once it has reached
the domain: who sent it, what it says, and when it arrived.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Notification:
    """One delivered notification. Immutable."""

    app_name:  str
    summary:   str
    timestamp: datetime
    body:      str        = ""
    # freedesktop app-icon hint: an icon-theme name or a file path/URI, as sent
    # in the Notify call. None where the sender gave none. The Qt overlay resolves
    # it to an actual icon (falling back to the app name).
    icon:      str | None = None
