"""Domain model for a configured, launchable application, and the rules for
turning a freedesktop ``[Desktop Entry]`` into one."""

import os
import re
import shlex
from dataclasses import dataclass, field
from collections.abc import Mapping

from domain.input.vocabulary import Trigger

# freedesktop Exec field codes — we pass no files/URLs, so they are stripped.
_FIELD_CODES = {
    "%f", "%F", "%u", "%U", "%i", "%c", "%k",
    "%d", "%D", "%n", "%N", "%v", "%m",
}

# Apps without X-Kasual-Order sort after explicitly-ordered ones (ties: filename).
ORDER_DEFAULT = 10_000

# A Steam game's own window has resourceClass `steam_app_<id>`; the id lets each
# game tile match its window rather than the shared `steam` client.
_STEAM_RUNGAMEID = re.compile(r"steam://rungameid/(\d+)")


@dataclass(frozen=True)
class App:
    """An app tile definition. Immutable; one per ``.desktop`` entry."""

    name:                 str
    command:              str
    args:                 tuple[str, ...]   = ()
    id:                   str               = ""     # stable identity (.desktop filename stem)
    icon:                 str | None        = None   # X-Kasual-Icon
    icon_theme:           str | None        = None   # freedesktop Icon
    color:                str               = "#2e3440"
    recall_menu_trigger:  str               = Trigger.CLICK
    launch_hide_grace_ms: int               = 0
    env:                  Mapping[str, str] = field(default_factory=dict)
    categories:           tuple[str, ...]   = ()      # freedesktop Categories
    wm_class:             str | None        = None    # freedesktop StartupWMClass
    requires_cdm:         bool              = False   # X-Kasual-RequiresCdm

    @property
    def command_basename(self) -> str:
        return os.path.basename(self.command).lower()

    @property
    def steam_app_id(self) -> str | None:
        """The Steam AppID, if this is a `steam://rungameid/<id>` forwarder tile —
        every game shares the `steam` command, so the AppID tells them apart."""
        if self.command_basename != "steam":
            return None
        for token in self.args:
            match = _STEAM_RUNGAMEID.search(token)
            if match:
                return match.group(1)
        return None

    @property
    def window_match_keys(self) -> tuple[str, ...]:
        """Identity strings a window is matched against to attribute it to this app.

        The command basename plus ``StartupWMClass`` when set (a window's class
        often differs from the command, e.g. ``org.kde.konsole`` vs ``konsole``).
        A Steam game matches only its own ``steam_app_<id>`` window — matching the
        shared ``steam`` basename would light up every Steam tile at once."""
        appid = self.steam_app_id
        if appid is not None:
            return (f"steam_app_{appid}",)
        keys = [self.command_basename]
        if self.wm_class:
            keys.append(self.wm_class.lower())
        return tuple(dict.fromkeys(keys))

    @property
    def is_game(self) -> bool:
        """Carries the freedesktop ``Game`` category — gates the in-game HUD toggle
        before the MangoHud layer is detected."""
        return "Game" in self.categories

    @classmethod
    def from_desktop_entry(cls, entry: Mapping[str, str]) -> "tuple[int, App] | None":
        """Returns ``(order, app)``, ``None`` for entries that are not tiles
        (``Type`` ≠ Application, ``NoDisplay`` / ``Hidden``), or raises
        ``ValueError`` for a malformed entry (no usable ``Name`` / ``Exec``)."""
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
            requires_cdm=_bool_entry(entry, "X-Kasual-RequiresCdm"),
        )
        order = _parse_int(entry.get("X-Kasual-Order"), ORDER_DEFAULT)
        return order, app

    def to_desktop_entry(self, order: int) -> dict[str, str]:
        """Inverse of :meth:`from_desktop_entry`. Emits a key only when non-default,
        so a from→to→from round-trip is stable."""
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
        if self.requires_cdm:
            entry["X-Kasual-RequiresCdm"] = "true"
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
    """Inverse of :func:`_parse_exec`; quotes each token to survive its shlex.split."""
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
    """Parse a freedesktop ``Categories`` value, dropping the trailing empty field."""
    if not raw:
        return ()
    return tuple(part for part in (p.strip() for p in raw.split(";")) if part)


def _parse_int(raw: str | None, default: int) -> int:
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default
