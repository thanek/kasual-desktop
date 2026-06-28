# Kasual Desktop — Audyt UX

> Dokument opisuje obecny stan UX aplikacji Kasual Desktop na podstawie zrzutów
> ekranu z rzeczywistego użytkowania oraz analizy modelu wejścia w kodzie
> (`src/domain/navigation/hints.py`, `src/domain/system/actions.py`,
> `src/infrastructure/.../input/gamepad_watcher.py`).
>
> **Założenie nadrzędne:** Kasual Desktop to interfejs **gamepad-first**. Pad jest
> instrumentem obsługi pierwszej kategorii — cały model interakcji, hierarchia
> ekranów i fokus są projektowane pod kontroler. Klawiatura i mysz to wyłącznie
> *fallback*. Ten audyt ocenia UX przez ten pryzmat: każdą decyzję projektową
> mierzymy tym, jak dobrze obsługuje się ją kciukami na padzie, a nie kursorem.

---

## 1. Current UX

Kasual Desktop jest „konsolową” nakładką launcher/desktop. Po uruchomieniu
użytkownik widzi pełnoekranowy pulpit z tapetą, **górnym paskiem systemowym**,
**rzędem kafelków aplikacji** na środku i **dolnym paskiem podpowiedzi**
sterowania (hint bar). Całość zaprojektowana jest tak, by dało się ją obsłużyć
bez dotykania myszy — analogicznie do Steam Big Picture / interfejsów konsolowych.

### Główne stany (ekrany)

| Ekran / stan | Co widać | Źródło (screenshot) |
|---|---|---|
| **Desktop / Tiles** | Tapeta, górny pasek, rząd kafelków, hint bar | 110647 |
| **Top bar focus** | Fokus przeniesiony na ikony systemowe u góry | (tryb TOPBAR w `hints.py`) |
| **Home Overlay** | Pionowe menu „Kasual Desktop” (Volume, Brightness, Sleep, Restart, Shut Down, Notifications, Network, Minimize) | 110906, 110926 |
| **Volume / Brightness slider** | Mała nakładka z suwakiem i wartością % | 110723, 110732 |
| **Confirm dialog** | „Are you sure you want to sleep?” + Yes/No | 110742 |
| **Notifications** | Lista „Recent notifications” | 110752 |
| **Network** | Karta z typem, IP, interfejsem + przycisk Disconnect | 110811 |
| **Tile „Manage” popover** | Move / Change color / Unpin | 110838 |
| **Color picker** | Paleta 20 kolorów kafelka | 110852 |
| **Tile „Actions” popover (app)** | „Launch” | 110956 |
| **Tile „Actions” popover (running)** | Restore / Close (pasek uruchomionych) | 111017 |
| **Aplikacja (File Browser)** | Sidebar, breadcrumb, siatka folderów + recall menu | 110705 |

### Model wejścia (mapowanie pada)

Z kodu (`gamepad_watcher.py`, `hints.py`):

| Przycisk | Funkcja |
|---|---|
| **D-pad / lewy stick** | Nawigacja po fokusowalnych elementach |
| **A** (BTN_SOUTH) | Select / Launch / Confirm |
| **B** (BTN_EAST) | Back / Cancel / Close overlay |
| **Y** (BTN_NORTH) | „Actions” — popover kontekstowy kafelka (Launch / Restore-Close) |
| **X** (BTN_WEST) | Close |
| **Start** (BTN_START) | „Manage” — popover zarządzania kafelkiem (Move/Color/Unpin) |
| **Start + Select** (chord) | Recall — otwiera Home Overlay z poziomu uruchomionej gry/aplikacji |
| **BTN_MODE (Guide)** | Toggle Home Overlay (na Windows zawsze; na Linux per-app trigger CLICK/HOLD_1S) |

Kluczowy mechanizm to **recall**: w trakcie gry przycisk Guide (lub chord
Start+Select) przywołuje Home Overlay nad działającą aplikacją — to serce
„konsolowego” doświadczenia.

---

## 2. Navigation

### Model nawigacji

Nawigacja jest **dwuwymiarowa, ale spłaszczona do stref**. Fokus żyje w jednej z
kilku stref, a przejścia między nimi są kierunkowe:

```
            ┌───────────────────────────────────────────────┐
   UP ↑     │  TOP BAR  (vol, bright, night, restart, power, │
            │            network, minimize)                  │
            └───────────────────────────────────────────────┘
                              ↑ UP / DOWN ↓
            ┌───────────────────────────────────────────────┐
            │  TILES  [Steam] [Files] [YouTube] [Edge] ...   │  ← LEFT/RIGHT
            └───────────────────────────────────────────────┘

   BTN_MODE / Start+Select  ──►  HOME OVERLAY (modal, UP/DOWN list)
   Y na kafelku             ──►  ACTIONS popover (Launch / Restore-Close)
   Start na kafelku         ──►  MANAGE popover (Move / Color / Unpin)
```

- **Tiles ⇄ Top bar:** z rzędu kafelków `UP` wchodzi na górny pasek, `DOWN`
  wraca. Hint bar potwierdza dostępne kierunki (TILES: L/R/UP; TOPBAR: L/R/DOWN).
- **Home Overlay** jest modalny i pionowy (`UP`/`DOWN`), wywoływany przyciskiem
  Guide/recall, zamykany `B` lub ponownym Guide.
- **Popovery kafelka** (Actions / Manage) są kontekstowe i przykotwiczone do
  fokusowanego kafelka — krótkie pionowe listy.
