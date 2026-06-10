"""The user-facing message-template port (localized), driven by the lifecycle."""

from typing import Protocol


class Prompts(Protocol):
    """User-facing message templates (localized). Lives behind a port so the
    application layer stays free of Qt's translation machinery; the adapter owns
    the strings and their translation context."""

    def close_confirm(self, name: str) -> str: ...
    def launch_failed(self, error: str) -> str: ...
