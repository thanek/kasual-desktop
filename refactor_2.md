# Raport: Refactoring pakietu `domain` -- SOLID, DRY, KISS

> Wygenerowano: `kimi-k2.6` · Data: 2026-06-19

---

## Wstęp

Przejrzałem cały pakiet `domain` (61 plikow, ~14 modulow/podpakietow). Ogólny poziom jest bardzo dobry -- architektura portow/adapters, czysta separacja od Qt/evdev, doskonale docstrings. Wiekszosc kodu jest juz SOLID-owa. Ponizej znajduja sie odkryte problemy i konkretne propozycje usprawnien.

---

## 1. [WYSOKI] `domain/lifecycle/app_lifecycle.py` -- God Class (SRP)

**Problem:** Klasa `AppLifecycle` ma 350 linii i laczy zbyt wiele odpowiedzialnosci: launch, restore, zamykanie, exit-handling, focus, reaktywacje, window management. Lamie zasade pojedynczej odpowiedzialnosci (SRP).

**Proponowane rozwiazanie:** Rozbic na mniejsze, wyspecjalizowane koordynatory:

```
domain/lifecycle/launcher.py     -> LaunchCoordinator
domain/lifecycle/closer.py       -> CloseCoordinator
domain/lifecycle/focuser.py      -> DesktopFocuser
```

`AppLifecycle` stanie się fasada (Facade Pattern) delegujaca do wyspecjalizowanych koordynatorow, bez wlasnej logiki biznesowej.

---

## 2. [WYSOKI] `domain/system/actions.py` + `domain/system/action_view.py` -- DRY

**Problem:** Dwie oddzielne struktury definiuja te same akcje systemowe:

- `actions.py`: `ACTIONS = {VOLUME: ..., BRIGHTNESS: ...}` -- logika (co robi)
- `action_view.py`: `PRESENTATION = {VOLUME: ..., BRIGHTNESS: ...}` -- wyglad (jak wyglada)

Przy dodaniu nowej akcji trzeba edytowac **dwa miejsca** -- latwo o rozsynchronizacje i naruszenie DRY.

**Proponowane rozwiazanie:** Jedna struktura zrodlowa:

```python
@dataclass(frozen=True)
class SystemAction:
    key: str
    needs_confirmation: bool
    effect: Callable[[ActionDeps], None]
    label: str
    icon: str
    color: str
    confirm_question: str | None
```

Aktualny `SystemAction` z `actions.py` powinien zawierac opcjonalne pole `ActionView`. `PRESENTATION` i `ACTIONS` to wtedy jeden `dict`.

---

## 3. [ŚREDNI] `domain/system/volume.py` + `domain/system/brightness.py` -- DRY (blizniacze klasy)

**Problem:** Prawie identyczna struktura obu klas:

```python
@dataclass(frozen=True)
class Volume:
    STEP = 5
    DEFAULT = 50
    value: int

@dataclass(frozen=True)
class Brightness:
    STEP = 10
    DEFAULT = 70
    MIN = 5
    value: int
```

**Proponowane rozwiazanie:** Generyczna klasa bazowa lub factory:

```python
# domain/system/ranged_value.py
@dataclass(frozen=True)
class RangedValue:
    value: int
    min_val: ClassVar[int] = 0
    max_val: ClassVar[int] = 100
    step: ClassVar[int] = 5

    def adjusted(self, delta: int) -> Self:
        return type(self)(self.value + delta)

# Volume = RangedValue.with_meta(step=5, default=50)
# Brightness = RangedValue.with_meta(step=10, default=70, min_val=5)
```

Redukuje kod z ~60 do ~20 linii i eliminuje ryzyko rozsynchronizacji logiki clampowania.

---

## 4. [ŚREDNI] `domain/lifecycle/app_lifecycle.py` -- powtorzona logika zamykania okien

**Problem:** `_close_app_windows()` (linie 251-263) i `request_close_app()` (linie 208-249) zawieraja podobna logike zamykania -- rozne sciezki dla `AppTarget` vs `WindowTarget`, rozne sposoby obslugi braku `pid`.

**Proponowane rozwiazanie:** Wyodrebnic `WindowCloser` lub strategie `CloseStrategy`, ktora wybiera odpowiednia sciezke na podstawie typu `Target`.

```python
class CloseStrategy(Protocol):
    def close(self, target: Target) -> None: ...

class AppCloseStrategy:
    def close(self, target: AppTarget) -> None: ...

class WindowCloseStrategy:
    def close(self, target: WindowTarget) -> None: ...
```

---

## 5. [ŚREDNI] `domain/menu/entry.py` -- roznieznosc nazw i nieuzywane stale

**Problem:** `domain.menu.entry` zawiera 12 stalych stringow do roznych menu. Programista musi znac polityke, ktore stringi do ktorego menu. Niektore (np. `UNPIN`) mocno zaleza od kontekstu.

**Proponowane rozwiazanie zgodne z KISS:** Nie ma tu dynamicznej logiki, ale lepiej zgrupowac per menu:

```python
class HomeMenuActions:
    RETURN_TO_APP = "return_to_app"
    CLOSE_APP = "close_app"
    # ...

class TileMenuActions:
    LAUNCH = "launch"
    RESTORE = "restore"
    # ...

class TileManagementActions:
    MOVE = "move"
    CHANGE_COLOR = "change_color"
    # ...
```

