"""What "set up" means for one requirement, and which path a machine takes there.

Nothing here knows about any particular requirement or distribution: that
knowledge is data, held in each requirement's own ``recipes`` module.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

COMMAND = "command"
PATH = "path"
GOAL = "goal"


class Readiness(enum.Enum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Check:
    """A predicate a step is written against. A kind the core does not know is
    the requirement's own to answer."""

    kind: str
    value: str = ""


GOAL_REACHED = Check(GOAL)


@dataclass(frozen=True)
class Remedy:
    """A step Kasual Desktop can take on the user's behalf, offered as a button
    and carried out by the gate's handler for *key*."""

    key: str
    label: str


@dataclass(frozen=True)
class Step:
    title: str
    instruction: str
    check: Check
    command: str = ""


@dataclass(frozen=True)
class Recipe:
    """Empty ``arch``/``distros``/``traits`` match any machine; a recipe that
    names traits needs all of them."""

    key: str
    notice: str
    steps: tuple[Step, ...]
    arch: tuple[str, ...] = ()
    distros: tuple[str, ...] = ()
    traits: tuple[str, ...] = ()
    remedies: tuple[Remedy, ...] = ()


@dataclass(frozen=True)
class MachineProfile:
    """*traits* are properties that cut across distributions: a read-only ostree
    deployment, a Raspberry Pi board, or whatever the requirement itself
    contributes about the state it found."""

    arch: str
    distro_id: str = ""
    like: tuple[str, ...] = ()
    traits: tuple[str, ...] = ()

    @property
    def distro_names(self) -> tuple[str, ...]:
        return (self.distro_id, *self.like) if self.distro_id else self.like

    def with_traits(self, extra: tuple[str, ...]) -> MachineProfile:
        return MachineProfile(
            self.arch, self.distro_id, self.like, (*self.traits, *extra))


@dataclass(frozen=True)
class Verification:
    """Wording for a confirmation only an asynchronous probe can give — the
    requirement may hold on disk yet still not work."""

    unchecked: str
    running: str
    confirmed: str
    failed: str
    detail_unchecked: str = ""
    detail_failed: str = ""


@dataclass(frozen=True)
class Subject:
    """What is being set up, as the card presents it. A *blocking* subject has
    no way past it: Kasual Desktop cannot run without it, so the card offers to
    quit rather than to continue."""

    title: str
    unsupported: str
    blocking: bool = False
    verification: Verification | None = None


@dataclass(frozen=True)
class StatusLine:
    text: str
    met: bool
    detail: str = ""


@dataclass(frozen=True)
class StepStatus:
    step: Step
    done: bool


@dataclass(frozen=True)
class Assessment:
    """One pass over the system: what it found, and the traits that finding
    contributes to recipe selection."""

    statuses: tuple[StatusLine, ...]
    traits: tuple[str, ...] = ()

    @property
    def met(self) -> bool:
        return all(status.met for status in self.statuses)


@dataclass(frozen=True)
class ReadinessReport:
    subject: Subject
    state: Readiness
    statuses: tuple[StatusLine, ...] = ()
    steps: tuple[StepStatus, ...] = ()
    notice: str = ""
    remedies: tuple[Remedy, ...] = ()

    @property
    def remaining(self) -> int:
        return sum(1 for status in self.steps if not status.done)


def recipe_for(machine: MachineProfile, recipes: tuple[Recipe, ...]) -> Recipe | None:
    """*recipes* must be ordered specific-first: the first match wins."""
    return next((r for r in recipes if _matches(r, machine)), None)


def _matches(recipe: Recipe, machine: MachineProfile) -> bool:
    return (_matches_arch(recipe, machine)
            and _matches_distro(recipe, machine)
            and _matches_traits(recipe, machine))


def _matches_arch(recipe: Recipe, machine: MachineProfile) -> bool:
    return not recipe.arch or machine.arch in recipe.arch


def _matches_distro(recipe: Recipe, machine: MachineProfile) -> bool:
    return not recipe.distros or any(
        name in recipe.distros for name in machine.distro_names
    )


def _matches_traits(recipe: Recipe, machine: MachineProfile) -> bool:
    return set(recipe.traits) <= set(machine.traits)
