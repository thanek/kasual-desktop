"""Tests for reading the session's environment: the parsing, and the sessions
where there is no manager to answer. No real one is ever called."""

import subprocess
from unittest.mock import patch

from infrastructure.linux.session_env import session_environ

_RUN = "infrastructure.linux.session_env.subprocess.run"


def _shows(block: str):
    return patch(_RUN, return_value=subprocess.CompletedProcess((), 0, block, ""))


def _fails(exc: Exception):
    return patch(_RUN, side_effect=exc)


class TestSessionEnviron:
    def test_reads_the_managers_block(self):
        with _shows("LANG=en_GB.UTF-8\nMANGOHUD=1\n"):
            assert session_environ() == {"LANG": "en_GB.UTF-8", "MANGOHUD": "1"}

    def test_keeps_values_that_hold_an_equals_sign(self):
        with _shows("XDG_DATA_DIRS=/usr/share:/a=b\n"):
            assert session_environ()["XDG_DATA_DIRS"] == "/usr/share:/a=b"

    def test_skips_lines_that_assign_nothing(self):
        with _shows("MANGOHUD=1\nnonsense\n\n"):
            assert session_environ() == {"MANGOHUD": "1"}

    def test_an_empty_value_is_still_set(self):
        with _shows("MANGOHUD=\n"):
            assert session_environ() == {"MANGOHUD": ""}

    def test_a_session_without_systemd_reads_as_empty(self):
        with _fails(FileNotFoundError()):
            assert session_environ() == {}

    def test_a_manager_that_does_not_answer_reads_as_empty(self):
        with _fails(subprocess.TimeoutExpired((), 5)):
            assert session_environ() == {}

    def test_a_refusal_reads_as_empty(self):
        with _fails(subprocess.CalledProcessError(1, ())):
            assert session_environ() == {}
