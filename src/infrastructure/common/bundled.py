"""Resolve paths to bundled resources shipped at the project root.

Top-level asset directories (``fonts/``, ``sounds/``, ``apps/``, ``locale/``)
live next to ``pyproject.toml`` at the repository root. Anchoring to that
marker file rather than counting ``Path.parents`` indices keeps these
resolves stable when an infrastructure module is moved between packages.
"""

from pathlib import Path

_MARKER = "pyproject.toml"


def project_root() -> Path:
    """The repository root, located by walking up to the ``pyproject.toml`` marker."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / _MARKER).is_file():
            return parent
    raise FileNotFoundError(f"Could not locate {_MARKER} above {here}")


def bundled_dir(name: str) -> Path:
    """A top-level asset directory at the project root (e.g. ``bundled_dir('fonts')``)."""
    return project_root() / name