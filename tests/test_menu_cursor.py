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


class TestSkipNonSelectable:
    """A non-selectable row (e.g. a SEPARATOR in the unified tile menu, §7.3) is
    stepped over and never lands the selection."""

    def _make_with_sep(self, sep_index, n=5, wrap=False):
        cur = MenuCursor(
            count=lambda: n,
            render=MagicMock(),
            on_activate=MagicMock(),
            on_dismiss=MagicMock(),
            feedback=MagicMock(),
            wrap=wrap,
            is_selectable=lambda i: i != sep_index,
        )
        return cur

    def test_down_steps_over_separator(self):
        # items: 0(sel) 1(sep) 2(sel) ...  — down from 0 skips 1, lands on 2.
        cur = self._make_with_sep(sep_index=1)
        cur.handle_pad("down")
        assert cur.index == 2

    def test_up_steps_over_separator(self):
        cur = self._make_with_sep(sep_index=1)
        cur.reset(2)
        cur.handle_pad("up")
        assert cur.index == 0

    def test_clamp_stays_when_only_separators_below(self):
        # items: 0(sel) 1(sel) 2(sep) 3(sep) 4(sep) — down from 1 finds nothing → stay.
        cur = MenuCursor(
            count=lambda: 5,
            render=MagicMock(), on_activate=MagicMock(), on_dismiss=MagicMock(),
            feedback=MagicMock(), wrap=False,
            is_selectable=lambda i: i < 2,
        )
        cur.reset(1)
        cur.handle_pad("down")
        assert cur.index == 1

    def test_wrap_skips_separator_around_the_end(self):
        # wrap mode: 0(sel) 1(sel) 2(sep) — down from 1 wraps over 2 to 0.
        cur = self._make_with_sep(sep_index=2, n=3, wrap=True)
        cur.reset(1)
        cur.handle_pad("down")
        assert cur.index == 0


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
