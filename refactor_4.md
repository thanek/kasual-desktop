# Plan refactoringu pakietu `domain` — SOLID / DRY / KISS

## Stan obecny

Analiza objęła wszystkie moduły w `src/domain/`:
`menu/`, `shared/`, `notifications/`, `system/`, `lifecycle/`, `catalog/`, `navigation/`, `network/`, `provisioning/`, `shell/`.

---

## 1. DRY — eliminacja duplikacji

### 1.1 `Volume` i `Brightness` — niemal identyczne(value objects z drobnymi różnicami zakresu)

**Pliki:**
- `domain/system/volume.py:9–20`
- `domain/system/brightness.py:14–26`

**Problem:** niemal ten sam kod z trzema różnicami: `STEP`, `DEFAULT`, `MIN`.

**Rekomendacja:** wspólna klasa bazowa / funkcja factory.

```python
# domain/shared/bounded_value.py

@dataclass(frozen=True)
class BoundedValue:
    """Immutable 0–100 value with step and an (optional) non-zero floor."""
    STEP: ClassVar[int] = 1
    DEFAULT: ClassVar[int] = 50
    MIN: ClassVar[int] = 0
    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", max(self.MIN, min(100, self.value)))

    def adjusted(self, delta: int) -> "BoundedValue":
        return dataclass_replace(self, value=self.value + delta)
```

`Volume` i `Brightness` stają się prostymi nadpisaniami klasy:

```python
@dataclass(frozen=True)
class Volume(BoundedValue):
    STEP = 5
    DEFAULT = 50
    MIN = 0

@dataclass(frozen=True)
class Brightness(BoundedValue):
    STEP = 10
    DEFAULT = 70
    MIN = 5
```

**Uwaga:** `dataclass_replace` wymaga Python 3.13+ lub `copy.replace()` na starszych wersjach.

---

### 1.2 Globalny stan mutowalny w `i18n`

**Plik:** `domain/shared/i18n.py:31–41`

**Problem:** ukryta zależność przez zmienną globalną `_active`. Moduły wywołujące `translate()` zależą od tego, że composition root wcześniej wywoła `use()`.

**Rekomendacja:** wstrzykiwanie przez konstruktor, globalna funkcja pozostaje jako wygodny alias dla przypadków testowych.

```python
class Translator:
    def translate(self, context: str, text: str) -> str: ...

_active: Translator | None = None

def translate(context: str, text: str) -> str:
    return _active.translate(context, text) if _active else text

def use(translator: Translator | None) -> None:
    global _active
    _active = translator
```

To już istnieje — **uwaga: zachować obecną strukturę**, globalny stan jest tu uzasadniony (singleton service locator, świadomy projekt). Drobna uwaga: `use()` powinno być wywoływane dokładnie raz na początku aplikacji. Dodać `assert _active is not None` w `translate()` jeśli chcemy fail-fast w razie pomyłki.

---

## 2. SRP — rozbicie klas zbyt dużych / spełniających wiele odpowiedzialności

### 2.1 `AppLifecycle` (350 linii)

**Plik:** `domain/lifecycle/app_lifecycle.py`

**Odpowiedzialności:**
1. Launch / restore
2. Close z procedurą potwierdzenia
3. Exit handling (`on_app_finished`, `on_app_launch_failed`)
4. Focus / reactivation (`on_focus_gained`, `reactivate_desktop`, `restore_desktop_view`)
5. Window arrangement
6. Gamepad handler push/pop

**Rekomendacja:** wydzielić domenowych "use-case'owych" collaboratorów wewnętrznych, ale NIE rozbudowywać fabryki — jedna klasa trzymająca cały przepływ życia aplikacji jest akceptowalna, o ile współpracownicy są dobrze wydzieleni. W tym przypadku współpracownicy SĄ dobrze wydzieleni (`ForegroundInspector`, `WindowManager`, `ProcessManager`, itp.), więc `AppLifecycle` pełni rolę Application Coordinator — to prawidłowy wzorzec.

**Drobna ekstrakcja (opcjonalna, niski priorytet):**
- `_raise_app` + `arrange_windows` → `WindowArranger` (klasa pomocnicza przyjmująca `WindowManager` + `ProcessManager`)
- procedurę confirm/cancel z `request_close_app` → `CloseConfirmation` (wyizolowana logika closures)

---

### 2.2 `App` (237 linii)

**Plik:** `domain/catalog/app.py`

**Odpowiedzialności:**
1. Data model (pola)
2. Parsing z desktop entry (`from_desktop_entry`)
3. Serialization do desktop entry (`to_desktop_entry`)
4. Computed properties (`steam_app_id`, `window_match_keys`, `is_game`)

**Rekomendacja:** SRP nie jest tu naruszone — każda z tych 4 odpowiedzialności dotyczy tego samego obiektu domenowego (App). Rozbijanie jej na osobne klasy byłoby overkill. Jedyna potencjalna ekstrakcja:

- `steam_app_id` / `window_match_keys` → helper w `domain/catalog/steam.py` (ale to tylko 30 linii kodu, nie wart osobnego modułu)

**KISS verdict:** zachować obecną strukturę `App`. Ewentualnie dodać `__slots__` dla zmniejszenia overheadu pamięciowego (Immutable dataclass + dużo instancji).

---

### 2.3 `FocusNavigator` (123 linii)

