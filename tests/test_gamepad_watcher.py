"""
Testy jednostkowe dla GamepadWatcher.

Testujemy:
  - stos handlerów (push/pop, LIFO, deduplikacja)
  - flagę _suppress_uinput
  - _dispatch i inject
  - _translate (eventy EV_KEY i EV_ABS)
  - _handle_stick_axis (próg, histereza, brak powtórzeń)
  - _is_gamepad (filtrowanie urządzeń)

Wątek _loop jest zawsze zablokowany przez fixture mock_gamepad,
więc żadne evdev ani UInput nie są potrzebne.
"""

import types
from evdev import ecodes


# ── Helpers ────────────────────────────────────────────────────────────────────

def ev(ev_type, code, value):
    """Szybki konstruktor zdarzenia evdev (duck-typing)."""
    return types.SimpleNamespace(type=ev_type, code=code, value=value)


# ── Stos handlerów ─────────────────────────────────────────────────────────────

class TestHandlerStack:
    def test_push_sets_suppress(self, mock_gamepad):
        assert mock_gamepad._suppress_uinput is False
        mock_gamepad.push_handler(lambda e: None)
        assert mock_gamepad._suppress_uinput is True

    def test_pop_clears_suppress_when_empty(self, mock_gamepad):
        h = lambda e: None
        mock_gamepad.push_handler(h)
        mock_gamepad.pop_handler(h)
        assert mock_gamepad._suppress_uinput is False

    def test_pop_keeps_suppress_when_handlers_remain(self, mock_gamepad):
        h1 = lambda e: None
        h2 = lambda e: None
        mock_gamepad.push_handler(h1)
        mock_gamepad.push_handler(h2)
        mock_gamepad.pop_handler(h2)
        assert mock_gamepad._suppress_uinput is True

    def test_push_deduplicates_and_moves_to_top(self, mock_gamepad):
        h1 = lambda e: None
        h2 = lambda e: None
        mock_gamepad.push_handler(h1)
        mock_gamepad.push_handler(h2)
        mock_gamepad.push_handler(h1)   # h1 już był → przesuń na szczyt
        assert mock_gamepad._handlers[-1] is h1
        assert len(mock_gamepad._handlers) == 2

    def test_pop_nonexistent_handler_is_noop(self, mock_gamepad):
        mock_gamepad.pop_handler(lambda e: None)   # nie powinno rzucać

    def test_multiple_push_pop_cycle(self, mock_gamepad):
        h = lambda e: None
        for _ in range(5):
            mock_gamepad.push_handler(h)
            mock_gamepad.pop_handler(h)
        assert mock_gamepad._handlers == []
        assert mock_gamepad._suppress_uinput is False


# ── _dispatch ─────────────────────────────────────────────────────────────────

class TestDispatch:
    def test_calls_top_handler(self, mock_gamepad):
        received = []
        mock_gamepad.push_handler(lambda e: received.append(e))
        mock_gamepad._dispatch("select")
        assert received == ["select"]

    def test_calls_only_top_handler(self, mock_gamepad):
        bottom = []
        top = []
        mock_gamepad.push_handler(lambda e: bottom.append(e))
        mock_gamepad.push_handler(lambda e: top.append(e))
        mock_gamepad._dispatch("up")
        assert top == ["up"]
        assert bottom == []   # handler pod spodem nie dostaje eventu

    def test_noop_when_stack_empty(self, mock_gamepad):
        mock_gamepad._dispatch("down")   # nie powinno rzucać

    def test_inject_routes_to_dispatch(self, mock_gamepad):
        received = []
        mock_gamepad.push_handler(lambda e: received.append(e))
        mock_gamepad.inject("cancel")
        assert received == ["cancel"]


# ── _translate — klawisze ─────────────────────────────────────────────────────

