"""Shared base for the level value objects (Volume, Brightness).

An immutable integer level constrained to ``[MIN, 100]``, with a step size and a
default. Subclasses set only the range/step constants; the clamp-on-construction
rule and the ``adjusted`` step are shared so the two levels cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar, Self


@dataclass(frozen=True)
class BoundedValue:
    """An immutable level in ``[MIN, 100]``. Construction clamps into range."""

    MIN:     ClassVar[int] = 0
    STEP:    ClassVar[int] = 1
    DEFAULT: ClassVar[int] = 50

    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", max(self.MIN, min(100, self.value)))

    def adjusted(self, delta: int) -> Self:
        """The same kind of value *delta* steps away (re-clamped)."""
        return replace(self, value=self.value + delta)
