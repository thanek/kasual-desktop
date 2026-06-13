# Domain Leaks in Infrastructure

Analiza fragmentów logiki domenowej w pakiecie `infrastructure`, które powinny być wyniesione do `domain`.

---

## 1. `tile_bar.py:199-208` — Definicja „running"

**Plik:** `src/infrastructure/qt/desktop/tile_bar.py`

```python
def is_tile_running(self, idx: int) -> bool:
    if self._app_manager.is_running(idx):
        return True
    if self._last_windows and idx < len(self._apps):
        app = self._apps[idx]
        return any(w.matches_app(app) for w in self._last_windows)
    return False
```

**Opis:** Reguła *„aplikacja jest running jeśli uruchomiona przez AppManager LUB ma widoczne okno w KWinie"* to **definicja domenowa** tego, co oznacza „running". `ProcessManager.is_running()` sprawdza tylko procesy, a warstwa infrastruktury rozszerza tę definicję o dopasowanie okien — bez konsultacji z domeną.

**Priorytet:** Wysoki

**Rozwiązanie:** Przenieść do domeny (np. `window_rules.py:is_tile_running(index, apps, windows, process_manager)`) lub dodać do `ProcessManager` jako rozszerzenie portu.

---

## 2. `desktop.py:287-298` — Reaktywacja desktopu na ActivationChange

**Plik:** `src/infrastructure/qt/desktop/desktop.py`

```python
def changeEvent(self, event) -> None:
    super().changeEvent(event)
    if event.type() == QEvent.Type.ActivationChange:
        if self.isActiveWindow() and self._foreground.is_idle() \
                and self._gamepad.top_handler() is None:
            self._lifecycle.reactivate_desktop()
```

**Opis:** Reguła *„kiedy Kasual odzyskuje focus od zamkniętej aplikacji i nikt nie obsługuje gamepada → przejmij kontrolę"* to **zasada domenowa** o tym, kiedy Desktop powinien reagtywować. Jest już w domenie jako `AppLifecycle.check_active_dyn_gone()`, ale ta ścieżka (edge-triggered na ActivationChange) omija ten mechanizm i wywołuje `reactivate_desktop()` bezpośrednio z Qt event handlera.

**Priorytet:** Średni

**Rozwiązanie:** Przenieść logikę podejmowania decyzji o reaktywacji do domeny (np. do `AppLifecycle`), a infrastruktura powinna tylko sygnalizować zdarzenie „odzyskano focus".

---

## 3. ~~`desktop.py:309-313`~~ — Escape → Home Overlay shortcut ~~done~~

**Plik:** `src/infrastructure/qt/desktop/desktop.py`

~~~python
if (key == Qt.Key.Key_Escape
        and self._nav.in_tiles
        and self._gamepad.top_handler() == self._handle_pad):
    self._gamepad.trigger_btn_mode()
    return True
~~~

**Opis:** Mapowanie Qt keys → domain `Event` (`_KEY_MAP`) jest poprawnie w infrastrukturze. Ale **Escape → trigger_btn_mode w tiles mode bez overlay** to **decyzja nawigacyjna** — specyficzny skrót klawiszowy dla konkretnego stanu domenowego, a nie translacja surowego inputu.

**Priorytet:** Niski

**Rozwiązanie:** Przenieść do `FocusNavigator.handle_pad()` jako dodatkowy event (np. `Event.ESCAPE_TO_HOME`) lub dodać do protokołu `PadControl` metodę `trigger_btn_mode_from_escape()`.

~~Zrobione: dodano `Event.ESCAPE_HOME`, `PadControl.trigger_home()`, logika w `FocusNavigator.handle_pad()`. Event filter redukowany do `inject(Event.ESCAPE_HOME)`.~~

---

## Poprawne miejsca (nie wymagają zmian)

| Miejsce | Co | Dlaczego jest OK |
|---|---|---|
| `window_manager.py:411` | Filtrowanie własnego PID z listy okien | Adapter filtruje własne okno — techniczna konieczność, nie reguła biznesowa |
| `tile_bar.py:385-388` | Konstruowanie `Window` z dynamic-tile state | Adapter dostarcza dane domenowe (pid → Window), nie decyduje o regułach |
| `_KEY_MAP` | Qt keys → domain Event | Translacja surowego inputu — poprawnie w adapterze |
| `gamepad_watcher.py:26-27` | Dead zone thresholds (10000/6000) | Tuning sprzętowy, nie reguła biznesowa |
| `window_manager.py:72` | Filtrowanie okien KWin (skipTaskbar, normalWindow) | Klasyfikacja okien specyficzna dla kompozytora |
