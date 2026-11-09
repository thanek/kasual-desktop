"""Tests for WindowsRtssHudControl — the HudControl port over RTSS's runtime
OSD-visibility flag.

Drives the adapter against a fake flags word (the SetFlags seam), asserting how
it reads the on/off state from RTSSHOOKSFLAG_OSD_VISIBLE and how enable/disable
clear/set that single bit while leaving the rest of the word (e.g. the limiter
bit 0x4) untouched. No RTSS / DLL is needed, so these run on any platform.
"""

from domain.system.hud import HUD_OFF
from infrastructure.windows.hud.rtss import (
    RTSSHOOKSFLAG_OSD_VISIBLE,
    WindowsRtssHudControl,
)

_LIMITER_BIT = 0x00000004  # an unrelated runtime flag we must preserve


class _FakeFlags:
    """In-memory stand-in for RTSS's SetFlags word: (word & AND) ^ XOR."""

    def __init__(self, word: int = 0, available: bool = True) -> None:
        self.word = word & 0xFFFFFFFF
        self._available = available

    def available(self) -> bool:
        return self._available

    def read(self) -> int | None:
        return self.word if self._available else None

    def write(self, and_mask: int, xor_mask: int) -> int | None:
        if not self._available:
            return None
        self.word = ((self.word & (and_mask & 0xFFFFFFFF)) ^ (xor_mask & 0xFFFFFFFF)) & 0xFFFFFFFF
        return self.word


def _control(word: int = 0, available: bool = True):
    flags = _FakeFlags(word, available)
    return WindowsRtssHudControl(flags=flags), flags


class TestAvailability:
    def test_unavailable_without_rtss(self):
        control, _ = _control(available=False)
        assert control.is_available() is False

    def test_available_with_rtss(self):
        control, _ = _control(available=True)
        assert control.is_available() is True


def _shown(control) -> bool:
    return not control.level().is_off


def _show(control) -> None:
    control.set_level(control.level().at(1))


def _hide(control) -> None:
    control.set_level(control.level().at(HUD_OFF))


class TestState:
    def test_shown_when_osd_bit_set(self):
        control, _ = _control(word=RTSSHOOKSFLAG_OSD_VISIBLE)
        assert _shown(control) is True

    def test_hidden_when_osd_bit_clear(self):
        control, _ = _control(word=_LIMITER_BIT)
        assert _shown(control) is False

    def test_hidden_when_unavailable(self):
        control, _ = _control(word=RTSSHOOKSFLAG_OSD_VISIBLE, available=False)
        assert _shown(control) is False

    def test_offers_a_single_detail_level(self):
        control, _ = _control(word=RTSSHOOKSFLAG_OSD_VISIBLE)
        assert control.level().most_detailed == 1


class TestShow:
    def test_sets_osd_bit(self):
        control, flags = _control(word=0)
        _show(control)
        assert _shown(control) is True
        assert flags.word & RTSSHOOKSFLAG_OSD_VISIBLE

    def test_preserves_other_flags(self):
        control, flags = _control(word=_LIMITER_BIT)
        _show(control)
        assert flags.word == (_LIMITER_BIT | RTSSHOOKSFLAG_OSD_VISIBLE)

    def test_idempotent_when_already_on(self):
        control, flags = _control(word=_LIMITER_BIT | RTSSHOOKSFLAG_OSD_VISIBLE)
        _show(control)
        assert flags.word == (_LIMITER_BIT | RTSSHOOKSFLAG_OSD_VISIBLE)


class TestHide:
    def test_clears_osd_bit(self):
        control, flags = _control(word=RTSSHOOKSFLAG_OSD_VISIBLE)
        _hide(control)
        assert _shown(control) is False
        assert not (flags.word & RTSSHOOKSFLAG_OSD_VISIBLE)

    def test_preserves_other_flags(self):
        control, flags = _control(word=_LIMITER_BIT | RTSSHOOKSFLAG_OSD_VISIBLE)
        _hide(control)
        assert flags.word == _LIMITER_BIT

    def test_idempotent_when_already_off(self):
        control, flags = _control(word=_LIMITER_BIT)
        _hide(control)
        assert flags.word == _LIMITER_BIT
