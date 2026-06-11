"""Pure text helpers shared across the domain (no Qt, no I/O)."""


def truncate(text: str, max_len: int) -> str:
    """Shorten `text` to `max_len`, ending with an ellipsis when it was cut."""
    return text[:max_len - 1] + '…' if len(text) > max_len else text
