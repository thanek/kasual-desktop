"""What "ready for DRM playback" means, and which path a machine takes there.

Nothing here knows about any distribution: that knowledge is data, held in
``recipes.py``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class CheckKind(enum.Enum):
    COMMAND = "command"
    PATH = "path"
    CDM = "cdm"


class Readiness(enum.Enum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Check:
    kind: CheckKind
    value: str = ""


@dataclass(frozen=True)
class Step:
    title: str
    instruction: str
    check: Check
    command: str = ""


@dataclass(frozen=True)
class Recipe:
    """Empty ``arch``/``distros`` match any machine."""

    key: str
    notice: str
    steps: tuple[Step, ...]
    arch: tuple[str, ...] = ()
    distros: tuple[str, ...] = ()


@dataclass(frozen=True)
class MachineProfile:
    arch: str
    distro_id: str = ""
    like: tuple[str, ...] = ()

    @property
    def distro_names(self) -> tuple[str, ...]:
        return (self.distro_id, *self.like) if self.distro_id else self.like


@dataclass(frozen=True)
class StepStatus:
    step: Step
    done: bool


@dataclass(frozen=True)
class ReadinessReport:
    state: Readiness
    steps: tuple[StepStatus, ...] = ()
    notice: str = ""

    @property
    def remaining(self) -> int:
        return sum(1 for status in self.steps if not status.done)


def recipe_for(machine: MachineProfile, recipes: tuple[Recipe, ...]) -> Recipe | None:
    """*recipes* must be ordered specific-first: the first match wins."""
    return next((r for r in recipes if _matches(r, machine)), None)


def _matches(recipe: Recipe, machine: MachineProfile) -> bool:
    return _matches_arch(recipe, machine) and _matches_distro(recipe, machine)


def _matches_arch(recipe: Recipe, machine: MachineProfile) -> bool:
    return not recipe.arch or machine.arch in recipe.arch


def _matches_distro(recipe: Recipe, machine: MachineProfile) -> bool:
    return not recipe.distros or any(
        name in recipe.distros for name in machine.distro_names
    )
