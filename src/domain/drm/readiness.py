"""Turns the recipes plus a live system into a readiness report."""

from domain.drm.plan import (
    Check, CheckKind, Readiness, ReadinessReport, Recipe, StepStatus, recipe_for,
)
from domain.drm.ports import SystemFacts
from domain.drm.recipes import all_recipes


class DrmReadiness:
    def __init__(
        self, facts: SystemFacts, recipes: tuple[Recipe, ...] | None = None
    ) -> None:
        self._facts = facts
        self._recipes = all_recipes() if recipes is None else recipes

    def is_ready(self) -> bool:
        return self._facts.cdm_path() is not None

    def report(self) -> ReadinessReport:
        recipe = recipe_for(self._facts.machine(), self._recipes)
        if recipe is None:
            return ReadinessReport(
                Readiness.READY if self.is_ready() else Readiness.UNSUPPORTED
            )
        # Readiness is the module itself, never the prerequisites: someone who
        # obtained it another way is ready with every step still unticked.
        state = Readiness.READY if self.is_ready() else Readiness.INCOMPLETE
        return ReadinessReport(state, self._evaluate(recipe), recipe.notice)

    def _evaluate(self, recipe: Recipe) -> tuple[StepStatus, ...]:
        return tuple(
            StepStatus(step, self._satisfied(step.check)) for step in recipe.steps
        )

    def _satisfied(self, check: Check) -> bool:
        if check.kind is CheckKind.COMMAND:
            return self._facts.has_command(check.value)
        if check.kind is CheckKind.PATH:
            return self._facts.path_exists(check.value)
        return self.is_ready()