- **Dialogi** (Confirm, Slider) przejmują wejście modalnie: Slider = `L/R`,
  Confirm = `L/R` między Yes/No.
- **Wewnątrz aplikacji** (np. File Browser) nawigacja jest „cofnięta” do appki,
  a recall (Guide) nakłada na nią menu „Kasual Desktop” (Return / Close / Return
  to Desktop).

### Hint bar jako kontrakt nawigacyjny

Dolny pasek jest **dynamiczny i per-ekran** — to mocny element. Każdy stan ma
zdefiniowany własny zestaw podpowiedzi (TILES, TOPBAR, OVERLAY_MENU, SLIDER,
CONFIRM, NOTIFICATIONS, NETWORK). Lewa strona = kierunki + Guide, prawa strona =
przyciski akcji. Etykieta klastra kierunkowego zmienia się kontekstowo
(„Navigate” → „Adjust” na suwaku).

---

## 3. Information Architecture

Hierarchia treści i funkcji:

```
Kasual Desktop
│
├── Top bar (skróty systemowe — szybki dostęp, 1 ruch w górę)
│   ├── Volume          → Slider overlay
│   ├── Brightness      → Slider overlay
│   ├── Night mode      → (toggle)
│   ├── Restart         → Confirm
│   ├── Power/Shutdown  → Confirm
│   ├── Network         → Network card (status + Disconnect)
│   └── Minimize Desktop
│
├── Tiles (katalog aplikacji — serce launchera)
│   ├── A / Launch              → uruchom aplikację
│   ├── Y / Actions             → Launch | (running:) Restore / Close
│   └── Start / Manage          → Move | Change color | Unpin
│                                    └── Change color → paleta 20 kolorów
│
├── Home Overlay (modalne menu globalne — duplikuje top bar + recall w grze)
│   ├── Return to Desktop
│   ├── Volume / Brightness
│   ├── Sleep / Restart / Shut Down
│   ├── Notifications
│   ├── Network
│   └── Minimize Desktop
│
└── Aplikacje (uruchomione okna)
    └── Recall menu: Return to App | Close App | Return to Desktop
```

### Kluczowa obserwacja IA

Funkcje systemowe są **zduplikowane w dwóch miejscach**: na górnym pasku i w Home
Overlay. To celowe (top bar = szybki dostęp z pulpitu; overlay = dostęp z gry),
ale tworzy dwie równoległe ścieżki do tych samych akcji, z różną prezentacją
(ikony w rzędzie vs. lista). Źródło prawdy jest jedno (`actions.py`), więc
zawartość jest spójna, ale *forma* i *sposób dotarcia* — nie.

---

## 4. Pain Points

### P1 — Niespójna lokalizacja (wysoki priorytet)
Na zrzutach widać mieszankę języków w jednej sesji: suwaki to **„Głośność”** i
**„Jasność”** (polski), ale Home Overlay, Notifications i Network są po angielsku
(„Volume”, „Brightness”, „Recent notifications”, „Network”). To samo pojęcie ma
dwie nazwy zależnie od ekranu. Łamie zaufanie do interfejsu i sugeruje
niekompletne pokrycie tłumaczeń lub różne konteksty tłumaczeniowe.

### P2 — Dwie nakładające się ścieżki do akcji systemowych
Top bar i Home Overlay robią to samo. Użytkownik musi nauczyć się, że „w grze
używam Guide → menu”, a „na pulpicie idę w górę na pasek” — choć obie drogi
prowadzą do identycznych akcji. Zwiększa to obciążenie poznawcze i ryzyko, że
top bar jest rzadko używany (skoro Home Overlay działa wszędzie).

### P3 — Rozdział „Actions” (Y) i „Manage” (Start) jest nieintuicyjny
Kafelek ma **dwa różne popovery na dwóch różnych przyciskach**:
- `Y` → Launch / Restore / Close (cykl życia aplikacji),
- `Start` → Move / Change color / Unpin (zarządzanie kafelkiem).

Granica „akcja na aplikacji” vs „akcja na kafelku” jest subtelna i wymaga
pamięci mięśniowej. Hint bar pokazuje oba („Actions”, „Manage”), ale dla nowego
użytkownika to dwa prawie identyczne menu konteksowe pod różnymi guzikami.

### P4 — Slider/Confirm overlay zasłaniają kafelki niespójnie
Nakładki Volume/Brightness/Confirm pojawiają się **na środku, częściowo
zasłaniając kafelki** (110723, 110732, 110742), w pozornie przypadkowej pozycji
(nie wycentrowane względem ekranu, „doczepione” gdzieś nad rzędem kafelków). Brak
spójnej kotwicy/pozycji nakładek obniża wrażenie dopracowania.

### P5 — Pasek uruchomionych aplikacji vs. rząd kafelków launchera
Screenshot 111017 pokazuje **inny tryb** rzędu (uruchomione okna z menu
Restore/Close), wizualnie bardzo podobny do launchera kafelków (110647). Dwa
różne znaczenia tego samego elementu UI (statyczny katalog vs. lista żywych okien)
mogą mylić — brak wyraźnego sygnału „to są teraz okna, nie aplikacje”.

### P6 — Brak widocznego stanu/feedbacku „co jest uruchomione”
Z poziomu pulptu nie widać od razu, które aplikacje są aktywne (poza wejściem w
tryb uruchomionych okien). Na padzie, gdzie nie ma pasków zadań ani myszki,
informacja „co działa” jest kluczowa, a obecnie ukryta.

