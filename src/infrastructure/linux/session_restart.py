"""Restart Kasual Desktop in place: the same process, so the same PID — the
launcher keeps waiting on it and launched games keep their parent."""

import logging
import os
import sys

from PyQt6.QtCore import QCoreApplication

from domain.display.relaunch import SessionRestart

logger = logging.getLogger(__name__)


class ExecSessionRestart(SessionRestart):
    def __init__(self, app: QCoreApplication) -> None:
        self._app = app
        self._requested = False

    def restart(self) -> None:
        self._requested = True
        self._app.quit()

    def replace_process_if_requested(self) -> None:
        if not self._requested:
            return
        logger.info("Restarting Kasual Desktop")
        logging.shutdown()
        os.execv(sys.executable, [sys.executable, *sys.argv])
