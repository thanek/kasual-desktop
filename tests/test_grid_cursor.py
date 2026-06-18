"""Tests for GridCursor — the 2-D grid navigation state machine.

Pure logic, no Qt/sound. Items are a flat list wrapped into rows of ``columns``;
covers left/right (column within row), up/down (row within column), both with
wrap, the short-last-row clamp, select, dismiss, hover and the render/feedback
side effects.
"""

from unittest.mock import MagicMock

from domain.menu.grid_cursor import GridCursor


def _make(n=6, columns=3):
    render      = MagicMock()
    on_activate = MagicMock()
    on_dismiss  = MagicMock()
    feedback    = MagicMock()
    cur = GridCursor(
        count=lambda: n,
        columns=columns,
        render=render,
        on_activate=on_activate,
        on_dismiss=on_dismiss,
        feedback=feedback,
    )
    return cur, render, on_activate, on_dismiss, feedback


class TestBasics:
    def test_starts_at_zero(self):
        cur, *_ = _make()
        assert cur.index == 0

    def test_reset_sets_index_and_renders(self):
        cur, render, *_ = _make()
        cur.reset(4)
        assert cur.index == 4
        render.assert_called_with(4)


class TestHorizontal:
    def test_right_moves_within_row(self):
        cur, render, _, _, fb = _make(n=6, columns=3)
        cur.handle_pad("right")
        assert cur.index == 1
        render.assert_called_with(1)
        fb.play.assert_called_once()

    def test_left_moves_within_row(self):
        cur, *_ = _make(n=6, columns=3)
        cur.reset(2)
        cur.handle_pad("left")
        assert cur.index == 1

    def test_right_wraps_at_row_end(self):
        cur, *_ = _make(n=6, columns=3)
        cur.reset(2)               # last column of row 0
        cur.handle_pad("right")
        assert cur.index == 0      # wraps back to the row's first column

    def test_left_wraps_to_row_end(self):
        cur, *_ = _make(n=6, columns=3)
        cur.reset(3)               # first column of row 1
        cur.handle_pad("left")
        assert cur.index == 5      # wraps to that row's last column

    def test_horizontal_stays_inside_short_last_row(self):
        cur, *_ = _make(n=8, columns=3)   # rows [0,1,2] [3,4,5] [6,7]
        cur.reset(6)
        cur.handle_pad("right")
        assert cur.index == 7
        cur.handle_pad("right")
        assert cur.index == 6      # wraps within the 2-wide last row


class TestVertical:
    def test_down_moves_to_next_row_same_column(self):
        cur, *_ = _make(n=6, columns=3)
        cur.reset(1)
        cur.handle_pad("down")
        assert cur.index == 4

    def test_up_moves_to_previous_row_same_column(self):
        cur, *_ = _make(n=6, columns=3)
        cur.reset(5)
        cur.handle_pad("up")
        assert cur.index == 2

    def test_down_wraps_to_top(self):
        cur, *_ = _make(n=6, columns=3)
        cur.reset(3)               # row 1, col 0
        cur.handle_pad("down")
        assert cur.index == 0

    def test_up_wraps_to_bottom(self):
        cur, *_ = _make(n=6, columns=3)
        cur.reset(0)
        cur.handle_pad("up")
        assert cur.index == 3

    def test_down_into_short_last_row_clamps_to_last_item(self):
        cur, *_ = _make(n=8, columns=3)   # last row [6,7] lacks column 2
        cur.reset(2)
        cur.handle_pad("down")
        assert cur.index == 5
        cur.handle_pad("down")
        assert cur.index == 7      # column 2 missing in last row → last item


class TestActivateDismiss:
    def test_select_activates_current(self):
        cur, _, on_activate, _, _ = _make()
        cur.reset(2)
        cur.handle_pad("select")
        on_activate.assert_called_once_with(2)

    def test_cancel_dismisses(self):
        cur, _, _, on_dismiss, _ = _make()
        cur.handle_pad("cancel")
        on_dismiss.assert_called_once()

    def test_close_dismisses(self):
        cur, _, _, on_dismiss, _ = _make()
        cur.handle_pad("close")
        on_dismiss.assert_called_once()


class TestHover:
    def test_hover_selects_and_renders(self):
        cur, render, _, _, fb = _make()
        cur.hover(4)
        assert cur.index == 4
        render.assert_called_with(4)
        fb.play.assert_called_once()

    def test_hover_same_index_is_noop(self):
        cur, render, _, _, fb = _make()
        cur.reset(2)
        render.reset_mock()
        cur.hover(2)
        render.assert_not_called()
        fb.play.assert_not_called()


class TestEdgeCases:
    def test_no_move_when_target_equals_current(self):
        cur, render, _, _, fb = _make(n=1, columns=3)
        cur.handle_pad("right")    # single item → stays put, no render/feedback
        assert cur.index == 0
        render.assert_not_called()
        fb.play.assert_not_called()

    def test_empty_palette_does_not_crash(self):
        cur, *_ = _make(n=0, columns=3)
        cur.handle_pad("right")
        cur.handle_pad("down")
        assert cur.index == 0
