"""Tests for AppAddController — the [＋] flow, with the picker overlay faked out.

Covers the hand-off after a confirmed selection: a DRM app asks for the check.
"""

from unittest.mock import MagicMock, patch

import pytest

from domain.catalog.app import App
from domain.provisioning.candidate import CandidateApp
from infrastructure.common.qt.desktop.app_add_controller import AppAddController


class FakePicker:
    """Records the callbacks instead of showing anything."""

    def __init__(self):
        self.on_confirm = None

    def present(self, _candidates, on_confirm, on_cancel, title):
        self.on_confirm = on_confirm


def _candidate(key, *, requires_cdm=False):
    return CandidateApp(
        key=key,
        app=App(name=key.title(), command=f"/opt/kd/{key}.sh",
                requires_cdm=requires_cdm),
        order=10, default_selected=False,
    )


@pytest.fixture
def flow():
    adder = MagicMock()
    adder.available.return_value = [_candidate("netflix", requires_cdm=True)]
    on_cdm_app = MagicMock()
    controller = AppAddController(
        [], adder, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(),
        restore_hints=MagicMock(), on_cdm_app=on_cdm_app,
    )
    picker = FakePicker()
    with patch(
        "infrastructure.common.qt.desktop.app_add_controller.OnboardingOverlay",
        return_value=picker,
    ):
        controller.show()
    return picker, on_cdm_app


class TestDrmHandOff:
    def test_adding_a_drm_app_asks_for_the_widevine_check(self, flow):
        picker, on_cdm_app = flow
        picker.on_confirm([_candidate("netflix", requires_cdm=True)])
        on_cdm_app.assert_called_once_with()

    def test_an_ordinary_app_asks_for_nothing(self, flow):
        picker, on_cdm_app = flow
        picker.on_confirm([_candidate("gimp")])
        on_cdm_app.assert_not_called()

    def test_confirming_an_empty_selection_asks_for_nothing(self, flow):
        picker, on_cdm_app = flow
        picker.on_confirm([])
        on_cdm_app.assert_not_called()
