"""Qt backend for the `support.i18n.Translator` port.

Resolves strings through Qt's translation system (the QTranslator installed on
the QApplication, loaded from locale/kasual_*.qm). Installed at the composition
root via `support.i18n.use(QtTranslator())`.
"""

from PyQt6.QtCore import QCoreApplication

from support.i18n import Translator


class QtTranslator(Translator):
    def translate(self, context: str, text: str) -> str:
        return QCoreApplication.translate(context, text)
