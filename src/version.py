"""Single runtime entry point for Kasual Desktop's version.

The version's source of truth is the git tag.  The build (``make stage``) bakes
the resolved value into ``_version.txt`` next to this module, so the installed
package reports the tag it was built from without needing git at runtime.

When running from a source checkout (no baked file) we derive the version
dynamically from ``git describe``, giving the same output as the Makefile
(e.g. ``0.2.0`` on a tagged commit, ``0.2.0-5-gabcdef`` between tags).  A
`` DEV`` suffix is appended so dev builds are visually distinct.  Only when git
is unavailable do we fall back to the static ``pyproject.toml`` value.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_GIT_DIR = Path(__file__).resolve().parent.parent


def is_packaged() -> bool:
    """True when running from an installed package (has baked _version.txt)."""
    return Path(__file__).with_name("_version.txt").is_file()


def test_api_enabled() -> bool:
    """True when Kasual Desktop and the apps it launches should publish their test
    APIs: requested explicitly, or implied by running from a source checkout."""
    return os.environ.get("KD_TEST_API") == "1" or not is_packaged()


def _git_describe() -> str | None:
    try:
        tag = (
            subprocess.run(
                ["git", "describe", "--tags"],
                cwd=_GIT_DIR,
                capture_output=True,
                text=True,
                timeout=5,
            )
            .stdout.strip()
        )
        return tag.lstrip("v") if tag else None
    except Exception:
        return None


def get_version() -> str:
    baked = Path(__file__).with_name("_version.txt")
    if baked.is_file():
        return baked.read_text(encoding="utf-8").strip()

    git = _git_describe()
    if git:
        return f"{git} DEV"

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        import tomllib

        return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    except Exception:
        return "0.0.0+unknown"
