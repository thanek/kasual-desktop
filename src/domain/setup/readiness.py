"""Turns a requirement plus its recipes and a live system into a readiness report."""

from domain.setup.plan import (
    COMMAND, GOAL, PATH, Assessment, Check, MachineProfile, Readiness,
    ReadinessReport, Recipe, StepStatus, recipe_for,
)
from domain.setup.ports import Requirement, SystemFacts


class SetupReadiness:
    def __init__(
        self,
        requirement: Requirement,
        facts: SystemFacts,
        recipes: tuple[Recipe, ...] = (),
    ) -> None:
        self._requirement = requirement
        self._facts = facts
        self._recipes = recipes

    def is_ready(self) -> bool:
        return self._requirement.assess().met

    def report(self) -> ReadinessReport:
        assessment = self._requirement.assess()
        subject = self._requirement.subject()
        recipe = recipe_for(self._profile(assessment), self._recipes)
        if recipe is None:
            return ReadinessReport(
                subject,
                Readiness.READY if assessment.met else Readiness.UNSUPPORTED,
                assessment.statuses,
            )
        return ReadinessReport(
            subject,
            Readiness.READY if assessment.met else Readiness.INCOMPLETE,
            assessment.statuses,
            self._evaluate(recipe, assessment),
            recipe.notice,
            recipe.remedies,
        )

    def _profile(self, assessment: Assessment) -> MachineProfile:
        return self._facts.machine().with_traits(assessment.traits)

    def _evaluate(
        self, recipe: Recipe, assessment: Assessment
    ) -> tuple[StepStatus, ...]:
        return tuple(
            StepStatus(step, self._satisfied(step.check, assessment))
            for step in recipe.steps
        )

    def _satisfied(self, check: Check, assessment: Assessment) -> bool:
        if check.kind == COMMAND:
            return self._facts.has_command(check.value)
        if check.kind == PATH:
            return self._facts.path_exists(check.value)
        if check.kind == GOAL:
            return assessment.met
        return self._requirement.satisfied(check)
