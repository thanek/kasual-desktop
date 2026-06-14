"""Domain model for a configured, launchable application.

Pure Python — no Qt, no I/O. The freedesktop ``.desktop`` format is part of the
problem domain (Kasual Desktop is a launcher of freedesktop app definitions), so
the *rules* for turning a ``[Desktop Entry]`` into an :class:`App` live here, in
:meth:`App.from_desktop_entry`. Only the file/``configparser`` I/O stays in the
``system.app_config`` adapter, which feeds raw key→value mappings to this.
"""

import os
import shlex
from dataclasses import dataclass, field
from collections.abc import Mapping

from domain.input.vocabulary import Trigger

# freedesktop Exec field codes — meaningless for our launcher (we pass no files
# or URLs), so they are stripped. See the Desktop Entry Specification.
_FIELD_CODES = {
    "%f", "%F", "%u", "%U", "%i", "%c", "%k",
    "%d", "%D", "%n", "%N", "%v", "%m",
}

# Apps without X-Kasual-Order sort after explicitly-ordered ones (ties: filename).
ORDER_DEFAULT = 10_000


@dataclass(frozen=True)
class App:
    """An app tile definition. Immutable; one per ``.desktop`` entry."""

    name:                 str
    command:              str
    args:                 tuple[str, ...]   = ()
    icon:                 str | None        = None   # qtawesome glyph (X-Kasual-Icon)
    icon_theme:           str | None        = None   # themed Icon name (freedesktop)
    color:                str               = "#2e3440"
    recall_menu_trigger:  str               = Trigger.CLICK
    launch_hide_grace_ms: int               = 0
    env:                  Mapping[str, str] = field(default_factory=dict)

    @property
    def command_basename(self) -> str:
        """Lowercased basename of the command — used to match KWin windows
        (resourceClass / desktopFile) back to this app."""
        return os.path.basename(self.command).lower()

    @classmethod
    def from_desktop_entry(cls, entry: Mapping[str, str]) -> "tuple[int, App] | None":
        """Build an :class:`App` from a freedesktop ``[Desktop Entry]`` mapping.

        Applies the standard's rules as Kasual Desktop uses them: skip entries that
        are not application tiles, strip Exec field codes, read the ``X-Kasual-*``
        extensions, fall back to defaults. Returns ``(order, app)`` — *order* is
        the placement key (``X-Kasual-Order``, default :data:`ORDER_DEFAULT`).

        Returns ``None`` for entries that are deliberately not tiles (``Type``
        other than Application, ``NoDisplay``/``Hidden`` true). Raises
        :class:`ValueError` for a malformed entry (no usable ``Name``/``Exec``),
        which the loader surfaces as a warning. Pure — no I/O, no logging.
        """
        if entry.get("Type", "Application") != "Application":
            return None
        if _bool_entry(entry, "NoDisplay"):
            return None
        if _bool_entry(entry, "Hidden"):
            return None

        name     = (entry.get("Name") or "").strip()
        exec_str = (entry.get("Exec") or "").strip()
        if not name or not exec_str:
            raise ValueError("missing Name or Exec")

        command, args = _parse_exec(exec_str)
        if command is None:
            raise ValueError("empty Exec after parsing")

        app = cls(
            name=name,
            command=command,
            args=tuple(args),
            icon=_str_entry(entry, "X-Kasual-Icon"),
            icon_theme=_str_entry(entry, "Icon"),
            color=_str_entry(entry, "X-Kasual-Color") or "#2e3440",
            recall_menu_trigger=_str_entry(entry, "X-Kasual-RecallMenuTrigger")
                                or Trigger.CLICK,
            launch_hide_grace_ms=_parse_int(entry.get("X-Kasual-HideGraceMs"), 0),
            env=_parse_env(entry.get("X-Kasual-Env")),
        )
        order = _parse_int(entry.get("X-Kasual-Order"), ORDER_DEFAULT)
        return order, app


def _bool_entry(entry: Mapping[str, str], key: str) -> bool:
    return (entry.get(key) or "").strip().lower() == "true"


def _str_entry(entry: Mapping[str, str], key: str) -> str | None:
    return (entry.get(key) or "").strip() or None


def _parse_exec(exec_str: str) -> "tuple[str | None, list[str]]":
    """Split a desktop ``Exec`` value into (command, args), dropping field codes."""
    cleaned: list[str] = []
    for token in shlex.split(exec_str):
        if token in _FIELD_CODES:
            continue
        cleaned.append(token.replace("%%", "%"))
    if not cleaned:
        return None, []
    return cleaned[0], cleaned[1:]


def _parse_env(raw: str | None) -> dict:
    """Parse ``X-Kasual-Env`` (``KEY1=val1;KEY2=val2``) into a dict."""
    env: dict[str, str] = {}
    if not raw:
        return env
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        if key:
            env[key] = value
    return env


def _parse_int(raw: str | None, default: int) -> int:
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default