### P7 — Discoverability funkcji ukrytych pod przyciskami
Kluczowe akcje (Manage, Actions, recall chord Start+Select) są dostępne wyłącznie
przez przyciski, których nie widać dopóki nie są w hint barze danego ekranu.
Chord Start+Select w ogóle nie jest komunikowany w UI. Nowy użytkownik nie ma jak
odkryć części funkcji bez dokumentacji.

### P8 — Network: surowa karta zamiast akcji
Karta sieci (110811) to głównie tekst diagnostyczny (Type, Connection, IP,
Interface) z jednym przyciskiem Disconnect. Dla gamepad-first to dużo informacji
o niskiej akcyjności — brak wyboru sieci Wi-Fi, brak listy. Wygląda jak read-only
panel statusu, nie jak sterowanie.

---

## 5. Strengths

### S1 — Konsekwentny, dynamiczny hint bar
Najmocniejszy element. Każdy ekran deklaruje własny zestaw podpowiedzi
(`hints.py`), z rozdziałem kierunki/akcje i kontekstową etykietą („Navigate” vs
„Adjust”). To wzorcowe dla gamepad-first — użytkownik zawsze wie, co robią
przyciski **tu i teraz**.

### S2 — Recall jako idea organizująca
Mechanizm Guide/Start+Select przywołujący Home Overlay nad grą to dokładnie to,
czego oczekuje się od interfejsu konsolowego. Spójne „zawsze mogę wrócić jednym
przyciskiem” to silny fundament zaufania.

### S3 — Czysta, czytelna estetyka kafelków
Duże kafelki z ikoną, kolorem i etykietą, wyraźny fokus (jasna ramka/poświata),
zaokrąglone rogi — dobrze czytelne z dystansu „kanapowego” (10-foot UI), co jest
właściwym targetem dla pada.

### S4 — Jedno źródło prawdy dla akcji
`actions.py` definiuje akcje, kolejność, ikony, potrzebę potwierdzenia i wording
w jednym miejscu. Gwarantuje to spójność treści między top barem a Home Overlay
(nawet jeśli forma się różni — patrz P2).

### S5 — Sensowne gating potwierdzeń
Akcje destrukcyjne (Sleep/Restart/Shutdown) mają wymuszone Confirm z czytelnym
pytaniem; akcje lekkie (Volume/Brightness) — nie. Dobry balans tarcia.

### S6 — Spójny model „B = wstecz/zamknij” w całym UI
Konsekwentne `A = potwierdź`, `B = wstecz/anuluj` na wszystkich nakładkach.
Przewidywalność mapowania to podstawa komfortu na padzie.

---

## 6. Weaknesses

### W1 — Onboarding ograniczony do provisioningu katalogu
Pierwsze uruchomienie seeduje aplikacje, ale **nie uczy modelu sterowania**
(Y vs Start, recall, chord). Przy interfejsie, którego cała wartość leży w
nawigacji padem, brak interaktywnego „jak to działa” jest istotną luką.

### W2 — Gęstość informacyjna nakładek systemowych
Network i Notifications to panele tekstowe o niskiej akcyjności i wysokiej
gęstości — sprzeczne z modelem „kciuki, dystans 2 m”. Notyfikacje to długa
przewijana lista identycznych wpisów bez grupowania/akcji.

### W3 — Brak hierarchii wizualnej między „warstwami”
Home Overlay, popovery kafelka i dialogi mają zbliżony styl (ciemne karty), więc
nie widać od razu **jak głęboko** jest się w nawigacji ani co jest modalne, a co
kontekstowe. Brak czytelnej „głębi” stosu nakładek.

### W4 — Niespójne pozycjonowanie nakładek
Suwaki/dialogi nie mają jednej, przewidywalnej kotwicy (patrz P4). Spójna pozycja
(np. zawsze dolne-centrum lub zawsze środek z przyciemnieniem tła) wzmocniłaby
poczucie struktury.

### W5 — Duplikacja semantyki UI (kafelki launchera vs. okna)
Ten sam rząd pełni dwie role (katalog aplikacji / lista uruchomionych okien) bez
mocnego rozróżnienia wizualnego (W3/P5).

### W6 — Funkcje odkrywalne tylko z hint bara (lub wcale)
Część akcji nie jest widoczna nigdzie poza momentem, gdy odpowiedni ekran jest
aktywny; chord Start+Select nie jest komunikowany w ogóle.

---

## 7. Propozycja: UX v2 *(sama propozycja — bez implementacji)*

> Zasada przewodnia v2: **każda decyzja optymalizowana pod kciuk na padzie i
> dystans kanapowy.** Klawiatura/mysz pozostają fallbackiem i nie dyktują
> układu. Celem nie jest dodawanie funkcji, lecz uproszczenie modelu mentalnego,
> ujednolicenie warstw i domknięcie odkrywalności.

### 7.1 Jeden, spójny model warstw (Layer System)
Zdefiniować jawnie trzy warstwy nakładek i nadać im **odrębną tożsamość
wizualną**, tak by głębokość była czytelna od pierwszego spojrzenia:
- **Warstwa 0 — Surface:** pulpit (tiles + top bar).
- **Warstwa 1 — Quick (kontekstowe):** popovery kafelka, suwaki — lekkie,
  przykotwiczone do elementu, bez przyciemniania tła.
