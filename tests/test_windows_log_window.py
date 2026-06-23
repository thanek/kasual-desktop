"""Tests for LogWindow — single-instance in-process log viewer.

The Windows log viewer is an in-process QWidget (no subprocess), so the tests
focus on lazy-build lifecycle and duplicate suppression.

No ctypes/Win32 mocking needed: LogWindow only imports Qt + the shared
LogProvider/FileLogSource/Lo viewer widget, all of which work cross-platform.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def log_file(tmp_path):
    f = tmp_path / "kasual.log"
    f.write_text("line1\nline2\n")
    return str(f)


class TestOpen:
    def test_lazy_builds_viewer_on_first_call(self, qapp, log_file):
        from infrastructure.windows.qt.log_window import LogWindow

        lw = LogWindow(log_file=log_file)
        assert lw._viewer is None

        lw.open()

        assert lw._viewer is not None
        assert lw._viewer.isVisible()

    def test_reuses_viewer_on_second_call(self, qapp, log_file):
        from infrastructure.windows.qt.log_window import LogWindow

        lw = LogWindow(log_file=log_file)
        lw.open()
        viewer = lw._viewer

        lw.open()

        assert lw._viewer is viewer
        assert lw._viewer.isVisible()

    def test_calls_show_raise_activate(self, qapp, log_file):
        from infrastructure.windows.qt.log_window import LogWindow

        lw = LogWindow(log_file=log_file)
        lw._viewer = MagicMock()
        lw.open()
        lw._viewer.show.assert_called_once()
        lw._viewer.raise_.assert_called_once()
        lw._viewer.activateWindow.assert_called_once()


class TestClose:
    def test_closes_and_deletes_viewer(self, qapp, log_file):
        from infrastructure.windows.qt.log_window import LogWindow

        lw = LogWindow(log_file=log_file)
        lw.open()
        viewer = lw._viewer

        lw.close()

        assert lw._viewer is None

    def test_noop_when_already_closed(self, qapp, log_file):
        from infrastructure.windows.qt.log_window import LogWindow

        lw = LogWindow(log_file=log_file)
        lw.close()


class TestOpenAfterClose:
    def test_creates_new_viewer(self, qapp, log_file):
        from infrastructure.windows.qt.log_window import LogWindow

        lw = LogWindow(log_file=log_file)
        lw.open()
        old_viewer = lw._viewer
        lw.close()

        lw.open()

        assert lw._viewer is not None
        assert lw._viewer is not old_viewer
        assert lw._viewer.isVisible()
