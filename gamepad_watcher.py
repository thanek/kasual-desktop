import logging
import threading
import time
from typing import Callable

from PyQt6.QtCore import pyqtSignal, QObject
from evdev import InputDevice, UInput, ecodes, list_devices

logger = logging.getLogger(__name__)

STICK_THRESHOLD = 10000   # zakres osi analogowej: -32768..32767
STICK_RESET     = 6000    # histereza – poniżej tej wartości oś jest "w centrum"

VIRTUAL_DEVICE_NAME = "console-desktop-vpad"


class GamepadWatcher(QObject):
    """
    Czyta eventy fizycznego pada w wątku tła.

    Pad jest zawsze grabowany ekskluzywnie. Wszystkie eventy oprócz BTN_MODE
    są przekazywane do wirtualnego pada (UInput, nazwa: VIRTUAL_DEVICE_NAME),
    z którego korzystają zewnętrzne aplikacje (np. Steam).

    Eventy nawigacyjne (up/down/left/right/select/cancel/close) są tłumaczone
    i rozsyłane przez stos handlerów LIFO – reaguje tylko handler na szczycie.
    BTN_MODE emituje osobny sygnał (nie trafia do stosu ani do wirtualnego pada).

    Interfejs stosu:
        push_handler(fn)  – dodaje handler na szczyt (jeśli był wcześniej, przesuwa)
        pop_handler(fn)   – usuwa handler
        inject(event)     – wstrzykuje event nawigacyjny z pominięciem pada (np. z klawiatury)

    Sygnały:
        btn_mode_pressed()     – BTN_MODE wciśnięty
        connected_changed(bool)
    """

    _raw              = pyqtSignal(str)    # wątek tła → GUI: event nawigacyjny
    btn_mode_pressed  = pyqtSignal()
    connected_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._handlers: list[Callable[[str], None]] = []
        self._lock = threading.Lock()
        self._raw.connect(self._dispatch)
        threading.Thread(target=self._loop, daemon=True, name="gamepad-watcher").start()

    # ── Publiczne API ──────────────────────────────────────────────────────

    def push_handler(self, handler: Callable[[str], None]) -> None:
        with self._lock:
            if handler in self._handlers:
                self._handlers.remove(handler)
            self._handlers.append(handler)

    def pop_handler(self, handler: Callable[[str], None]) -> None:
        with self._lock:
            if handler in self._handlers:
                self._handlers.remove(handler)

    def inject(self, event: str) -> None:
        """Wstrzyknij event nawigacyjny (np. z klawiatury) do aktywnego handlera."""
        self._dispatch(event)

    # ── Wewnętrzne ─────────────────────────────────────────────────────────

    def _dispatch(self, event: str) -> None:
        with self._lock:
            handler = self._handlers[-1] if self._handlers else None
        if handler:
            handler(event)

    def _loop(self) -> None:
        device: InputDevice | None = None
        uinput: UInput | None      = None
        was_connected = False
        held: set[int] = set()
        stick = {"x": None, "y": None}

        while True:
            # ── Szukaj pada ───────────────────────────────────────────────
            if device is None:
                held.clear()
                stick["x"] = stick["y"] = None

                if uinput is not None:
                    try:
                        uinput.close()
                    except Exception:
                        pass
                    uinput = None

                for path in list_devices():
                    try:
                        d = InputDevice(path)
                        if not self._is_gamepad(d):
                            d.close()
                            continue
                        d.grab()
                        uinput = UInput.from_device(d, name=VIRTUAL_DEVICE_NAME)
                        device = d
                        logger.info(
                            "Zgrabowano: %s  →  wirtualny: %s",
                            device.name, uinput.device.path,
                        )
                        if not was_connected:
                            was_connected = True
                            self.connected_changed.emit(True)
                        break
                    except Exception as exc:
                        logger.debug("Pominięto urządzenie: %s", exc)

            # ── Czytaj eventy ─────────────────────────────────────────────
            if device:
                try:
                    pending: list[str] = []
                    for ev in device.read_loop():
                        if ev.type == ecodes.EV_SYN:
                            # Koniec paczki – emituj unikalne eventy nawigacyjne
                            seen: set[str] = set()
                            for nav in pending:
                                if nav not in seen:
                                    seen.add(nav)
                                    self._raw.emit(nav)
                            pending.clear()
                            if uinput:
                                uinput.syn()

                        elif ev.type == ecodes.EV_KEY and ev.code == ecodes.BTN_MODE:
                            # BTN_MODE: przechwytuj lokalnie, NIE przekazuj do wirtualnego pada
                            if ev.value == 1:
                                self.btn_mode_pressed.emit()

                        else:
                            # Przekaż do wirtualnego pada
                            if uinput:
                                uinput.write(ev.type, ev.code, ev.value)
                            self._translate(ev, held, stick, pending)

                except OSError:
                    logger.info("Pad odłączony")
                    device = None
                    was_connected = False
                    self.connected_changed.emit(False)
            else:
                time.sleep(1)

    def _translate(self, ev, held: set[int], stick: dict, pending: list) -> None:
        if ev.type == ecodes.EV_KEY:
            if ev.value == 1:
                held.add(ev.code)
                if ev.code == ecodes.BTN_SOUTH:
                    self._raw.emit("select")
                elif ev.code == ecodes.BTN_EAST:
                    self._raw.emit("cancel")
                elif ev.code == ecodes.BTN_WEST:
                    self._raw.emit("close")
                elif ev.code == ecodes.BTN_START and ecodes.BTN_SELECT in held:
                    self.btn_mode_pressed.emit()
            elif ev.value == 0:
                held.discard(ev.code)

        elif ev.type == ecodes.EV_ABS:
            if ev.code == ecodes.ABS_HAT0X:
                if ev.value == -1:
                    stick["x"] = "left";  pending.append("left")
                elif ev.value == 1:
                    stick["x"] = "right"; pending.append("right")
                else:
                    stick["x"] = None
            elif ev.code == ecodes.ABS_HAT0Y:
                if ev.value == -1:
                    stick["y"] = "up";    pending.append("up")
                elif ev.value == 1:
                    stick["y"] = "down";  pending.append("down")
                else:
                    stick["y"] = None
            elif ev.code == ecodes.ABS_X:
                self._handle_stick_axis(ev.value, "x", "left", "right", stick, pending)
            elif ev.code == ecodes.ABS_Y:
                self._handle_stick_axis(ev.value, "y", "up", "down", stick, pending)

    def _handle_stick_axis(
        self,
        value: int,
        axis: str,
        neg_event: str,
        pos_event: str,
        stick: dict,
        pending: list,
    ) -> None:
        if value < -STICK_THRESHOLD and stick[axis] != neg_event:
            stick[axis] = neg_event
            pending.append(neg_event)
        elif value > STICK_THRESHOLD and stick[axis] != pos_event:
            stick[axis] = pos_event
            pending.append(pos_event)
        elif abs(value) < STICK_RESET:
            stick[axis] = None

    @staticmethod
    def _is_gamepad(device: InputDevice) -> bool:
        try:
            caps = device.capabilities()
            if ecodes.EV_KEY not in caps:
                return False
            keys = caps[ecodes.EV_KEY]
            gamepad_buttons = [
                ecodes.BTN_SOUTH, ecodes.BTN_EAST,
                ecodes.BTN_NORTH, ecodes.BTN_WEST,
                ecodes.BTN_START, ecodes.BTN_SELECT,
            ]
            has_hat = (
                ecodes.EV_ABS in caps
                and any(ax in caps[ecodes.EV_ABS]
                        for ax in [ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y])
            )
            return (
                any(b in keys for b in gamepad_buttons) or has_hat
            ) and ecodes.KEY_A not in keys
        except Exception:
            return False
