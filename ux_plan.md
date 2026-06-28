# Kasual Desktop — Plan implementacji UX v2

> Plan wdrożenia zmian uzgodnionych w `UX.md` (§7.3, §7.4, §7.10 + foundation).
> Kolejność: od najmniejszego blast-radius (czysta domena) do największego
> (przebudowa Home Overlay). Każda faza jest **samodzielnie wdrażalna i
> testowalna** — można zatrzymać się po dowolnej.
>
> **Zasada nadrzędna:** gamepad-first. Każda zmiana wejścia ma najpierw model w
> `domain/input` (testowalny bez Qt), potem mapowanie w adapterach
> (evdev / pygame) i fallback klawiatury.
>
> **Architektura, której pilnujemy:** logika w `domain/` (bez Qt, bez I/O),
> prezentacja w `infrastructure/common/qt`, OS-specyfika za portami. Windows nie
> importuje z `kde/` i odwrotnie.

---

## Mapa zmian → kod

| Obszar UX | Sekcja | Domena (źródło prawdy) | Adapter / UI |
|---|---|---|---|
| Jedno menu kafla | §7.3 | `domain/menu/tile.py` | `qt/desktop/desktop.py`, `qt/overlays/tile_popover.py` |
| Pinned apps + `[＋]` | §7.4 | `domain/catalog/target.py`, `domain/provisioning/*`, `domain/catalog/live_catalog.py` | `qt/desktop/{tile_bar,app_tile}.py`, `qt/overlays/onboarding_overlay.py` |
| Home Overlay v2 | §7.10 | `domain/menu/home.py`, `domain/system/{actions,brightness,volume}.py` | `qt/overlays/home_overlay.py`, `qt/desktop/{topbar,hint_bar}.py` |
| Input (bumpery/triggery/Y) | foundation | `domain/input/vocabulary.py`, `domain/navigation/hints.py` | `linux|windows/input/gamepad_watcher.py` |

---

## Faza 0 — Fundament wejścia (blokuje §7.10)

**Cel:** rozszerzyć abstrakcyjny słownik wejścia o sygnały potrzebne v2, zanim
ktokolwiek ich użyje. Bez tego strefy Home Overlay nie ruszą.

**Domena**
- `domain/input/vocabulary.py` — dodać do `Event`:
  - `SECTION_PREV`, `SECTION_NEXT` — bumpery (LB/RB), przełączanie sekcji overlaya,
  - `VOLUME_DOWN`, `VOLUME_UP` — triggery (LT/RT), globalna głośność,
  - `ACTIONS` — rozwinięcie dropdownu (przycisk Y) na kaflu/Power.
- `domain/navigation/hints.py` — dodać **strefowe** zestawy hintów dla Home
  Overlay (Quick adjust vs Actions) oraz glify `LB/RB`, `LT/RT`, `Y`. Rozszerzyć
  `Button` o `LB`, `RB` (i ewentualnie analogowe triggery jako osobny element).

**Adaptery**
- `infrastructure/linux/input/gamepad_watcher.py` (`_translate_key`/`_translate_axis`):
  - `BTN_TL` → `SECTION_PREV`, `BTN_TR` → `SECTION_NEXT`,
  - `BTN_TL2`/`ABS_Z` → `VOLUME_DOWN`, `BTN_TR2`/`ABS_RZ` → `VOLUME_UP`
    (triggery są analogowe — próg + debounce, nie spamić eventami),
  - `BTN_NORTH` → `ACTIONS` (dziś niemapowane).
- `infrastructure/windows/input/gamepad_watcher.py` — analogiczne mapowanie pygame/XInput.
- Klawiatura (fallback): `qt/overlays/*`, `qt/desktop/desktop.py` `_KEY_MAP` —
  np. `Q/E`→sekcje, `-/=`→głośność, `Tab`/`F`→ACTIONS.

**Testy:** `tests/.../input/` — produkcja `Event` z kodów klawiszy; próg triggera.
**Ryzyko:** triggery analogowe mogą „dryfować” → twardy próg + histereza
(wzór jest już w `_translate_axis` dla sticka). Bumpery wolne wewnątrz overlaya
(overlay grabuje input), ale w grze nie ruszamy — recall to wciąż BTN_MODE.

