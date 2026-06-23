"""Metaclass helper so a Qt widget/object can declare it implements a Protocol port.

Combines ``type(QObject)`` with the (private) ``typing._ProtocolMeta`` so a class
that subclasses both a ``QObject`` derivative and a ``Protocol`` port doesn't
raise ``TypeError: metaclass conflict``.
"""

from typing import _ProtocolMeta  # type: ignore[attr-defined]
from PyQt6.QtCore import QObject


class ProtocolQtMeta(type(QObject), _ProtocolMeta):
    """Combined metaclass usable on classes deriving from a Qt base and a Protocol."""