"""Translation as a domain-facing service — beside `domain`, not under it.

The rest of the app localizes user-facing text without importing PyQt6: it calls
the module-level `translate(context, text)`, which delegates to whatever
`Translator` the composition root installed via `use()`. With no backend
installed (tests, headless tooling) it is the identity — strings pass through
untranslated — so nothing here, nor anything that only depends on here, needs Qt.

Why `translate(context, text)` and not a bare `_(text)`: the string extractor
(`pylupdate6`, see tools/update_translations.sh) scans source *statically* and
only harvests calls named `translate` taking a literal (context, text) pair.
Keeping that exact call shape — and not hiding it behind a 1-arg wrapper — is
what lands these strings in locale/kasual_*.ts. That name is the extractor's
contract, not a Qt dependency: the implementation below is plain Python.

The same `translate` doubles as an extraction marker for deferred strings: called
at import time (before any backend is installed) it returns the source verbatim,
so a data table can list `translate(...)` calls and have them harvested, then be
re-translated at render time once a backend is in place.
"""

from typing import Protocol


class Translator(Protocol):
    """Resolves a source string to its localized form within a context."""

    def translate(self, context: str, text: str) -> str: ...


_active: Translator | None = None


def use(translator: Translator | None) -> None:
    """Install (or, with None, clear) the backend `translate` delegates to.

    Called once by the composition root after the Qt application exists. Kept a
    module-level switch rather than a constructor argument so callers translate
    via the global `translate` without each one holding a `Translator`."""
    global _active
    _active = translator


def translate(context: str, text: str) -> str:
    """Localize `text` within `context`. Identity when no backend is installed."""
    return _active.translate(context, text) if _active is not None else text
