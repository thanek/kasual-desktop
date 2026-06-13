"""Qt backend for the `support.i18n.Translator` port.

Resolves strings through Qt's translation system (the QTranslator installed on
the QApplication, loaded from locale/kasual_*.qm). Installed at the composition
root via `support.i18n.use(QtTranslator())`.
"""

import logging

from PyQt6.QtCore import QCoreApplication, QLocale, QTranslator

from support import i18n
from support.i18n import Translator

logger = logging.getLogger(__name__)


class QtTranslator(Translator):
    def translate(self, context: str, text: str) -> str:
        return QCoreApplication.translate(context, text)


def install_translations(app, locale_dir: str) -> None:
    """Load the system-locale ``.qm`` into ``app`` and route ``support.i18n``
    through Qt — the translation setup every QApplication in the project needs
    (the main process and the standalone log-viewer process both call this).

    ``locale_dir`` is supplied by the caller (which knows its own location), so
    this stays free of assumptions about the source-tree layout.
    """
    translator = QTranslator(app)
    if translator.load(QLocale.system(), "kasual", "_", locale_dir, ".qm"):
        app.installTranslator(translator)
        logger.info("Loaded translation: %s", QLocale.system().name())
    else:
        logger.info("No .qm file for localization: %s", QLocale.system().name())
    # Route the app's `support.i18n.translate` calls through Qt now that the
    # QApplication (and any QTranslator) exists.
    i18n.use(QtTranslator())