- **Warstwa 2 — Modal (globalne):** Home Overlay, Confirm, Network,
  Notifications — wycentrowane, z przyciemnieniem tła, jawnie „przejmujące” pad.

Każda warstwa ma stałą pozycję, animację wejścia i styl ramki. Rozwiązuje
P4/W3/W4.

### 7.2 Ujednolicenie ścieżek do akcji systemowych
Wybrać **jedną kanoniczną drogę** do akcji systemowych i podporządkować jej
drugą:
- **Home Overlay = jedyne pełne menu systemowe** (działa wszędzie: pulpit i gra).
- **Top bar = tylko status + 2–3 najczęstsze szybkie akcje** (np. głośność,
  sieć, zegar) — przestaje być pełną kopią menu, staje się „paskiem stanu z
  skrótami”.

Eliminuje dwoistość z P2; użytkownik uczy się jednego gestu (Guide → menu).

### 7.3 Jedno menu kafelka, zawartość zależna od stanu
Dziś kafelek ma **dwa popovery na dwóch przyciskach** — `Y` („Actions”:
Launch/Restore/Close) i `Start` („Manage”: Move/Change color/Unpin). To
nietrafione: dwa prawie identyczne menu kontekstowe wymagają pamięci mięśniowej,
„który guzik to które menu” (P3).

v2 scala je w **jeden popover** (pod `Y`), którego zawartość zależy od **stanu
kafelka** — z kluczową zasadą: **opcje zarządzania kafelkiem są ukryte, gdy
aplikacja jest włączona.** Running tile to nie moment na przestawianie/zmianę
koloru/odpinanie — wtedy liczy się tylko „wróć / zamknij”.

```
 Catalog · idle              Catalog · running          Ephemeral window
 (nie działa)                (działa)                    (okno spoza katalogu)
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│ ▸ Launch        │        │ ▸ Restore       │        │ ▸ Restore       │
│ ───────────────  │        │   Close         │        │   Close         │
│   Move          │        └─────────────────┘        │ ───────────────  │
│   Change color  │         (zarządzanie ukryte —      │   Pin to menu   │
│   Unpin         │          brak Move/Color/Unpin)    └─────────────────┘
└─────────────────┘
```

Reguły:
- **Akcja główna na górze**, podświetlona, zależna od stanu: `Launch` /
  `Restore`. `A` na kafelku nadal wykonuje ją natychmiast (happy path bez
  otwierania menu).
- **Sekcja zarządzania** (`Move`, `Change color`, `Unpin`) widoczna **tylko dla
  kafelka idle**. Po uruchomieniu znika — odsłania się dopiero po zamknięciu
  aplikacji.
- **Okno efemeryczne** zamiast zarządzania oferuje jedyną sensowną akcję
  trwałości: **`Pin to menu`** (awans do katalogu — spójne z separatorem z 7.4).
- **`Start` zwolniony** — można go przeznaczyć na wartościowszy skrót globalny
  (np. szybki powrót do ostatnio uruchomionej aplikacji/gry).

Mapuje się to wprost na domenę: `compose_tile_menu` (Launch vs Restore/Close)
i `tile_management_menu` (Move/Color/Unpin vs Pin) z `domain/menu/tile.py` zostają
**złożone w jedną kompozycję**, w której gałąź zarządzania jest dołączana tylko
dla `AppTarget` w stanie *not running*. Rozwiązuje P3.

### 7.4 Kafelek niosący stan — „katalog” i „uruchomione” to jeden rząd

> **Korekta założenia.** Pierwotnie ten punkt proponował „dwa tryby rzędu”
> (Library vs Running). To błędne ramy: w modelu domeny (`domain/menu/tile.py`,
> `domain/lifecycle/tile_bar_view.py`) **kafelek z katalogu może być
> jednocześnie otwartym oknem** — to wtedy *ten sam jeden kafelek*, nie dwa byty
> do wyboru. „Katalog” i „uruchomione” to nie dwie listy, lecz **dwa wymiary
> stanu jednego kafelka**.

#### Faktyczny model (z kodu)

Istnieją dwa typy celów kafelka i trzeci, wynikowy stan:

| Stan kafelka | Czym jest | `A` (akcja główna) | Menu kontekstowe | „Manage” |
|---|---|---|---|---|
| **Catalog · idle** | `AppTarget`, nie działa | **Launch** | Launch | Move / Color / Unpin |
| **Catalog · running** | `AppTarget`, ma okno | **Restore** (przełącz) | Restore / Close | Move / Color / Unpin |
| **Ephemeral window** | `WindowTarget` (okno spoza katalogu) | **Restore** | Restore / Close | **Pin to menu** |

> Tabela opisuje **stan obecny** (dwa osobne menu: `Y` „Menu kontekstowe” i
> `Start` „Manage”). v2 scala te kolumny w jedno menu zależne od stanu, ukrywając
> zarządzanie dla kafla running — patrz **§7.3**.

> **Zakres.** KD celowo adresuje aplikacje **jednoekranowe** — Steam Big Picture,
> gry, wbudowany File Browser i YouTube — w praktyce niemal zawsze pełnoekranowe,
> które nie spawnują wielu okien. Relację „jeden `AppTarget` ↔ wiele okien” v2
> traktuje jako **poza zakresem**: kafelek running mapuje na jedno okno, a
> `Restore` pozostaje jednoznaczny.

Kluczowe wnioski, które v2 musi uszanować:
1. **Tożsamość, nie duplikat.** Uruchomiony Steam to ten sam kafelek co Steam w
   katalogu — `A` zmienia znaczenie z *Launch* na *Restore*, kafelek się nie
   rozdwaja.