---

## Faza 1 — Jedno menu kafla (§7.3)

**Cel:** scalić dwa popovery (`Y` actions + `Start` manage) w jeden, zależny od
stanu; ukryć zarządzanie dla kafla *running*.

**Domena — `domain/menu/tile.py`**
- Nowa kompozycja, np. `compose_tile_menu_v2(target, is_running)`, łącząca dziś
  rozdzielone `compose_tile_menu` (Launch / Restore-Close) i `tile_management_menu`
  (Move/Color/Unpin vs Pin):
  - `AppTarget` + **not running** → `Launch` + separator + `Move`, `Change color`, `Unpin`;
  - `AppTarget` + **running** → `Restore`, `Close` (gałąź zarządzania **pominięta**);
  - `WindowTarget` → `Restore`, `Close`, `Pin to menu`.
- Zostawić `MenuItem`/`entry.py` bez zmian (te same akcje, inna kompozycja).

**Adapter — `qt/desktop/desktop.py`**
- `_open_tile_popover` (≈445): podmienić `tile_menu_for` na nową kompozycję.
- `_open_tile_management` (≈466–474): **usunąć** osobny popover; `Event.MANAGE`
  (Start) odpiąć od tile-managementu. `Start` zwolniony — zostawić nieobsadzony
  lub (opcjonalnie, oddzielny ticket) podpiąć „powrót do ostatniej aplikacji”.
- `TilePopoverMenu` — wsparcie separatora/sekcji (nieklikalny nagłówek grupy);
  drobna zmiana renderu w `tile_popover.py`.
- `hints.py` `TILES` — usunąć hint „Manage”, zostawić `A Select` / `Y Actions`.

**Testy:** `tests/.../menu/` — trzy stany kafla → poprawny zestaw `MenuItem`
(w szczególności: running **nie** zawiera Move/Color/Unpin).
**Ryzyko:** niskie — czysta domena + jedno miejsce wywołania. Migracja: stare
`tile_menu_for`/`tile_management_menu` można zostawić deprecated do czasu zdjęcia
testów, albo przepiąć od razu.

---

## Faza 1.5 — Terminologia: „Home” zamiast „Desktop” (§7.11)

**Cel:** usunąć kolizję „Desktop/pulpit” (launcher KD vs pulpit OS). **Tylko
stringi user-facing** — wewnętrzny słownik kodu zostaje. Niezależne, niskie ryzyko,
można wdrożyć kiedykolwiek.

**Stringi do zmiany (z kontekstem tłumaczeniowym pylupdate6):**
- `domain/menu/home.py` — `"Return to Desktop"` → `"Return to Home screen"`
  (PL „Wróć do ekranu głównego”); dotyczy zarówno kontekstu Home, jak i recall nad
  aplikacją (`_return_to_desktop_item`).
- `domain/system/actions.py` — `HIDE_DESKTOP` label `"Minimize Desktop"` →
  `"Minimize Kasual Desktop"` (PL „Minimalizuj Kasual Desktop”). Ikona/efekt bez zmian.
- `domain/menu/tile.py` / `entry.py` — sprawdzić etykiety `RESTORE`/`RETURN` pod
  kątem słowa „Desktop” (np. recall „Return to Desktop” w File Browser z screena
  110705) i ujednolicić do „Home / Ekran główny”.
- `locale/kasual_pl.ts` + `kasual_en.ts` — zaktualizować wpisy, przegenerować
  `.qm` (`./test.sh`/build); usunąć osierocone tłumaczenia „…Desktop”.

**Czego NIE ruszamy:** klasy/identyfikatory `Desktop`, `RETURN_TO_DESKTOP`,
`HIDE_DESKTOP`, nazwa produktu „Kasual Desktop”, nagłówek overlaya „Kasual Desktop”.

**Test:** przełączenie locale PL/EN pokazuje spójnie „Home/Ekran główny”; nigdzie
nie zostaje „Wróć do pulpitu”. Smoke: recall nad aplikacją i menu na ekranie
głównym pokazują tę samą, nową etykietę.

**Ryzyko:** minimalne (i18n). Można wpiąć do M1.

---

