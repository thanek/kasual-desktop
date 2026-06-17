"""The mutable selection over the candidate list.

The multi-select analogue of :class:`domain.menu.cursor.MenuCursor`: it owns
*which* candidates are toggled on, seeded from each candidate's
``default_selected``. The navigation cursor (which row is highlighted) stays in
the view; this holds only the chosen-state, so the use-case and tests reason
about selection without Qt.
"""

from domain.provisioning.candidate import CandidateApp


class AppSelection:
    def __init__(self, candidates: list[CandidateApp]) -> None:
        self._candidates = list(candidates)
        self._selected = [c.default_selected for c in self._candidates]

    @property
    def count(self) -> int:
        return len(self._candidates)

    def is_selected(self, index: int) -> bool:
        return self._selected[index]

    def toggle(self, index: int) -> None:
        self._selected[index] = not self._selected[index]

    def chosen(self) -> list[CandidateApp]:
        """The selected candidates, preserving the candidate-list order."""
        return [c for c, on in zip(self._candidates, self._selected) if on]
