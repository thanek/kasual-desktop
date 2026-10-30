"""How Kasual Desktop's shown surfaces reach another screen, per windowing system."""

from PyQt6.QtGui import QGuiApplication, QScreen
from PyQt6.QtWidgets import QWidget

from domain.display.display import Display, DisplayPlacement, Displays
from domain.display.relaunch import AnnouncedRelaunch
from infrastructure.common.qt.ui import target_screen
from infrastructure.common.qt.ui.target_screen import placed_surfaces, put_on


class QtDisplays(Displays):
    def connected(self) -> list[Display]:
        return [Display(screen.name(), _label(screen)) for screen in QGuiApplication.screens()]


def _label(screen: QScreen) -> str:
    model = screen.model()
    return f"{model} ({screen.name()})" if model else screen.name()


class ScreenPlacement(DisplayPlacement):
    def aim_at(self, display_id: str | None) -> None:
        target_screen.aim_at(display_id)

    def move_to(self, display_id: str | None) -> None:
        self.aim_at(display_id)
        screen = target_screen.target_screen()
        if screen is None:
            return
        for surface in placed_surfaces():
            self._carry(surface, screen)

    def moves_live(self) -> bool:
        return True

    def _carry(self, surface: QWidget, screen: QScreen) -> None:
        raise NotImplementedError


class RemappingPlacement(ScreenPlacement):
    """A layer surface is bound to its output when it maps, so it maps again."""

    def _carry(self, surface: QWidget, screen: QScreen) -> None:
        was_shown = surface.isVisible()
        was_active = surface.isActiveWindow()
        if was_shown:
            QWidget.hide(surface)
        put_on(surface, screen)
        if was_shown:
            QWidget.show(surface)
        if was_active:
            surface.activateWindow()


class RepositioningPlacement(ScreenPlacement):
    """An ordinary top-level moves; a fullscreen one is fullscreened again there."""

    def _carry(self, surface: QWidget, screen: QScreen) -> None:
        refullscreen = surface.isVisible() and surface.isFullScreen()
        offset = surface.pos() - surface.screen().geometry().topLeft()
        if refullscreen:
            surface.showNormal()
        surface.move(screen.geometry().topLeft() + offset)
        put_on(surface, screen)
        if refullscreen:
            surface.showFullScreen()


class RelaunchingPlacement(ScreenPlacement):
    def __init__(self, relaunch: AnnouncedRelaunch) -> None:
        self._relaunch = relaunch

    def move_to(self, display_id: str | None) -> None:
        self.aim_at(display_id)
        self._relaunch.relaunch_onto_another_screen()

    def moves_live(self) -> bool:
        return False
