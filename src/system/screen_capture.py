"""Grab a still of the current screen for use as an overlay background.

On Wayland, Qt's QScreen.grabWindow() returns an empty pixmap and the
org.kde.KWin.ScreenShot2 D-Bus interface refuses callers that lack the
X-KDE-DBUS-Restricted-Interfaces authorization. Spectacle ships with that
authorization, so we shell out to it. The capture is synchronous (~0.4s);
callers must invoke it *before* changing what is on screen (e.g. before
minimizing a running app), so the still reflects the live screen.
"""

import logging
import os
import shutil
import subprocess
import tempfile

from PyQt6.QtGui import QPixmap

logger = logging.getLogger(__name__)

_OUTPUT = os.path.join(tempfile.gettempdir(), "kasual_overlay_bg.png")
_TIMEOUT_S = 3


def capture_screen() -> QPixmap | None:
    """Return a still of the entire desktop, or None if capture failed.

    Uses `spectacle -b -n -f`: background mode, no notification, full screen.
    """
    if shutil.which("spectacle") is None:
        logger.warning("DBG capture_screen: spectacle not found on PATH")
        return None

    try:
        result = subprocess.run(
            ["spectacle", "-b", "-n", "-f", "-o", _OUTPUT],
            capture_output=True,
            timeout=_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        logger.warning("DBG capture_screen: spectacle timed out")
        return None
    except OSError as exc:
        logger.warning("DBG capture_screen: spectacle failed: %s", exc)
        return None

    if result.returncode != 0 or not os.path.exists(_OUTPUT):
        logger.warning(
            "DBG capture_screen: spectacle rc=%s stderr=%s",
            result.returncode, result.stderr.decode(errors="replace").strip(),
        )
        return None

    pixmap = QPixmap(_OUTPUT)
    try:
        os.remove(_OUTPUT)
    except OSError:
        pass

    if pixmap.isNull():
        logger.warning("DBG capture_screen: loaded pixmap is null")
        return None
    return pixmap
