"""Single runtime entry point for Kasual Desktop's version.

The version's source of truth is the git tag. The build (``make stage``) bakes
the resolved value into ``_version.txt`` next to this module, so the installed
package reports the tag it was built from without needing git at runtime. When
running from a source checkout (no baked file) we fall back to ``pyproject.toml``
so dev runs still report something sensible.
"""

from pathlib import Path


def get_version() -> str:
    baked = Path(__file__).with_name("_version.txt")
    if baked.is_file():
        return baked.read_text(encoding="utf-8").strip()

    # Dev checkout: read the static fallback from pyproject.toml at the repo root.
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        import tomllib

        return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    except Exception:
        return "0.0.0+unknown"