class TestTranslateKeys:
    """
    _translate dla EV_KEY:
      - press (value=1) → emit nawigacyjny
      - release (value=0) → tylko aktualizacja held, brak emisji
    """

    def _translate_with_handler(self, mock_gamepad, ev_obj):
        """Pomocnik: push handler, wywołaj _translate, zwróć zebrane eventy."""
        received = []
        mock_gamepad.push_handler(lambda e: received.append(e))
        held, stick, pending = set(), {"x": None, "y": None}, []
        mock_gamepad._translate(ev_obj, held, stick, pending)
        return received

    def test_btn_south_emits_select(self, mock_gamepad):
        result = self._translate_with_handler(
            mock_gamepad, ev(ecodes.EV_KEY, ecodes.BTN_SOUTH, 1)
        )
        assert result == ["select"]

    def test_btn_east_emits_cancel(self, mock_gamepad):
        result = self._translate_with_handler(
            mock_gamepad, ev(ecodes.EV_KEY, ecodes.BTN_EAST, 1)
        )
        assert result == ["cancel"]

    def test_btn_west_emits_close(self, mock_gamepad):
        result = self._translate_with_handler(
            mock_gamepad, ev(ecodes.EV_KEY, ecodes.BTN_WEST, 1)
        )
        assert result == ["close"]

    def test_key_release_emits_nothing(self, mock_gamepad):
        result = self._translate_with_handler(
            mock_gamepad, ev(ecodes.EV_KEY, ecodes.BTN_SOUTH, 0)
        )
        assert result == []

    def test_held_tracks_pressed_keys(self, mock_gamepad):
        held = set()
        mock_gamepad._translate(ev(ecodes.EV_KEY, ecodes.BTN_SOUTH, 1), held, {"x": None, "y": None}, [])
        assert ecodes.BTN_SOUTH in held

    def test_held_removes_released_keys(self, mock_gamepad):
        held = {ecodes.BTN_SOUTH}
        mock_gamepad._translate(ev(ecodes.EV_KEY, ecodes.BTN_SOUTH, 0), held, {"x": None, "y": None}, [])
        assert ecodes.BTN_SOUTH not in held

    def test_start_plus_select_emits_btn_mode(self, mock_gamepad):
        """BTN_START wciśnięty gdy BTN_SELECT trzymany → sygnał btn_mode_pressed."""
        fired = []
        mock_gamepad.btn_mode_pressed.connect(lambda: fired.append(True))
        held = {ecodes.BTN_SELECT}
        mock_gamepad._translate(ev(ecodes.EV_KEY, ecodes.BTN_START, 1), held, {"x": None, "y": None}, [])
        assert fired == [True]


# ── _translate — DPAD (EV_ABS HAT) ───────────────────────────────────────────

class TestTranslateDpad:
    """
    DPAD przez HAT0X/HAT0Y → dodaje do pending (emitowane w SYN).
    """

    def _pending(self, mock_gamepad, ev_obj):
        pending = []
        mock_gamepad._translate(ev_obj, set(), {"x": None, "y": None}, pending)
        return pending

    def test_hat_up(self, mock_gamepad):
        assert self._pending(mock_gamepad, ev(ecodes.EV_ABS, ecodes.ABS_HAT0Y, -1)) == ["up"]

    def test_hat_down(self, mock_gamepad):
        assert self._pending(mock_gamepad, ev(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 1)) == ["down"]

    def test_hat_left(self, mock_gamepad):
        assert self._pending(mock_gamepad, ev(ecodes.EV_ABS, ecodes.ABS_HAT0X, -1)) == ["left"]

    def test_hat_right(self, mock_gamepad):
        assert self._pending(mock_gamepad, ev(ecodes.EV_ABS, ecodes.ABS_HAT0X, 1)) == ["right"]

    def test_hat_center_no_event(self, mock_gamepad):
        assert self._pending(mock_gamepad, ev(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 0)) == []

    def test_hat_updates_stick_state(self, mock_gamepad):
        stick = {"x": None, "y": None}
        mock_gamepad._translate(ev(ecodes.EV_ABS, ecodes.ABS_HAT0Y, -1), set(), stick, [])
        assert stick["y"] == "up"

    def test_hat_center_clears_stick_state(self, mock_gamepad):
        stick = {"x": None, "y": "up"}
        mock_gamepad._translate(ev(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 0), set(), stick, [])
        assert stick["y"] is None