2. **Okna efemeryczne to obywatele drugiej kategorii.** Niezapięte okno
   (`WindowTarget`) istnieje tylko póki żyje proces; jego jedyną akcją
   zarządzania jest **Pin** (awans do trwałego kafelka katalogu).

#### Makieta — jeden rząd „Pinned apps”, stan na kafelku

```
 ┌─ Pinned apps ──────────────────────────────────┐  ┊  ┌─ Open ──┐
 ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ╭┄┄┄┄╮  ┊  ╭┄┄┄┄┄┄┄┄╮
 │   ▣    │ │   📁   │ │   ▶    │ │   e    │ ┊  ＋ ┊  ┊  ┊   >_   ┊
 │ Steam  │ │ Files  │ │YouTube │ │  Edge  │ ┊ Add ┊  ┊  ┊ PShell ┊
 │        │ │ ▂▂▂▂▂▂ │ │ ▂▂▂▂▂▂ │ │        │ ╰┄┄┄┄╯  ┊  ┊ ▂▂▂▂▂▂ ┊
 └────────┘ └────────┘ └────────┘ └────────┘         ┊  ╰┄┄┄┄┄┄┄┄╯
   idle      running    running    idle    add-tile  ┊   running
             (fokus)                       (stały)   ┊  (niezapięte)

   legenda:  ▂▂▂   = pasek „running” (zawsze widoczny, nie tylko w trybie restore)
             ┊     = separator: po lewej trwały katalog, po prawej żywe okna
             ╭┄╮   = obrys kreskowany = afordancja / okno efemeryczne (nie w katalogu)
             ＋    = stały, syntetyczny kafel „Add app” (zawsze ostatni w Pinned apps)
```

Różnice względem stanu obecnego (screenshot 111017): pasek „running” jest
**stały** (widać go też na zwykłym launcherze, nie tylko w trybie Restore/Close),
a okna efemeryczne dostają **wizualnie odmienny, kreskowany obrys** i lądują **za
separatorem**.

#### Syntetyczny kafel „Add app” `[＋]`

Sekcja **Pinned apps** kończy się **zawsze obecnym, syntetycznym kafelkiem `[＋]`
(„Add app”)** — afordancją dodania nowej pozycji do katalogu. To nie jest
`AppTarget` ani `WindowTarget`, lecz osobny rodzaj celu (np. `AddTileTarget`):

- **Zawsze widoczny** jako ostatni kafel w Pinned apps (także gdy katalog jest
  pusty — wtedy jest jedynym kafelkiem, naturalnym punktem startu po prowizjonowaniu).
- **`A` na nim** otwiera **odchudzony picker provisioningu** — ten sam komponent
  co przy pierwszym uruchomieniu (`domain/provisioning`), ale z listą kandydatów
  **przefiltrowaną o już zapięte aplikacje**. Mechanika jest gotowa: każdy
  `CandidateApp` ma stabilny `key` (= nazwa pliku `.desktop`), więc wystarczy
  pominąć kandydatów, których `key` już istnieje w katalogu.
- **Wynik** wybranych pozycji ląduje jako nowe kafelki **przed** `[＋]` (który
  pozostaje na końcu).
- Wizualnie **odróżniony** (kreskowany obrys, wyszarzony, ikona `＋`), by nie
  mylił się z realną aplikacją — nie ma stanu running ani menu Manage.

```
        [＋ Add app]  ──A──►   ┌── Add app ─────────────────────────┐
                              │ ☐ Lutris                            │
                              │ ☑ Heroic Games Launcher             │  ← A: toggle
                              │ ☐ Discord                           │
                              │ ☐ OBS Studio                        │
                              │ ─────────────────────────────────── │
                              │              [ Add 1 ]   (Start)     │  ← Start: zatwierdź
                              └─────────────────────────────────────┘
                                (już zapięte: Steam, Files, YouTube,
                                 Edge — odfiltrowane z listy)
```

#### Co to rozwiązuje
- **P5 / W5** — znika fałszywa dychotomia „launcher vs lista okien”: jeden rząd,
  stan na kafelku, separator dla efemeryd.
- **P6** — stan „co działa” jest widoczny **zawsze** (stały pasek), bez wchodzenia
  w osobny tryb. Opcjonalnie dyskretny licznik „N running” przy zegarze.
- **Odkrywalność dodawania aplikacji** — dziś katalog rozszerza się przez ręczne
  pliki `.desktop` lub ponowny provisioning z CLI; kafel `[＋]` czyni to czynnością
  pierwszej kategorii, dostępną **z pada**, bez myszki i terminala. Domyka też
  pętlę: provisioning przestaje być tylko zdarzeniem pierwszego uruchomienia.
- **Spójność z domeną** — `Pin` dla okna efemerycznego i `Unpin` dla kafelka
  katalogu stają się czytelne wizualnie (przejście przez separator: zapięcie =
  przeniesienie z prawej na lewą stronę).

### 7.5 Interaktywny onboarding sterowania (Controller Tutorial)
Po provisioningu — krótki, pomijalny **interaktywny samouczek pada**: „naciśnij
A, by uruchomić”, „naciśnij Y dla opcji kafelka”, „przytrzymaj Guide, by otworzyć
menu”. Plus stała, wywoływalna **„ściąga sterowania”** (np. z Home Overlay →
Help). Komunikuje też chord/recall. Rozwiązuje W1/P7/W6.

