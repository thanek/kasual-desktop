"""Which screen Kasual Desktop runs on: the one the user picked while it is
connected, otherwise wherever the system puts it — the pick itself is kept."""

from domain.display.display import (
    SYSTEM_DECIDES, Display, DisplayPlacement, DisplayPreference, Displays,
)
from domain.shared.choice import remembered_but_absent

_NOTHING_APPLIED_YET = object()


class DisplaySelection:
    def __init__(
        self,
        preference: DisplayPreference,
        displays: Displays,
        placement: DisplayPlacement,
    ) -> None:
        self._preference = preference
        self._displays = displays
        self._placement = placement
        self._applied: object = _NOTHING_APPLIED_YET

    def options(self) -> list[Display]:
        connected = self._displays.connected()
        preferred = self._preference.preferred()
        if remembered_but_absent(connected, preferred):
            return [*connected, Display(preferred, preferred, connected=False)]
        return connected

    def chosen(self) -> str | None:
        return self._preference.preferred()

    def target(self) -> str | None:
        preferred = self._preference.preferred()
        if any(display.id == preferred for display in self._displays.connected()):
            return preferred
        return SYSTEM_DECIDES

    def settle(self) -> None:
        self._applied = self.target()
        self._placement.aim_new_surfaces_at(self._applied)

    def choose(self, display_id: str | None) -> None:
        self._preference.set_preferred(display_id)
        if self.target() != self._applied:
            self._move_to_target()

    def follow_screen_changes(self) -> None:
        target_changed = self.target() != self._applied
        if target_changed and self._placement.moves_live():
            self._move_to_target()

    def _move_to_target(self) -> None:
        self._applied = self.target()
        self._placement.move_shown_surfaces_to(self._applied)