## Faza 2 — Pinned apps + kafel `[＋]` + stały wskaźnik running (§7.4)

**Cel:** jeden rząd ze stanem na kaflu, separator dla okien efemerycznych, stały
syntetyczny kafel „Add app”, stały wskaźnik running.

**Domena**
- `domain/catalog/target.py` — dodać trzeci wariant `AddTileTarget` (syntetyczny,
  bez indeksu aplikacji); rozszerzyć `Target = AppTarget | WindowTarget | AddTileTarget`
  i `target_at()` tak, by **ostatnia** pozycja w sekcji pinned mapowała na `[＋]`.
- `domain/provisioning/` — funkcja filtrująca kandydatów o już zapięte:
  - w `selection.py`/`catalog.py` dodać `exclude_keys: set[str]`; `CandidateApp.key`
    jest stabilny (= nazwa pliku `.desktop`), więc filtr to różnica zbiorów kluczy.
- `domain/catalog/live_catalog.py` — `append()` już istnieje; wynik add-flow
  woła `append` (lub batch dla multi-select).

**Adapter — `qt/desktop/`**
- `app_tile.py` — **stały pasek „running”** (dziś widoczny tylko w trybie
  restore wg screena 111017): rysować zawsze, gdy `is_tile_running`. Wariant
  „efemeryczny” (`WindowTarget`) → kreskowany obrys; `[＋]` → wyszarzony, ikona `＋`,
  brak stanu running i brak menu Manage.
- `tile_bar.py` — wstawić separator między pinned (apps) a open (windows);
  dołożyć `[＋]` jako ostatni kafel sekcji pinned; uwzględnić w nawigacji fokusu
  (rząd to wciąż L/R, ale `[＋]` i separator są „przeskakiwalne” spójnie).
- `[＋]` aktywacja → otwarcie odchudzonego pickera: **reużyć
  `onboarding_overlay.py`** (komponent provisioningu) z listą przefiltrowaną
  `exclude_keys = {zapięte klucze}`; po zatwierdzeniu → `live_catalog.append`.
- Po dodaniu: kafle lądują **przed** `[＋]`; odświeżyć rząd.

**Testy:** provisioning z `exclude_keys` (pomija zapięte); `target_at` zwraca
`AddTileTarget` na ostatniej pozycji pinned; menu Manage niedostępne dla `[＋]`.
**Ryzyko:** średnie — dotyka modelu fokusu rzędu i resolvera celów. Pilnować, by
`[＋]` nie wpadał w heurystyki running/HUD ani w `compose_tile_menu_v2`
(early-return dla `AddTileTarget`).

---

## Faza 3 — Home Overlay v2 (§7.10)

Największa faza; rozbita na podkroki, każdy osobno testowalny.

### 3a. Gating jasności na sterowalny backlight
**Domena — `domain/system/brightness.py`**
- Port ma dziś tylko `get/set`; dodać `is_controllable() -> bool` (lub `available`).
- Adaptery jasności (KDE / Windows) implementują zapytanie o sterowalny backlight
  (laptop/DDC). Brak → suwak jasności znika z Quick adjust.

> **Forward-compatibility (multi-device — NIE budujemy teraz, YAGNI).** W
> przyszłości może pojawić się wiele wyjść audio i wideo (labelka „aktualne
> urządzenie”, docelowo wybór). Plan to przewiduje, nie implementując:
> - **Nie przeciążać `is_controllable()`** — ma odpowiadać wyłącznie na pytanie
>   gatingu („czy istnieje *jakiekolwiek* sterowalne wyjście?”). Przyszłe
>   `outputs()` / `current_output()` / `set_output()` to **osobne rozszerzenie
>   portu, obok**, nie zamiast.
> - **Miejsce zarezerwowane w Quick adjust** — pod suwakiem labelka statusu
>   („Wyjście: …”), a edycja (przyszłość) reużywa idiomu Power-dropdownu: `◄►`
>   reguluje, `Y` (`ACTIONS`, dodawane w Fazie 0) rozwija picker urządzeń. Hook
>   pod to powstaje już teraz przy okazji, bez kodu audio/wideo.
> - **Semantyka suwaka** = „poziom *aktualnego/domyślnego* wyjścia” — zdanie
>   pozostaje prawdziwe, gdy urządzeń przybędzie; nie zaszywać twardego „jest
>   dokładnie jedno urządzenie” w `volume.py`/`brightness.py`.