### 7.6 Przeprojektowanie paneli systemowych pod pad
- **Network v2:** zacząć od **listy wybieralnych sieci** (Wi-Fi) z fokusowalnymi
  wierszami i akcją Connect/Disconnect na `A`; szczegóły diagnostyczne (IP,
  interfejs) zwinięte pod „Details”. Mniej tekstu, więcej akcji (P8/W2).
- **Notifications v2:** grupowanie po aplikacji/typie, zwijanie powtórzeń
  („Screenshot copied ×6”), akcje per-wpis na `A` (np. Open / Dismiss), `X` =
  „Clear all”. (W2)

### 7.7 Domknięcie lokalizacji
Jeden audyt i18n: każdy widoczny string przez ten sam kontekst tłumaczeniowy, aby
„Volume/Głośność” i „Brightness/Jasność” były spójne we **wszystkich** ekranach
naraz. Test: przełączenie locale zmienia 100% widocznych etykiet, zero mieszanki.
Rozwiązuje P1.

### 7.8 „Zawsze widoczny” kontrakt sterowania
Utrzymać mocną stronę (dynamiczny hint bar), ale dodać:
- **glify przycisków zamiast/obok słów** (rozpoznawalne ikony A/B/X/Y/Guide),
  bo na padzie ikona „przycisku A” czyta się szybciej niż słowo „Select”;
- **wykrywanie typu pada** (Xbox/PlayStation/Nintendo) i dopasowanie glifów oraz
  układu A/B (krzyż vs koło) — kluczowe dla gamepad-first, eliminuje błędy
  „nacisnąłem nie ten guzik”. Wzmacnia S1/S6.

### 7.9 Spójny system fokusu i „powrotu”
Zagwarantować, że **`B` zawsze cofa o dokładnie jedną warstwę** (popover →
kafelek → … ) i nigdy nie „przeskakuje” ani nie zamyka za dużo; oraz że po
zamknięciu dowolnej nakładki fokus wraca **dokładnie tam, skąd przyszedł**. To
fundament komfortu nawigacji wyłącznie padem.

---

### 7.10 Home Overlay v2 — kontekstowe menu z regulacją inline

Przeprojektowanie Home Overlay (dziś: pionowa lista + osobne pod-overlaye suwaków,
screeny 110906/110723) w **jeden kontekstowy ekran**: regulacja inline + siatka
kart akcji, z zawartością zależną od tego, **skąd** menu zostało przywołane.

#### Dwa konteksty (KD nie ocenia typu aplikacji)

Menu ma dokładnie dwa warianty; KD **nie orzeka „gra vs aplikacja”** — używa
nazwy procesu w pierwszym planie:

| Kontekst | Nagłówek | Sekcja akcji |
|---|---|---|
| **Home** (z ekranu głównego) | „Menu Globalne” | system (Power, …) |
| **Aplikacja** (recall nad oknem) | „Kontekst: {Nazwa}” | `Wróć do {Nazwa}` · `Zamknij {Nazwa}` · `Ekran główny` + (warunkowo) HUD |

**HUD** to **warunkowo obecny wiersz** w kontekście aplikacji, odsłaniany tylko
gdy backend HUD zgłasza zdolność (gra wykryta na Linuksie / RTSS hookuje na
Windows — patrz README). Rama: *„HUD dostępny tu”*, nie *osąd typu aplikacji*.
Etykiety nigdy nie mówią „gra” — zawsze nazwa.

#### Makieta — kontekst Desktop

```
+-------------------------------------------------------------+
|                       KASUAL DESKTOP                        |
|                     [ Menu Globalne ]                       |
+-------------------------------------------------------------+
|  (🔊) Głośność:  [██████████████████████████░░░░░░] 80%    |  ← Quick adjust
|  (☀) Jasność:    [████████████░░░░░░░░░░░░░░░░░░░░] 50%    |    (tylko gdy
+-------------------------------------------------------------+      backlight)
|   +-------------+  +-------------+  +-------------+          |
|   | (🌙) Uśpij ▾|  | (🌐) Sieć   |  | (🔔) Powiad.|          |  ← Akcje (siatka)
|   |  Zasilanie  |  |  …          |  |  …          |          |
|   +-------------+  +-------------+  +-------------+          |
+-------------------------------------------------------------+
| [LB/RB] Sekcja | [D-Pad] Nawig. | (A) Wybierz | (B) Zamknij |
+-------------------------------------------------------------+
```

#### Makieta — kontekst Aplikacji (z warunkowym HUD)

```
+-------------------------------------------------------------+
|                       KASUAL DESKTOP                        |
|                 [ Kontekst: Steam ]                         |
+-------------------------------------------------------------+
|  (🔊) Głośność:  [██████████████████████████░░░░░░] 80%    |
|  (☀) Jasność:    [████████████░░░░░░░░░░░░░░░░░░░░] 50%    |
+-------------------------------------------------------------+
|   +-------------+  +-------------+  +-------------+          |
|   | (▶) Wróć do |  | (✕) Zamknij |  | (🏠) Ekran    |          |
|   |    Steam    |  |    Steam    |  |   główny     |          |
|   +-------------+  +-------------+  +-------------+          |
|   ────────────────────────────────────────────────         |
|   (▣) Statystyki HUD:  [ WŁĄCZONE ]    ← tylko gdy dostępny  |
+-------------------------------------------------------------+
| [LB/RB] Sekcja | [D-Pad] Nawig. | (A) Wybierz | (B) Wznów   |
+-------------------------------------------------------------+
```

