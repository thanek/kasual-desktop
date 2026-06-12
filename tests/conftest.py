import os
import sys
from unittest.mock import patch

# Offscreen backend — działa bez wyświetlacza (CI, Xvfb, itp.)
# Jeśli zmienna jest już ustawiona (np. DISPLAY), nie nadpisujemy.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Dodaj katalog główny projektu do ścieżki importu
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest


@pytest.fixture(autouse=True)
def silence_sounds():
    """Wycisza odtwarzanie dźwięków (SoundFeedback) we wszystkich testach."""
    with patch("infrastructure.audio.feedback.SoundFeedback.play"):
        yield


@pytest.fixture
def mock_gamepad(qapp):
    """
    GamepadWatcher bez uruchamiania wątku _loop.

    Patchujemy threading.Thread zanim __init__ go wywoła,
    więc wątek evdev nigdy nie startuje — testy są w pełni izolowane
    od sprzętu i uprawnień do UInput.
    """
    with patch("infrastructure.input.gamepad_watcher.threading.Thread"):
        from infrastructure.input.gamepad_watcher import GamepadWatcher
        gw = GamepadWatcher()
    return gw
