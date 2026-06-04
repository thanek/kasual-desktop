"""
Testy TileBar — guard sygnatury (zapobiega resetowi animacji marquee)
oraz emisja sygnału windows_changed (w tym przy pustej liście okien).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock

from desktop.tile_bar import TileBar


def _win(id_: str, title: str = "App") -> dict:
    """Minimalny słownik okna — pid=0 omija getpgid i sprawdzenia AppManagera."""
    return {'id': id_, 'title': title, 'pid': 0, 'desktopFile': '', 'resourceClass': ''}


@pytest.fixture
def app_manager():
    mgr = MagicMock()
    mgr.all_running_pids.return_value = []
    mgr.is_running.return_value = False
    mgr.running_idxs.return_value = []
    return mgr


@pytest.fixture
def bar(qapp, app_manager):
    return TileBar(apps=[], app_manager=app_manager)


# ── Guard sygnatury ────────────────────────────────────────────────────────────

class TestSignatureGuard:
    """Identyczna lista okien nie może burzyć i budować kafli od nowa —
    to był korzeń problemu resetowania animacji marquee przy każdym 3-sekundowym
    odświeżeniu listy okien przez KWin."""

    def test_pierwsze_wywolanie_buduje_kafel(self, bar):
        bar.update_windows([_win("1")])
        assert len(bar._dynamic_tiles) == 1

    def test_identyczne_wywolanie_nie_przebudowuje(self, bar):
        bar.update_windows([_win("1", "Długa nazwa")])
        original_tile = bar._dynamic_tiles[0][2]

        bar.update_windows([_win("1", "Długa nazwa")])  # ta sama sygnatura

        assert bar._dynamic_tiles[0][2] is original_tile   # ten sam obiekt AppTile

    def test_zmiana_tytulu_wywoluje_przebudowe(self, bar):
        bar.update_windows([_win("1", "Stary tytuł")])
        original_tile = bar._dynamic_tiles[0][2]

        bar.update_windows([_win("1", "Nowy tytuł")])   # inna sygnatura

        assert bar._dynamic_tiles[0][2] is not original_tile

    def test_identyczne_wywolanie_nie_emituje_sygnalu(self, bar):
        bar.update_windows([_win("1")])

        received = []
        bar.windows_changed.connect(lambda: received.append(1))
        bar.update_windows([_win("1")])   # bez zmian

        assert received == []


# ── Emisja windows_changed ─────────────────────────────────────────────────────

class TestWindowsChangedSignal:
    """windows_changed musi być emitowany przy każdej prawdziwej przebudowie —
    w tym przy przejściu do pustej listy, żeby Desktop._check_active_dyn_gone
    uruchomił się gdy ostatnie otwarte okno zostanie zamknięte."""

    def test_emitowany_gdy_okna_dodane(self, bar):
        received = []
        bar.windows_changed.connect(lambda: received.append(1))

        bar.update_windows([_win("1")])

        assert received == [1]

    def test_emitowany_gdy_ostatnie_okno_zamkniete(self, bar):
        bar.update_windows([_win("1")])   # punkt startowy

        received = []
        bar.windows_changed.connect(lambda: received.append(1))
        bar.update_windows([])            # ostatnie okno zniknęło

        assert received == [1]

    def test_emitowany_gdy_okno_zastapione(self, bar):
        bar.update_windows([_win("1")])

        received = []
        bar.windows_changed.connect(lambda: received.append(1))
        bar.update_windows([_win("2")])   # inne okno

        assert received == [1]

    def test_dynamiczne_kafle_czyszczone_przy_pustej_liscie(self, bar):
        bar.update_windows([_win("1")])
        bar.update_windows([])

        assert bar._dynamic_tiles == []