# ── _handle_stick_axis ────────────────────────────────────────────────────────

class TestHandleStickAxis:
    from gamepad_watcher import STICK_THRESHOLD, STICK_RESET

    OVER  = 11000   # > STICK_THRESHOLD (10000)
    UNDER = 5000    # < STICK_RESET (6000)

    def test_positive_over_threshold_appends_pos(self, mock_gamepad):
        stick, pending = {"x": None}, []
        mock_gamepad._handle_stick_axis(self.OVER, "x", "left", "right", stick, pending)
        assert pending == ["right"]
        assert stick["x"] == "right"

    def test_negative_over_threshold_appends_neg(self, mock_gamepad):
        stick, pending = {"x": None}, []
        mock_gamepad._handle_stick_axis(-self.OVER, "x", "left", "right", stick, pending)
        assert pending == ["left"]
        assert stick["x"] == "left"

    def test_no_repeat_same_direction(self, mock_gamepad):
        """Jeżeli oś już ma kierunek, ten sam kierunek nie dodaje kolejnego eventu."""
        stick, pending = {"x": "right"}, []
        mock_gamepad._handle_stick_axis(self.OVER, "x", "left", "right", stick, pending)
        assert pending == []

    def test_reset_below_hysteresis(self, mock_gamepad):
        stick, pending = {"x": "right"}, []
        mock_gamepad._handle_stick_axis(self.UNDER, "x", "left", "right", stick, pending)
        assert stick["x"] is None
        assert pending == []

    def test_no_event_between_threshold_and_reset(self, mock_gamepad):
        """Strefa martwa: wartość między STICK_RESET a STICK_THRESHOLD → nic."""
        mid = 8000   # > STICK_RESET ale < STICK_THRESHOLD
        stick, pending = {"x": None}, []
        mock_gamepad._handle_stick_axis(mid, "x", "left", "right", stick, pending)
        assert pending == []
        assert stick["x"] is None


# ── _is_gamepad ───────────────────────────────────────────────────────────────

class TestIsGamepad:
    """Statyczna metoda filtrująca urządzenia."""

    from gamepad_watcher import GamepadWatcher

    def _make_device(self, keys=None, abs_axes=None, has_key_a=False):
        """Zbuduj mock urządzenia z podanymi capabilities."""
        from unittest.mock import MagicMock
        d = MagicMock()
        caps = {}
        if keys is not None:
            if has_key_a:
                keys = list(keys) + [ecodes.KEY_A]
            caps[ecodes.EV_KEY] = keys
        if abs_axes is not None:
            caps[ecodes.EV_ABS] = abs_axes
        d.capabilities.return_value = caps
        return d

    def test_recognizes_gamepad_with_buttons(self):
        from gamepad_watcher import GamepadWatcher
        d = self._make_device(keys=[ecodes.BTN_SOUTH, ecodes.BTN_EAST, ecodes.BTN_NORTH,
                                     ecodes.BTN_WEST, ecodes.BTN_START, ecodes.BTN_SELECT])
        assert GamepadWatcher._is_gamepad(d) is True

    def test_recognizes_gamepad_with_hat(self):
        from gamepad_watcher import GamepadWatcher
        d = self._make_device(keys=[ecodes.BTN_SOUTH], abs_axes=[ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y])
        assert GamepadWatcher._is_gamepad(d) is True

    def test_rejects_keyboard(self):
        from gamepad_watcher import GamepadWatcher
        d = self._make_device(keys=[ecodes.BTN_SOUTH, ecodes.BTN_EAST], has_key_a=True)
        assert GamepadWatcher._is_gamepad(d) is False

    def test_rejects_device_without_ev_key(self):
        from gamepad_watcher import GamepadWatcher
        d = self._make_device()   # brak EV_KEY
        assert GamepadWatcher._is_gamepad(d) is False

    def test_rejects_on_exception(self):
        from gamepad_watcher import GamepadWatcher
        from unittest.mock import MagicMock
        d = MagicMock()
        d.capabilities.side_effect = OSError("brak uprawnień")
        assert GamepadWatcher._is_gamepad(d) is False