### 3b. Power jako pad-dropdown (sticky last-choice)
**Domena**
- `domain/system/actions.py` — Sleep/Restart/Shutdown już istnieją z confirm;
  dodać pojęcie **domyślnej akcji zasilania** (preferencja).
- Persystencja: jedna wartość w configu (cross-platform config root z README) —
  np. `power.default = sleep|restart|shutdown` (domyślnie `sleep`).
- Logika dropdownu: `A` na kaflu → akcja domyślna; `ACTIONS` (Y) → lista; wybór =
  **wykonaj + utrwal**, ale **utrwalenie dopiero po potwierdzonym** confirm
  (`Yes`); `No`/`B` nie zmienia defaultu. To reguła czysto domenowa — pokryć
  testami bez Qt.

### 3c. Sekcyjny model menu
**Domena — `domain/menu/home.py`**
- `compose_home_menu` już jest kontekstowy (nazwa aplikacji w „Return/Close {0}”,
  `foreground_is_game`, HUD gating) — **rozszerzyć**, nie pisać od zera:
  - zwracać **sekcje** (Quick adjust [volume, brightness?], Actions [Power-dropdown,
    …], HUD [warunkowo]), a nie płaską listę;
  - brightness w Quick adjust tylko gdy `brightness.is_controllable()`;
  - HUD jako warunkowy wiersz w kontekście aplikacji (już gated na `foreground_is_game`
    + `hud_menu_item`); etykiety pozostają z nazwą procesu (bez „gra”).

### 3d. Przebudowa widżetu overlaya
**Adapter — `qt/overlays/home_overlay.py`**
- Z pionowej listy (`MenuCursor`, 1D) na **dwustrefowy układ**: Quick adjust +
  siatka kart (`domain/menu/grid_cursor.py` — 2D nav już istnieje).
- **Bumpery** `SECTION_PREV/NEXT` przełączają sekcje; D-pad zostaje w sekcji.
- **Suwaki inline** — przenieść logikę z `volume_overlay.py`/`brightness_overlay.py`
  do sekcji Quick (te osobne overlaye można potem wycofać); `◄►` reguluje.
- **Triggery** `VOLUME_DOWN/UP` regulują głośność niezależnie od fokusu.
- **Power-dropdown** — render kafla z chevronem `▾` + glifem `(Y)`; po `ACTIONS`
  rozwinięcie listy (zakotwiczone), wybór → confirm → wykonanie/utrwalenie.
- **Strefowy hint bar** — `qt/desktop/hint_bar.py` renderuje zestaw zależny od
  aktywnej sekcji (Quick: `LB/RB Sekcja | ◄► Reguluj | B`; Actions: `LB/RB Sekcja
  | D-Pad | A | B`).

### 3e. Top bar — pojedynczy Power
**Adapter — `qt/desktop/topbar.py`**
- Zamiast pełnej trójcy: **jeden** przycisk Power = ta sama domyślna akcja co w
  overlayu (jedno źródło prawdy — preferencja z 3b). Network/Notifications
  zostają na top barze (rzadkie wg §7.10).

**Testy:** `compose_home_menu` zwraca poprawne sekcje per kontekst i per
`is_controllable`; reguły Power-dropdownu (utrwalenie tylko po `Yes`).
**Ryzyko:** wysokie — to przebudowa centralnego ekranu. Mitygacja: 3a–3c (domena)
przed 3d–3e (UI); osobne overlaye volume/brightness usuwać **dopiero** gdy Quick
adjust działa; trzymać feature za flagą do czasu pełnego przejścia.

---

## Faza 4 — Backlog (pozostałe §7.x, poza bieżącym zakresem)

Nie wchodzą w ten plan, ale spójne kierunkowo — osobne tickety:
- **§7.1** jawny system warstw (Surface / Quick / Modal) + wspólna tożsamość wizualna.
- **§7.5** interaktywny samouczek pada (po provisioningu) + „ściąga sterowania”.
- **§7.6** redesign Network (lista sieci) i Notifications (grupowanie/akcje).
- **§7.8** glify przycisków + wykrywanie typu pada (Xbox/PS/Nintendo, A/B vs krzyż/koło).
- **§7.9** twardy kontrakt `B` = jedna warstwa wstecz + przywracanie fokusu.

