"""Tests that a fatal signal leaves a stack behind in the log.

A segfault inside Qt or a C extension kills the process before any Python handler
runs, so without this the log just stops mid-session and says only that Kasual
died — never where.
"""

import faulthandler
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from session import setup_logging

_SRC = Path(__file__).resolve().parent.parent / "src"


@pytest.fixture
def armed(tmp_path):
    """Disarm afterwards, so a later test is not left writing crash traces into a
    temporary directory that has since been removed."""
    was_enabled = faulthandler.is_enabled()
    yield tmp_path
    if not was_enabled:
        faulthandler.disable()


def test_arms_the_crash_handler(armed):
    setup_logging(armed)
    assert faulthandler.is_enabled()


def test_a_segfault_writes_its_stack_into_the_log(tmp_path):
    # In a subprocess: what is under test is what survives a process dying of
    # SIGSEGV, which cannot be asserted from inside this one.
    script = textwrap.dedent(f"""
        import ctypes, sys
        sys.path.insert(0, {str(_SRC)!r})
        from pathlib import Path
        from session import setup_logging
        setup_logging(Path({str(tmp_path)!r}))
        ctypes.string_at(0)
    """)
    result = subprocess.run([sys.executable, "-c", script],
                            capture_output=True, timeout=60)
    assert result.returncode != 0

    written = (tmp_path / "kasual.log").read_text(encoding="utf-8")
    assert "Fatal Python error" in written
    assert "Segmentation fault" in written
    assert "string_at" in written   # the frame that actually crashed