**Plik:** `domain/navigation/focus_navigator.py`

**Odpowiedzialności:**
1. Focus mode state (TILES / TOPBAR)
2. Top-bar selection index
3. Navigation event translation (handle_pad)
4. Render coordination
5. Mouse hover delegation

**Rekomendacja:** klasa jest dobrze spasowana. Opcjonalna ekstrakcja:

- event → mode mapping → helper method `_handle_tiles_event()` / `_handle_topbar_event()` dla czytelności (ale kod jest prosty, nie ma duplikacji)

---

## 3. ISP — dekompozycja protokołów

### 3.1 `TileBarView` — "służy dwóm klientom"

**Plik:** `domain/lifecycle/tile_bar_view.py`

```python
class TileBarView(Protocol):
    """The tile bar as the lifecycle touches it (TileBar): running-status display
    and dynamic-window presence queries. A narrower role-interface than
    navigation's TileFocusView (ISP); TileBar satisfies both."""
```

**Problem:** protokół "spełnia oba" — lifecycle i navigation.

**Rekomendacja:** sprawdzić, czy faktycznie `TileFocusView` (z `navigation/bar_views.py`) i `TileBarView` mogą być rozdzielone. Jeśli tak — rozdzielić. Jeśli nie — usunąć komentarz i pozostawić jako intentional join.

---

### 3.2 `DesktopControl` — dziedziczenie protokołu

**Plik:** `domain/shell/desktop_control.py:9`

```python
class DesktopControl(SessionView, Protocol):
```

**Problem:** niejawne rozszerzanie interfejsu przez dziedziczenie.

**Rekomendacja:** zamiast inheritance, zdefiniować pełny protokół lub composition:

```python
class DesktopControl(Protocol):
    def show_fullscreen(self) -> None: ...
    def hide_view(self) -> None: ...
    def activate(self) -> None: ...
    def is_visible(self) -> bool: ...
    # session methods re-declared explicitly:
    def resume(self) -> None: ...
    def hide(self) -> None: ...
```

---

## 4. DODATKOWE REFACTORINGI (KISS / DRY)

### 4.1 `cursor_base.py` + `cursor.py` + `grid_cursor.py` — dobry istniejący design

**Komentarz:** Ta trójka jest wzorcowym przykładem zastosowania Template Method + Strategy. `Cursor` to abstract base z hook method `_destination()`. Zachować bez zmian.

---

### 4.2 `window_rules.py` — duplikacja Steam logic

**Plik:** `domain/catalog/window_rules.py:80–81`

```python
if app.steam_app_id is not None:
    return any(w.matches_app(app) for w in windows)
```

Ta sama logika pojawia się w `app_lifecycle.py:178` (`app.steam_app_id is None`).

**Rekomendacja:** wydzielić do metody na klasie `App`:

```python
# w domain/catalog/app.py
def matches_window(self, windows: Sequence[Window]) -> bool:
    return any(w.matches_app(self) for w in windows)
```

Wówczas `is_app_running` staje się:
```python
if app.steam_app_id is not None:
    return app.matches_window(windows)
```

---

### 4.3 Usunąć martwy kod / TODO

Nie znaleziono jawnych TODO w analizowanych plikach. Warto przed finalnym refactoringiem przeprowadzić `grep -n "TODO\|FIXME\|XXX\|HACK"` w całym `domain/`.

---

## 5. PRIORYTETY — harmonogram

| Priorytet | Zadanie | Plik | Effort |
|-----------|---------|------|--------|
| 🔴 Wysoki | Ekstrakcja `BoundedValue` base class | `domain/system/volume.py`, `brightness.py` | Low |
| 🔴 Wysoki | Rozdzielenie `DesktopControl` protokołu (ISP) | `domain/shell/desktop_control.py` | Low |
| 🟡 Średni | Ekstrakcja `WindowArranger` helper z `AppLifecycle` | `domain/lifecycle/app_lifecycle.py` | Medium |
| 🟡 Średni | Split `TileBarView` / `TileFocusView` jeśli faktycznie duplikują | `domain/lifecycle/tile_bar_view.py`, `navigation/bar_views.py` | Medium |
| 🟢 Niski | `steam_app_id` helper na `App.matches_window()` | `domain/catalog/app.py`, `window_rules.py` | Low |
| 🟢 Niski | `__slots__` na `App` (pamięć przy wielu instancjach) | `domain/catalog/app.py` | Low |

---

## 6. CO NIE WYMAGA ZMIAN

- **`Cursor` / `MenuCursor` / `GridCursor`** — wzorcowy Template Method, nie ruszać
- **`AppLifecycle`** jako całość — rola Application Coordinator jest prawidłowa
- **`EventEmitter`** — czysty, generyczny, wielokrotnego użytku
- **`NotificationCenter`**, **`Notification`**, **`Window`**, **`NetworkStatus`** — proste, immutable value objects, KISS
- **`window_rules.py`** jako moduł — czyste, pure functions, composable

---

## 7. ZASADY DALSZEJ PRACY

1. Każda zmiana osobno — commit po każdym zakończonym refactoringu
2. Uruchomić istniejące testy po każdej zmianie (jeśli istnieją)
3. Przed zmianami w `AppLifecycle` upewnić się, że testy pokrywają ścieżki launch/close/restore
4. type: ignore tylko tam gdzie Python < 3.13 i `copy.replace` nie istnieje