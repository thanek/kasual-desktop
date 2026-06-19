# Propozycja refaktoringu pakietu `domain`

---

## SRP (Single Responsibility)

1. **`App` — rozdzielić model od parsowania** (`catalog/app.py`). `from_desktop_entry()` / `to_desktop_entry()` + 9 helperów to osobny concern. Wyciągnąć do `AppParser` / `AppSerializer` (lub fabryki).
2. **`AppLifecycle` — "god coordinator" (350 linii, 12 argów konstruktora)** (`lifecycle/app_lifecycle.py`). Rozbić na dedykowane koordynatory: `AppLauncher`, `AppRestorer`, `AppCloser`, `WindowArranger` z fasadą `AppLifecycle` delegującą do nich.
3. **`action_view.py` — 4 responsibility w jednym pliku.** Rozdzielić: `ActionView` (model), `PRESENTATION` (dane statyczne), `system_action_items()` (kompozycja menu), `make_action_confirm()` (adapter).
4. **Value object + Protocol w jednym pliku** (`brightness.py`, `volume.py`). Rozdzielić `Brightness`/`Volume` od ich Protocoli do osobnych plików portów.

## OCP (Open/Closed)

5. **Zamknięty `ACTIONS` dict + `PRESENTATION` dict** (`actions.py` + `action_view.py`). Połączyć definicję akcji w jeden `ActionDefinition` dataclass (identity + effect + presentation), rejestrowany w liście — rozszerzanie przez dodanie elementu, nie edycję dwóch dictów.
6. **Zamknięty if/elif w `FocusNavigator.handle_pad()`** (`navigation/focus_navigator.py`). Zamienić na dispatch table `{event: handler}` per tryb, dodanie nowego event'u = dodanie wpisu, nie edycja łańcucha elif.

## LSP

7. **`Cursor._destination()` — `raise NotImplementedError`** (`menu/cursor_base.py`). Zamienić na `@abc.abstractmethod` — błąd przy konstrukcji, nie przy wywołaniu.

## ISP (Interface Segregation)

8. **Fat `PadControl`** (8 metod). Rozdzielić na: `HandlerStack` (push/pop/top), `TriggerControl` (set_app_btn_mode_trigger, trigger_btn_mode, trigger_home), `PadRefresh` (refresh, inject).
9. **Fat `ProcessManager`** (`lifecycle/process_manager.py`). Wydzielić `ProcessIndex` (swap_indices, remove_index) od właściwego lifecycle (launch, terminate, on_started...).
10. **Fat `WindowManager`** — wydzielić `WindowObserver` (on_windows_updated, cached_windows) od `WindowOperations` (activate, close, minimize, raise).

## DIP

11. **Globalny singleton i18n** (`shared/i18n.py`). Zamiast modułowego `_active`, wstrzykiwać `Translator` przez konstruktor tam gdzie to potrzebne. Ewentualnie zachować comodity `translate()` ale traktować jako świadomy kompromis, nie domyślny wzorzec.
12. **Surowy `pad_handler: Callable`** w `AppLifecycle` — tworzy coupling z implementacją widgetu. Zamienić na mały Protocol z identity semantics (np. `HandlerRef`).

## DRY

13. **`Volume` / `Brightness` — identyczna struktura**. Wyciągnąć generyczny `ClampedValue(min, max, step, value)` z `adjusted()` i `__post_init__`. `Volume`/`Brightness` jako aliasy lub cienkie podklasy.
14. **`VolumeControl` / `BrightnessControl` — identyczne Protocole**. Generyczny `SliderControl[T](Protocol)` lub `LevelControl`.
15. **Translation context `"Kasual Desktop"` × 25**. Stała `TRANSLATION_CONTEXT = "Kasual Desktop"` w `i18n.py`, importowana wszędzie.
16. **Duplikat parent-chain walk** (`window_rules.py`). Wyciągnąć `walk_parent_chain(pid, parent_of) -> Iterator[int]` z cycle-detection i używać w obu funkcjach.
17. **`show_confirm` signature w `DesktopView` i `DesktopControl`**. Wspólny Protocol `Confirmation` z tą jedną metodą, oba dziedziczą.

## KISS

18. **`AppCatalog` + `LiveCatalog` — niepotrzebna dwuwarstwowa abstrakcja**. `LiveCatalog` tylko opakowuje immutable `AppCatalog` i tworzy nowy przy każdej mutacji. Uprościć do jednej mutowalnej klasy katalogu.
19. **`DesktopControl(SessionView, Protocol)`** — myląca multi-dziedziczenie. Zamienić na kompozycję: `DesktopControl` otrzymuje `SessionView` jako zależność, nie dziedziczy.
20. **`from_desktop_entry()` zwraca `tuple[int, App] | None` + rzuca `ValueError`** — three-way convention. Uprościć do jednego mechanizmu: `Result` type albo zawsze rzucać wyjątek.
21. **Niepotrzebny Protocol `Prompts` + jedyna implementacja `LocalizedPrompts`** (`lifecycle/prompts.py`). Skoro implementacja jest w domain i nie ma powodu do wielokrotności — zostawić samą klasę, usunąć Protocol.

---

## Priorytety (impact/effort)

| Priorytet | Issue | Uzasadnienie |
|-----------|-------|-------------|
| **P0** | #13 (ClampedValue) | Mały effort, duży gain DRY |
| **P0** | #7 (ABC abstract) | One-liner, poprawia bezpieczeństwo |
| **P1** | #2 (AppLifecycle split) | Największy problem SRP |
| **P1** | #1 (App parser extraction) | Druga największa klasa |
| **P1** | #5 (ActionDefinition union) | Likwiduje synchronizację dwóch dictów |
| **P1** | #15 (i18n constant) | Szybki win |
| **P2** | #8-10 (ISP splits) | Większy effort ale poprawia testowalność |
| **P2** | #18 (LiveCatalog flatten) | Uproszczenie modelu |
| **P3** | #6 (dispatch table) | Wymaga przepisania navigatora |
| **P3** | #11 (i18n DI) | Duży effort, dużo call-sites |