#### Model wejścia — bumpery jako przełącznik sekcji (rozwiązuje konflikt stref)

Overlay ma kilka typów kontrolek (suwaki, karty, toggle). Żeby `L/R` nie znaczyło
raz „reguluj”, raz „przesuń fokus”, **przełączanie sekcji schodzi z D-pada na
bumpery**:

- **`LB` / `RB`** — skok między sekcjami (Quick adjust ⇄ Akcje ⇄ HUD). D-pad
  zostaje **czysto w sekcji**.
- W **Quick adjust**: `D-pad ↕` wybiera suwak, `◄ ►` reguluje na żywo
  (nav_label „Adjust”, jak w `hints.py`).
- W **Akcjach**: `D-pad` nawiguje 2D po siatce, `A` aktywuje.
- **`LT` / `RT`** — **globalna głośność −/+**, niezależnie od fokusu (a docelowo
  i poza overlayem). Daje głośności prymat „zawsze pod ręką” **bez** czynienia jej
  celem fokusu.
- **`B`** — kontekstowy powrót: „Zamknij Menu” (Desktop) / „Wznów {Nazwa}”
  (Aplikacja) — spójnie z §7.9.

Hint bar jest **strefowy**: zmienia się przy przejściu fokusu między Quick a
siatką (wykorzystuje istniejącą mocną stronę S1).

#### Quick adjust — Volume i Brightness

- Para **wizualnie nierozłączna**, ale o **różnym poziomie dostępu**: głośność ma
  dodatkową ścieżkę `LT/RT`, jasność nie.
- **Suwak jasności pojawia się tylko, gdy platforma ma sterowalny backlight**
  (laptop/DDC). Na desktopie z monitorem zewnętrznym znika — żadnego martwego
  suwaka; głośność zostaje sama.

#### Power jako pad-dropdown (split-button ze „sticky last-choice”)

Zamiast zawsze pokazywać „świętą trójcę”, kafel **Power** pokazuje
**skonfigurowaną akcję domyślną**, z pełnym wyborem o dwa ruchy dalej:

```
  stan domyślny                  po (Y) — wybór
 ┌──────────────────┐          ┌──────────────────┐
 │ (🌙) Uśpij     ▾ │          │ (🌙) Uśpij     ▴ │
 │   Zasilanie  (Y) │          ├──────────────────┤
 └──────────────────┘          │ ● Uśpij          │  ← obecny default
   A → Uśpij od razu           │   Restart        │
   Y → rozwiń wybór            │   Wyłącz         │  ← A: wykonaj TERAZ
                               └──────────────────┘     i ustaw jako default
                                (A) Wywołaj i ustaw | (B) Anuluj
```

Reguły:
1. **`A` na kaflu** = wykonaj akcję domyślną od razu (z istniejącym confirm).
2. **`Y`** rozwija listę Sleep/Restart/Shutdown; `A` na pozycji **wykonuje ją i
   utrwala jako nowy default** (jeden ruch = użycie + zapamiętanie).
3. **Default zmienia się dopiero przy *potwierdzonym* wykonaniu** (confirm „Yes”).
   Wycofanie na confirmie (`No`/`B`) **nie** zmienia defaultu — chroni przed
   przypadkowym przestawieniem i odruchowym `A` następnym razem.
4. **Brak osobnego „ustaw bez wykonania”** — wybór *jest* użyciem; kto chce inny
   default, ustawi go naturalnie przy następnym faktycznym użyciu.
5. Chevron `▾` i glif `(Y)` **widoczne zawsze** — rozwijalność jest odkrywalna
   (łata na P7/W6).

Jedna persystowana preferencja (config) jest źródłem prawdy o „ulubionej” akcji —
ten sam default zasila pojedynczy przycisk Power na top barze (rzadka, deliberate
ścieżka), więc top bar nie dubluje już pełnej trójcy.

#### Co to rozwiązuje
- **P2 / W2** — kasuje pod-overlay suwaka (regulacja inline) i porządkuje
  dwoistość ścieżek systemowych: częste pod ręką (overlay), rzadkie na top barze.
- **Konflikt stref** — bumpery jako sekcje + strefowy hint bar dają jednoznaczne
  `L/R` na każdym ekranie.
- **„Święta trójca”** — pad-dropdown: częsta ścieżka = 1 `A`, rzadka = 2 ruchy,
  z samouczącym się defaultem szanującym stałą preferencję użytkownika.
- **Brak osądu typu aplikacji** — etykiety z nazwą procesu, HUD jako zdolność.

---

### 7.11 Terminologia — „Home” zamiast „Desktop”

**Problem.** Słowo „Desktop / pulpit” wskazuje dwa różne byty: **pulpit systemu**
(Plasma/Windows — to, co user uważa za „swój pulpit”) oraz **ekran główny KD**
(launcher z zegarem i kaflami). Dzisiejsze „Return to Desktop / Wróć do pulpitu”
prowadzi do *launchera KD*, a user może oczekiwać pulpitu OS — fałszywa obietnica.

**Zasada.** User jest właścicielem słowa „pulpit” = pulpit OS. KD oddaje to słowo
i nazywa swój ekran główny idiomem konsolowym **„Home / Ekran główny”** (jak
Xbox/Steam) — bytem odrębnym od gier i od pulpitu OS.

**Kanoniczny słownik (user-facing; PL + EN):**

