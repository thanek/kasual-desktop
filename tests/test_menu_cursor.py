"""Tests for MenuCursor — the vertical menu navigation state machine.

Pure logic, no Qt/sound. Covers both modes (clamp / wrap), select, dismiss,
hover and the feedback/render side effects.
"""

from unittest.mock import MagicMock

from domain.menu.cursor import MenuCursor


def _make(n=3, wrap=False):
    render      = MagicMock()
    on_activate = MagicMock()
    on_dismiss  = MagicMock()
    feedback    = MagicMock()
    cur = MenuCursor(
        count=lambda: n,
        render=render,
        on_activate=on_activate,
        on_dismiss=on_dismiss,
        feedback=feedback,
        wrap=wrap,
    )
    return cur, render, on_activate, on_dismiss, feedback


class TestBasics:
    def test_starts_at_zero(self):
        cur, *_ = _make()
        assert cur.index == 0

    def test_reset_sets_index_and_renders(self):
        cur, render, *_ = _make()
        cur.reset(2)
        assert cur.index == 2
        render.assert_called_with(2)


class TestClampMode:
    def test_down_moves(self):
        cur, render, _, _, fb = _make(n=3)
        cur.handle_pad("down")
        assert cur.index == 1
        render.assert_called_with(1)
        fb.play.assert_called_once_with("cursor")

    def test_up_at_top_stays_silent(self):
        cur, render, _, _, fb = _make(n=3)
        cur.handle_pad("up")
        assert cur.index == 0
        render.assert_not_called()
        fb.play.assert_not_called()

    def test_down_at_bottom_stays_silent(self):
        cur, _, _, _, fb = _make(n=2)
        cur.handle_pad("down")   # 0 → 1
        cur.handle_pad("down")   # clamp at 1
        assert cur.index == 1
        assert fb.play.call_count == 1


class TestWrapMode:
    def test_up_wraps_to_last(self):
        cur, _, _, _, fb = _make(n=3, wrap=True)
        cur.handle_pad("up")
        assert cur.index == 2
        fb.play.assert_called_once_with("cursor")

    def test_down_wraps_to_first(self):
        cur, *_ = _make(n=3, wrap=True)
        cur.handle_pad("down")   # 0→1
        cur.handle_pad("down")   # 1→2
        cur.handle_pad("down")   # 2→0
        assert cur.index == 0


class TestSelectDismiss:
    def test_select_activates_current(self):
        cur, _, on_activate, _, _ = _make(n=3)
        cur.handle_pad("down")
        cur.handle_pad("select")
        on_activate.assert_called_once_with(1)

    def test_cancel_dismisses(self):
        cur, _, _, on_dismiss, _ = _make()
        cur.handle_pad("cancel")
        on_dismiss.assert_called_once()

    def test_close_dismisses(self):
        cur, _, _, on_dismiss, _ = _make()
        cur.handle_pad("close")
        on_dismiss.assert_called_once()


class TestHover:
    def test_hover_changes_index_with_feedback(self):
        cur, render, _, _, fb = _make()
        cur.hover(2)
        assert cur.index == 2
        render.assert_called_with(2)
        fb.play.assert_called_once_with("cursor")

    def test_hover_same_index_is_noop(self):
        cur, render, _, _, fb = _make()
        cur.hover(0)
        render.assert_not_called()
        fb.play.assert_not_called()


class TestEmpty:
    def test_move_with_no_items_is_noop(self):
        cur, render, _, _, fb = _make(n=0)
        cur.handle_pad("down")
        assert cur.index == 0
        render.assert_not_called()
        fb.play.assert_not_called()
