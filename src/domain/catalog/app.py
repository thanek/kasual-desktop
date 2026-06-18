"""Domain model for a configured, launchable application.

Pure Python — no Qt, no I/O. The freedesktop ``.desktop`` format is part of the
problem domain (Kasual Desktop is a launcher of freedesktop app definitions), so
the *rules* for turning a ``[Desktop Entry]`` into an :class:`App` live here, in
:meth:`App.from_desktop_entry`. Only the file/``configparser`` I/O stays in the
``system.app_config`` adapter, which feeds raw key→value mappings to this.
"""

import os
import re
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

# A Steam game launched through the `steam steam://rungameid/<id>` forwarder runs
# in its own top-level window whose KWin resourceClass is `steam_app_<id>`. The
# game id is extracted from the launch arguments so each game tile can be matched
# to *its* window rather than the shared `steam` client.
_STEAM_RUNGAMEID = re.compile(r"steam://rungameid/(\d+)")


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
    categories:           tuple[str, ...]   = ()      # freedesktop Categories
    wm_class:             str | None        = None    # freedesktop StartupWMClass

    @property
    def command_basename(self) -> str:
        """Lowercased basename of the command — used to match KWin windows
        (resourceClass / desktopFile) back to this app."""
        return os.path.basename(self.command).lower()

    @property
    def steam_app_id(self) -> str | None:
        """The Steam AppID this tile launches, if it is a `steam steam://
        rungameid/<id>` forwarder tile — else None.

        Steam games share the `steam` command, so every game tile has the same
        ``command_basename`` ("steam"). The AppID is what tells them apart.
        """
        if self.command_basename != "steam":
            return None
        for token in self.args:
            match = _STEAM_RUNGAMEID.search(token)
            if match:
                return match.group(1)
        return None

    @property
    def window_match_keys(self) -> tuple[str, ...]:
        """Identity strings a KWin window's resourceClass / desktopFile basename
        is matched against to attribute the window to this app.

        Normally the command basename, plus the ``StartupWMClass`` when set — a
        window's reported class often differs from the command name (e.g.
        ``org.kde.konsole`` vs ``konsole``), so a pinned tile carries the window's
        own class to match it back. A Steam game tile, however, matches only its
        own ``steam_app_<id>`` window — never the bare ``steam`` client whose
        window stays open behind *every* running game. Matching on the shared
        ``steam`` basename would light up every Steam tile at once.
        """
        appid = self.steam_app_id
        if appid is not None:
            return (f"steam_app_{appid}",)
        keys = [self.command_basename]
        if self.wm_class:
            keys.append(self.wm_class.lower())
        return tuple(dict.fromkeys(keys))   # de-duplicate, preserve order

    @property
    def is_game(self) -> bool:
        """True for a game tile — carries the standard freedesktop ``Game``
        category. Gates the in-game HUD toggle for the tile's own window even
        before the MangoHud layer is detected (see :mod:`domain.system.hud`)."""
        return "Game" in self.categories

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
            categories=_parse_categories(entry.get("Categories")),
            wm_class=_str_entry(entry, "StartupWMClass"),
        )
        order = _parse_int(entry.get("X-Kasual-Order"), ORDER_DEFAULT)
        return order, app

    def to_desktop_entry(self, order: int) -> dict[str, str]:
        """Render this app back into a freedesktop ``[Desktop Entry]`` mapping.

        The inverse of :meth:`from_desktop_entry`: it owns the App→freedesktop
        rules, the provisioning adapter does the file I/O. Emits only the keys
        Kasual Desktop uses, and only when they carry a non-default value, so a
        from→to→from round-trip is stable. *order* is the placement key
        (``X-Kasual-Order``), passed in because it is not an :class:`App` field
        (symmetric with ``from_desktop_entry`` returning ``(order, app)``).
        """
        entry: dict[str, str] = {
            "Type": "Application",
            "Name": self.name,
            "Exec": _join_exec(self.command, self.args),
        }
        if self.icon_theme is not None:
            entry["Icon"] = self.icon_theme
        if self.icon is not None:
            entry["X-Kasual-Icon"] = self.icon
        if self.wm_class is not None:
            entry["StartupWMClass"] = self.wm_class
        if self.color != "#2e3440":
            entry["X-Kasual-Color"] = self.color
        if self.recall_menu_trigger != Trigger.CLICK:
            entry["X-Kasual-RecallMenuTrigger"] = self.recall_menu_trigger
        if self.launch_hide_grace_ms:
            entry["X-Kasual-HideGraceMs"] = str(self.launch_hide_grace_ms)
        if self.env:
            entry["X-Kasual-Env"] = ";".join(f"{k}={v}" for k, v in self.env.items())
        if self.categories:
            entry["Categories"] = ";".join(self.categories) + ";"
        entry["X-Kasual-Order"] = str(order)
        return entry


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


def _join_exec(command: str, args: tuple[str, ...]) -> str:
    """Re-join (command, args) into a desktop ``Exec`` value, quoting each token
    so it survives the ``shlex.split`` in :func:`_parse_exec` (the inverse)."""
    return " ".join(shlex.quote(token) for token in (command, *args))


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


def _parse_categories(raw: str | None) -> tuple[str, ...]:
    """Parse a freedesktop ``Categories`` value (``Game;ActionGame;``) into a
    tuple, dropping the empty trailing field the spec's semicolons leave behind."""
    if not raw:
        return ()
    return tuple(part for part in (p.strip() for p in raw.split(";")) if part)


def _parse_int(raw: str | None, default: int) -> int:
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default
