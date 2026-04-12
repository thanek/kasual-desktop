"""Kontroler aplikacji — wiring między gamepadem, desktopem, overlayem i trayem."""

import logging

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher
from desktop import Desktop
from overlays.home_overlay import HomeOverlay
from system.window_manager import KWinWindowManager
from ui.tray import SystemTray

logger = logging.getLogger(__name__)


class Application:
    """
    Łączy wszystkie komponenty aplikacji i obsługuje globalne zdarzenia:
      - BTN_MODE → buduje menu kontekstowe i pokazuje HomeOverlay
      - connected_changed → synchronizuje stan desktopa, overlaya i traya
    """

    def __init__(
        self,
        apps:    list[dict],
        gamepad: GamepadWatcher,
        desktop: Desktop,
        overlay: HomeOverlay,
        tray:    SystemTray,
        wm:      KWinWindowManager,
    ) -> None:
        self._apps    = apps
        self._gamepad = gamepad
        self._desktop = desktop
        self._overlay = overlay
        self._tray    = tray
        self._wm      = wm

        gamepad.btn_mode_pressed.connect(self._on_btn_mode)
        gamepad.connected_changed.connect(self._on_connected_changed)

    def start(self) -> None:
        """Uruchamia okresowe odświeżanie listy okien."""
        self._wm.start_periodic_refresh(3000)

    # ── Obsługa zdarzeń ────────────────────────────────────────────────────

    def _on_btn_mode(self) -> None:
        """BTN_MODE: pokazuje overlay z menu dopasowanym do aktualnego kontekstu."""
        running_idx = self._desktop.app_manager.running_idx()
        dyn         = self._desktop.active_dynamic_window

        if running_idx is None and dyn is None:
            # Na pulpicie → menu systemowe z powrotem do pulpitu
            self._overlay.show_overlay(on_cancel=self._desktop.show_desktop)
            return

        # Aplikacja lub okno dynamiczne jest aktywne → menu kontekstowe
        if running_idx is not None:
            title     = self._apps[running_idx]["name"]
            close_cb  = self._desktop.request_close_running_app
            cancel_cb = self._desktop.restore_dynamic_window
        else:
            _, title  = dyn
            close_cb  = self._desktop.request_close_dynamic_window
            cancel_cb = self._desktop.restore_dynamic_window

        label = title if len(title) <= 22 else title[:21] + '…'
        extra = [
            {
                "label":    f"  Powrót do {label}",
                "icon":     "fa5s.times",
                "callback": cancel_cb,
            },
            {
                "label":    f"  Zamknij {label}",
                "icon":     "fa5s.times-circle",
                "callback": close_cb,
            },
            {
                "label":    "  Powrót do Pulpitu",
                "icon":     "fa5s.home",
                "callback": self._desktop.show_desktop,
            },
        ]
        self._overlay.show_overlay(extra_items=extra)

    def _on_connected_changed(self, connected: bool) -> None:
        """Pad podłączony / odłączony: synchronizuje wszystkie komponenty."""
        self._tray.set_connected(connected)
        if connected:
            self._desktop.resume()
        else:
            self._overlay.hide_overlay()
            self._desktop.hide()