---

## 6. [NISKI] `domain/shared/` -- mikro-pakiety z pojedynczymi modulami

**Problem:** `domain/shared/` ma 5 malych modulow (`event_emitter`, `scheduler`, `i18n`, `text`, `feedback`). Kazdy to osobny plik z pojedyncza klasa/konstanta.

**Proponowane rozwiazanie (opcjonalne):** Jesli w planach jest wiecej "shared utilities", mozna rozwazyc polaczenie w jeden modul `domain/shared/core.py`. Obecna granulacja jest jednak poprawna, czytelna i zgodna z KISS -- zmiana kosmetyczna, niskiego prioryteu.

---

## 7. [NISKI] `domain/notifications/view.py` -- brak abstrakcji formatowania czasu

**Problem:** `relative_age()` w `notifications/view.py` zawiera twardo zakodowane stale (`_MINUTE`, `_HOUR`, `_DAY`) i logike formatowania. Podobna potrzeba moze wystapic w innych miejscach (logi, inne powiadomienia).

**Proponowane rozwiazanie:** Wyodrebnic do `domain/shared/time_formatting.py`:

```python
def relative_age(timestamp: datetime, now: datetime) -> str: ...
def format_duration(seconds: int) -> str: ...
```

---

## 8. [ŚREDNI] `domain/navigation/focus_navigator.py` -- zbyt wiele odpowiedzialnosci

**Problem:** Klasa `FocusNavigator` laczy nawigacje dwoma obszarami (tiles/topbar), obsluge myszy, obsluge gamepada, escape home. To ~123 linie z wieloma branchami `if self._mode == ...`.

**Proponowane rozwiazanie:** Podzial na mniejsze klasy:

```
domain/navigation/tile_navigator.py      -> TileNavigator
domain/navigation/topbar_navigator.py    -> TopBarNavigator
domain/navigation/focus_state.py         -> FocusState (maszyna stanow)
```

`FocusNavigator` to wtedy jedynie prosta maszyna stanowa (State Pattern) laczaca `TileNavigator` i `TopBarNavigator`.

---

## 9. [NISKI] `domain/menu/home.py` + `domain/menu/tile.py` -- powtorzone wzorce kompozycji menu

**Problem:** Zarowno `compose_home_menu()` jak i `tile_menu_for()` / `compose_tile_menu()` robia to samo: biora `Target` i komponuja `list[MenuItem]`. Logika jest bardzo podobna (sprawdzenie stanu -> zbudowanie listy).

**Proponowane rozwiazanie (DRY, ale z umiarem):** Wprowadzenie wzorca `MenuBuilder`:

```python
class MenuBuilder:
    def __init__(self) -> None:
        self._items: list[MenuItem] = []

    def add_if(self, condition: bool, item: MenuItem) -> "MenuBuilder": ...
    def build(self) -> list[MenuItem]: ...
```

Uzyw sparingo -- jesli uzycie bedzie tylko w tych dwoch m合同的, wprowadzenie pelnego buildera moze byc nadmiarowe (KISS). Ale jesli menu bedzie wiecej, warto.

---

## 10. [ŚREDNI] `domain/provisioning/catalog.py` -- twardo zakodowane dane

**Problem:** 94 linie definisuace "starter candidates" z twardo zakodowanymi wartosciami: nazwami, kolorami, scieżkami, ikonami. To jest data, nie logika.

**Proponowane rozwiazanie:** Przeniesienie definicji do JSON/YAML w katalogu `resources/`, a `catalog.py` ogranicza sie tylko do deserializacji i filtrowania (`discovery.is_available()`).

```yaml
# resources/starter_candidates.yml
- key: files
  name: File Browser
  command: "{bundled_base}/apps/file_browser/file_browser.sh"
  icon: fa5s.folder-open
  color: "#5e81ac"
  order: 40
  default_selected: true
```

---

## Podsumowanie i priorytety

| Priorytet | Element | Problem | Szacowany wplyw |
|-----------|---------|---------|-----------------|
| **Wysoki** | `app_lifecycle.py` | God Class (350 linii) | Trudny w testowaniu, podatny na regresje |
| **Wysoki** | `actions.py` vs `action_view.py` | DRY -- 2 miejsca na 1 akcje | Latwo zapomniec o synchronizacji |
| **Średni** | `volume.py` / `brightness.py` | DRY -- blizniacze klasy | 60 linii redundancji |
| **Średni** | `focus_navigator.py` | SRP -- zbyt duza klasa | Trudna w utrzymaniu |
| **Średni** | `provisioning/catalog.py` | Data w kodzie vs plik | Trudne w edycji przez nie-programistow |
| **Niski** | `entry.py`, `shared/`, `view.py` | Kosmetyka/KISS | Poprawa czytelnosci |

---

## Rekomendowany plan wdrozenia

1. **Krok 1:** `actions.py` + `action_view.py` -> jedna struktura (niski koszt, wysoka wartosc)
2. **Krok 2:** `volume.py` + `brightness.py` -> `RangedValue` (bardzo niski koszt)
3. **Krok 3:** `app_lifecycle.py` -> podzial na koordynatory (najwiekszy wysilek, ale tez najwiekszy zysk)
4. **Krok 4:** Pozostale pozycje (opcjonalnie, w wolnym czasie)
