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
    icon:      str | None = None   # qtawesome glyph; None where unknown
