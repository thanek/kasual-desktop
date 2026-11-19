import os
import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="exec restart")

from infrastructure.linux import session_restart  # noqa: E402
from infrastructure.linux.session_restart import ExecSessionRestart  # noqa: E402


def test_nothing_opened_by_the_old_process_outlives_the_exec():
    read_end, write_end = os.pipe()
    os.set_inheritable(read_end, True)
    restart = ExecSessionRestart(MagicMock())
    restart.restart()
    try:
        with patch.object(session_restart.os, "execv") as execv:
            restart.replace_process_if_requested()
        execv.assert_called_once()
        assert os.get_inheritable(read_end) is False
    finally:
        os.close(read_end)
        os.close(write_end)


def test_stays_put_unless_asked():
    with patch.object(session_restart.os, "execv") as execv:
        ExecSessionRestart(MagicMock()).replace_process_if_requested()
    execv.assert_not_called()
