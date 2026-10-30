"""Tests for the screen Kasual Desktop's surfaces are put on."""

import pytest
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from domain.display.display import SYSTEM_DECIDES
from infrastructure.common.qt.ui import target_screen
from infrastructure.common.qt.ui.screen_placement import (
    QtDisplays, RelaunchingPlacement, RepositioningPlacement,
)


@pytest.fixture(autouse=True)
def system_decides(qapp):
    target_screen.aim_at(SYSTEM_DECIDES)
    yield
    target_screen.aim_at(SYSTEM_DECIDES)


def test_the_system_decides_on_the_primary_screen():
    assert target_screen.target_screen() is QGuiApplication.primaryScreen()


def test_an_absent_screen_falls_back_to_the_primary_one():
    target_screen.aim_at("NO-SUCH-OUTPUT")
    assert target_screen.target_screen() is QGuiApplication.primaryScreen()


def test_a_connected_screen_is_the_target():
    screen = QGuiApplication.screens()[-1]
    target_screen.aim_at(screen.name())
    assert target_screen.target_screen() is screen


def test_a_placed_surface_is_moved_with_the_rest():
    surface = QWidget()
    target_screen.place_on_target_screen(surface)
    assert surface in target_screen.placed_surfaces()


def test_a_deleted_surface_is_left_behind():
    surface = QWidget()
    target_screen.place_on_target_screen(surface)
    from PyQt6 import sip
    sip.delete(surface)
    assert all(not sip.isdeleted(s) for s in target_screen.placed_surfaces())


def test_every_connected_screen_is_offered():
    offered = [display.id for display in QtDisplays().connected()]
    assert offered == [screen.name() for screen in QGuiApplication.screens()]


def test_moving_aims_new_surfaces_at_the_screen():
    screen = QGuiApplication.screens()[-1]
    RepositioningPlacement().move_shown_surfaces_to(screen.name())
    assert target_screen.target_screen() is screen


class FakeRelaunch:
    def __init__(self):
        self.relaunches = 0

    def relaunch_onto_another_screen(self):
        self.relaunches += 1


def test_a_desktop_that_cannot_move_live_relaunches():
    relaunch = FakeRelaunch()
    placement = RelaunchingPlacement(relaunch)
    placement.move_shown_surfaces_to("HDMI-A-1")
    assert (placement.moves_live(), relaunch.relaunches) == (False, 1)


def test_aiming_alone_never_relaunches():
    relaunch = FakeRelaunch()
    RelaunchingPlacement(relaunch).aim_new_surfaces_at("HDMI-A-1")
    assert relaunch.relaunches == 0