---

## Faza 5 — UX v2.1: Trwała powierzchnia Home *(side-project, PoC-first, OSTATNI punkt)*

> **To nie jest UX v2** (patrz `UX.md` §8). Osobny tor, **po całym v2**,
> bezwzględnie **z PoC przed implementacją**. Cel: zegar+data zawsze pod ręką
> (skrócenie „odczyt godziny w grze”) i rozpuszczenie top bara w jeden trwały
> komponent collapsed/expanded.

**Model (trzy konteksty — szczegóły w `UX.md` §8):**
1. **Widok KD** — komponent trwały: zwinięty (sam nagłówek: zegar+data) ↔ rozwinięty
   (nagłówek + content §7.10) przez **wewnętrzny morph, bez map/unmap**.
2. **KD zminimalizowany** — zamknięty; pojawia się na BTN_MODE (model dotychczasowy).
3. **Aplikacja** — zamknięty; pojawia się na BTN_MODE z contentem kontekstu (§7.10).

**Etap 0 — PoC (gate; bez niego nie ruszamy implementacji):**
- Zweryfikować **morph collapse↔expand w widoku KD na jednej stale zmapowanej
  powierzchni** (wzorem trwałego hint bara) — czy unika animacji KWin.
- Zweryfikować **zastąpienie top bara nagłówkiem** bez regresji (status: zegar,
  data, sieć, badge powiadomień).
- **Parytet Windows** (desktop surface, brak layer-shell) — czy collapse/expand
  działa też tam.

**Implementacja (dopiero po PoC):**
- Rozpad top bara: status → zwinięty nagłówek; akcje → rozwinięty content (już w §7.10).
- Konteksty 2/3 zostają na modelu „mapowanie na żądanie” — **brak trwałej
  powierzchni nad pełnoekranową grą** (to celowo neutralizuje dawny Spike #1 i
  ryzyko prowokowania paneli KWin — dlatego dziś `keyboard=NONE`).

**Ryzyko:** wysokie (zmiana centralnej chrome) — dlatego PoC-first i na końcu.
Nie blokuje żadnej fazy v2; v2 jest w pełni wartościowe bez tego toru.

---

## Sekwencja i kamienie milowe

```
M1  Faza 0 (input) + Faza 1 (menu kafla) + Faza 1.5 (Home/i18n)  ← najmniejsze ryzyko
M2  Faza 2 (Pinned + [＋] + running indicator)
M3  Faza 3a–3c (domena Home Overlay: gating, Power, sekcje)
M4  Faza 3d–3e (UI Home Overlay + top bar)        ← za flagą, potem usunięcie starych overlayów
M5  Faza 4 (backlog wg priorytetu)
─────────────────────────────────────────────────  ← koniec UX v2
M6  Faza 5 — UX v2.1 (side-project): PoC → (gate) → implementacja
```

## Przekrojowe zasady realizacji
- **Najpierw domena, potem adapter** — każda faza zaczyna od testowalnej logiki
  w `domain/`, dopiero potem Qt/evdev/pygame.
- **Parytet platform** — każdą zmianę wejścia/portu wdrożyć w obu adapterach
  (`linux/` i `windows/`) lub jawnie ją zaślepić; nie łamać `windows_main`/`main`.
- **Testy** — istniejący pytest (`./test.sh` / `.\test.ps1`); nowe reguły domenowe
  pokryte przed UI. Bez Qt w testach domeny.
- **i18n** — nowe stringi przez `translate(...)` z właściwym kontekstem
  (`"Kasual Desktop"` / `"Desktop"` / `"HintBar"`), zgodnie z wzorcem ekstrakcji
  pylupdate6; uzupełnić `locale/*.ts`.
- **Wycofania** — `volume_overlay.py`/`brightness_overlay.py` oraz
  `tile_management_menu` usuwać dopiero po przejściu odpowiednio Fazy 3d i Fazy 1.
