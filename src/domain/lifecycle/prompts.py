"""The user-facing message-template port (localized) and its default impl.

The lifecycle drives these prompts; they used to sit behind a port in an
infrastructure adapter only because building a localized string meant importing
Qt. With translation behind the `domain.shared.i18n` port, the message vocabulary —
the wording and its translation context — is plain domain logic and lives here.
The port stays so callers can substitute it (e.g. fakes in tests).
"""

from typing import Protocol

from domain.shared.text import truncate
from domain.shared.i18n import translate


class Prompts(Protocol):
    """User-facing message templates (localized)."""

    def close_confirm(self, name: str) -> str: ...
    def launch_failed(self, error: str) -> str: ...


class LocalizedPrompts(Prompts):
    """Default `Prompts`: source strings localized through `domain.shared.i18n`.

    The translation context ("Desktop") is kept stable so the existing locale
    entries (locale/kasual_*.ts) keep resolving."""

    def close_confirm(self, name: str) -> str:
        # Truncate the (potentially long) app/window title for display.
        return translate(
            "Desktop", 'Are you sure you want to close\n"{0}"?'
        ).format(truncate(name, 40))

    def launch_failed(self, error: str) -> str:
        return translate(
            "Desktop", "Failed to launch application:\n{0}"
        ).format(error)
