"""GNOME screen placement — Mutter decides where windows go, so the Kasual Helper
extension moves Kasual Desktop's windows; Qt is only told where they now live."""

from PyQt6.QtGui import QScreen
from PyQt6.QtWidgets import QWidget

from infrastructure.common.qt.ui.screen_placement import ScreenPlacement
from infrastructure.common.qt.ui.target_screen import put_on
from infrastructure.gnome import helper


class GnomePlacement(ScreenPlacement):
    def aim_new_surfaces_at(self, display_id: str | None) -> None:
        super().aim_new_surfaces_at(display_id)
        helper.set_target_monitor(display_id)

    def _carry(self, surface: QWidget, screen: QScreen) -> None:
        put_on(surface, screen)