| Referent | PL | EN |
|---|---|---|
| Ekran główny KD (launcher) | **Ekran główny** | **Home screen** |
| „wróć do launchera KD” | **Wróć do ekranu głównego** | **Return to Home screen** |
| ukryj KD → pokaż OS (dziś `Minimize Desktop`) | **Minimalizuj Kasual Desktop** | **Minimize Kasual Desktop** |
| pulpit systemu operacyjnego | **Pulpit systemu** | **System desktop** |
| nagłówek / marka | **Kasual Desktop** (zostaje) | **Kasual Desktop** (zostaje) |

**Zakres.** Zmieniamy wyłącznie **stringi user-facing** (`actions.py`, `home.py`,
`locale/*.ts`). Wewnętrzny słownik kodu (`Desktop`, `RETURN_TO_DESKTOP`,
`HIDE_DESKTOP`) **może zostać** — implementacja ≠ copy. Lista stringów do zmiany:
patrz `ux_plan.md` → Faza 1.5.

---

### Podsumowanie kierunku v2
Kasual Desktop ma **bardzo dobre fundamenty gamepad-first** (recall, dynamiczny
hint bar, jedno źródło akcji, czytelne kafelki). v2 nie powinno dokładać funkcji,
lecz **uprościć model mentalny**: jedna droga do akcji systemowych, jedno menu
kafelka, jasne warstwy nakładek, widoczny stan „co działa”, domknięta lokalizacja
i onboarding sterowania. Efektem ma być interfejs, który da się opanować padem w
ciągu pierwszych dwóch minut i którego nigdy nie trzeba „dotknąć myszką”.

---

## 8. UX v2.1 *(side-project, PoC-first)* — Trwała powierzchnia Home

> **To nie jest część UX v2.** Osobny, eksperymentalny tor, wdrażany **na końcu**,
> **po PoC**. Cel: skrócić „odczyt godziny w grze” (dziś 6 czynności) i ujednolicić
> chrome KD w jeden trwały komponent zamiast osobnego top bara i tworzonego
> per-press Home Overlay (`HomeOverlayFactory` tworzy świeży overlay na każde
> BTN_MODE → map/unmap → animacje KWin).

### Motywacja
Z poziomu gry, by sprawdzić godzinę, trzeba dziś: pauza → overlay → powrót do
pulpitu → odczyt → overlay → powrót do gry. Zegar w nagłówku Home Overlay
sprowadza to do: pauza → BTN_MODE → odczyt → wznów. Dalej idzie pomysł rozpuszczenia
top bara w **jeden trwały komponent „Home”** o stanach zwinięty/rozwinięty.

### Model — trzy konteksty

| Kontekst | Gdy **niewywołany** | Gdy **wywołany** (BTN_MODE) |
|---|---|---|
| **1. Widok KD** (pulpit) | **zwinięty, zawsze widoczny** — sam nagłówek (zegar + data) | **rozwinięty** — nagłówek + content menu |
| **2. KD zminimalizowany** | **zamknięty** (brak chrome) | pojawia się (klik / hold BTN_MODE) |
| **3. Aplikacja na wierzchu** | **zamknięty** (brak chrome) | pojawia się — content **dopasowany do kontekstu aplikacji** (§7.10) |

Kluczowe: **trwały, zwinięty nagłówek istnieje wyłącznie w widoku KD** (kontekst 1).
Nad grą i przy zminimalizowanym KD obowiązuje dotychczasowy model „pojawia się na
żądanie”. Dzięki temu **nie ma trwałej powierzchni nad pełnoekranową grą** —
znika ryzyko prowokowania paneli KWin (problem, przez który overlay ma dziś
`keyboard=NONE`).

```
  Kontekst 1 — widok KD
  ┌──────────────────────────────────────┐      ┌──────────────────────────────────────┐
  │  Sunday 28 Jun 2026   11:06           │      │  Sunday 28 Jun 2026   11:06           │  ← nagłówek (stały)
  └──────────────────────────────────────┘      ├──────────────────────────────────────┤
            zwinięty (sam nagłówek)              │  (🔊) Głośność  [██████░░] 80%        │
                                                 │  ... sekcje §7.10 ...                  │  ← content
              ── BTN_MODE ──►                    └──────────────────────────────────────┘
                                                            rozwinięty
```

### Rozpad top bara
Top bar znika jako osobny byt; jego role się rozdzielają:
- **status** (zegar, data, sieć, w przyszłości bateria, badge powiadomień) → **zwinięty nagłówek**;
- **akcje** (volume, brightness, power, network, notifications) → **rozwinięty content** (i tak mają tam dom w §7.10).

### Warunek techniczny (PoC)
- **Morph bez map/unmap:** zwijanie/rozwijanie to wewnętrzna zmiana geometrii/opacity
  **jednej, stale zmapowanej powierzchni** (w widoku KD) — wzorem trwałego hint bara,
  by uniknąć animacji KWin. Konteksty 2/3 nadal mapują na żądanie.
- **Parytet Windows:** brak layer-shell — ten sam komponent jako desktop surface;
  model collapse/expand musi działać też tam.
- **Zakres PoC:** zweryfikować morph collapse↔expand w widoku KD i zastąpienie top
  bara nagłówkiem — *przed* podjęciem decyzji o pełnej implementacji.

### Status
**Side-project. Najpierw PoC, potem (ewentualnie) implementacja jako ostatni punkt
planu — po całym UX v2.** Patrz `ux_plan.md` → Faza 6.
