# Plan refaktoringu pakietu `domain` — synteza recenzji refactor_1..4

> Plan wykonawczy. Powstał z przeglądu czterech propozycji (`refactor_1..4.md`)
> zweryfikowanych względem rzeczywistego kodu. Bierze tylko to, co potwierdzone
> w źródle; odrzuca przeinżynierowanie i pomysły łamiące konwencje repo
> (hexagonal: logika w `domain`, I/O w `infrastructure`; porty bez prefiksu `I*`).

## Zasady wykonania

1. Każdy punkt = osobny, mały commit.
2. Po każdej zmianie uruchomić testy: `./test.sh`.
3. `AppLifecycle` ruszamy **na końcu** i tylko jako wąskie ekstrakcje za
   zachowaniem publicznego API (fasada/delegacja) — siedzi na ścieżce krytycznej
   launch/close, z gęstymi przypadkami brzegowymi (Steam forwarder, deferred
   hide, re-enumeracja pada). Najpierw upewnić się, że testy pokrywają
   launch/close/restore.
4. Boy Scout Rule na dotykanych plikach; bez komentarzy „co", tylko nieoczywiste „dlaczego".

---

## P0 — tanie, wysokiej pewności

### 1. `Cursor._destination` → `@abc.abstractmethod` (LSP)
**Plik:** `domain/menu/cursor_base.py:65-68`
Zamiast `raise NotImplementedError` oznaczyć metodę `@abc.abstractmethod`
(klasa dziedziczy po `abc.ABC`). Błąd przy konstrukcji niekompletnej podklasy,
nie przy wywołaniu. Sprawdzić, że `MenuCursor`/`GridCursor` nadal się tworzą.
*(refactor_1 #7)*

### 2. `Volume`/`Brightness` → wspólny `BoundedValue` (DRY)
**Pliki:** `domain/system/volume.py`, `domain/system/brightness.py`
(+ nowy `domain/system/bounded_value.py` lub `domain/shared/`).
Wydzielić bazę z `__post_init__` (clamp) i `adjusted(delta)`, parametryzowaną
`MIN`/`STEP`/`DEFAULT` jako `ClassVar`. `Volume` (MIN=0, STEP=5, DEFAULT=50) i
`Brightness` (MIN=5, STEP=10, DEFAULT=70) jako cienkie podklasy frozen-dataclass.
- `adjusted()` musi zwracać własny typ (`copy.replace`/`dataclasses.replace`,
  nie hardkodowany konstruktor).
- Przy okazji usunąć osierocony literał-string w `volume.py:22` (udaje docstring
  po definicji klasy).
- Protokoły `VolumeControl`/`BrightnessControl` **zostają** osobno (różne porty).
*(konsensus refactor_1 #13/14, refactor_2 #3, refactor_4 #1.1 — wersja r4 najlepiej dopięta)*

---

## P1 — realne DRY, średni zysk

### 3. `ACTIONS` + `PRESENTATION` → jeden rejestr (DRY)
**Pliki:** `domain/system/actions.py`, `domain/system/action_view.py`
Dwa słowniki kluczowane tymi samymi stałymi (`VOLUME`, `BRIGHTNESS`, …) —
dodanie akcji wymaga edycji obu, bez pilnowania synchronizacji. Połączyć w jeden
`dataclass` (identity + `needs_confirmation` + `effect` + prezentacja:
label/icon/color/confirm_question) w jednej, uporządkowanej strukturze.
- **KRYTYCZNE i18n:** zachować literalne wywołania `translate("Kasual Desktop", "...")`
  w miejscu definicji — `pylupdate6` ekstrahuje **statycznie** tylko literały
  `(kontekst, tekst)`. Nie chować kontekstu/tekstu za zmienną.
- Nie ujednolicać kontekstu na siłę: są dwa konteksty (`"Kasual Desktop"` ×40,
  `"Desktop"` ×9) i to jest świadome (locale `.ts` zależą od nich).
*(refactor_1 #5, refactor_2 #2)*

### 4. `App.matches_window()` + `walk_parent_chain()` (DRY)
**Pliki:** `domain/catalog/app.py`, `domain/catalog/window_rules.py`, `domain/lifecycle/app_lifecycle.py`
- Dodać na `App` metodę `matches_window(windows) -> bool` opakowującą powtarzane
  `any(w.matches_app(self) for w in windows)` (występuje w `is_app_running`,
  `_close_app_windows`, `_raise_app`).
- Wydzielić w `window_rules.py` generator `walk_parent_chain(pid, parent_of)` z
  cycle-detection (`visited`) i użyć w `descends_from_launcher` oraz
  `resolve_recall_trigger` (identyczny szkielet `while current>1 and not visited`).
*(refactor_4 #4.2, refactor_1 #16)*

---

## P2 — `AppLifecycle`, ostrożnie (na końcu)

### 5. Wąskie ekstrakcje z `AppLifecycle` (SRP, prawej wielkości)
**Plik:** `domain/lifecycle/app_lifecycle.py` (350 linii)
**NIE** rozbijać na 4 koordynatory (refactor_1 #2 / refactor_2 #1 — przeinżynierowane;
współpracownicy `ForegroundInspector`/`WindowManager`/`ProcessManager` są już
wydzieleni, więc to poprawny Application Coordinator). Tylko dwie ekstrakcje za
zachowaniem publicznego API:
- `WindowArranger` — z `_raise_app` + `arrange_windows` (przyjmuje
  `WindowManager` + `ProcessManager`).
- `CloseConfirmation` — wyizolować logikę domknięć `_confirmed`/`_cancelled`
  z `request_close_app`; przy okazji scalić wspólną ścieżkę zamykania okien
  z `_close_app_windows` (zwykły prywatny helper, **bez** `CloseStrategy` Protocol).
`AppLifecycle` pozostaje fasadą delegującą.
*(refactor_4 #2.1; łagodzi refactor_1 #2 / refactor_2 #1 / refactor_2 #4)*

---

## CO ŚWIADOMIE ZOSTAWIAMY BEZ ZMIAN

- **`App` (struktura)** — SRP nie naruszone; model+parse+serialize+computed
  dotyczą tego samego bytu. Bez splitu, bez `__slots__` (kilkanaście instancji —
  zero zysku). *(odrzuca refactor_1 #1, refactor_2; za refactor_4 #2.2)*
- **`LiveCatalog` + `AppCatalog`** — celowy wzorzec: niemutowalna wartość +
  mutowalna komórka referencyjna współdzielona przez konsumentów index-keyed.
  Spłaszczenie przywraca bug rozjeżdżających się kopii. *(odrzuca refactor_1 #18)*
- **i18n `_active` (service locator)** — uzasadniony globalny stan; bez DI i bez
  `assert` (złamałby identycznościowe zachowanie headless/testów).
  *(odrzuca refactor_1 #11; za refactor_4 #1.2 z korektą)*
- **`DesktopControl(SessionView, Protocol)`** — kompozycja interfejsów Protokołów
  to idiom; re-deklaracja metod = anty-DRY. *(odrzuca refactor_1 #19, refactor_4 #3.2)*
- **`TileBarView` / `TileFocusView`** — już rozdzielone na rozłączne role-interfejsy
  (ISP zrobione poprawnie). *(odrzuca refactor_4 #3.1)*
- **`Prompts` Protocol** — port zostaje dla podstawialności w testach. *(odrzuca refactor_1 #21)*
- **`FocusNavigator`** — dobrze spasowany; bez State Pattern. *(odrzuca refactor_2 #8)*
- **`Cursor`/`MenuCursor`/`GridCursor`** — wzorcowy Template Method. *(za refactor_4 #6)*
- **`provisioning/catalog.py`** — to dane **+** logika (`with_real_icon`,
  `is_available`, enumy); YAML łamałby hexagonal (ładowanie = I/O) i type-safety.
  *(odrzuca refactor_2 #10)*
- **`from_desktop_entry` (None vs ValueError)** — dwie różne semantyki, nie
  „three-way convention". *(odrzuca refactor_1 #20)*
- **`entry.py`** — już pogrupowane sekcjami; klasy per-menu = marginalny zysk,
  gorszy import. *(odrzuca refactor_2 #5)*
- **`shared/` granularność, `MenuBuilder`, `relative_age` ekstrakcja** — pomijalne.
- **Cały refactor_3.md** — generyczny katalog wzorców GoF, łamie konwencje repo
  (`I*`, adaptery w `domain`); odrzucony jako plan.

---

## Kolejność realizacji

1. P0 #1 (`@abstractmethod`)
2. P0 #2 (`BoundedValue`)
3. P1 #3 (rejestr akcji)
4. P1 #4 (`matches_window` + `walk_parent_chain`)
5. P2 #5 (`AppLifecycle`: `WindowArranger` + `CloseConfirmation`) — po potwierdzeniu pokrycia testami
