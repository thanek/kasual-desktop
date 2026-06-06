# Plan: aplikacje z plików `.desktop` zamiast `apps.yml`

## Context
Dziś aplikacje KD definiuje pojedynczy `apps.yml` (lista dictów: `name`, `command`, `args`,
`icon` qtawesome, `color`, `recall_menu_trigger`, `launch_hide_grace_ms`). Użytkownik chce
przejść na standard freedesktop: pliki `*.desktop` w `~/.config/kasual-desktop/apps/`, z
dodatkowymi ustawieniami KD (kolor kafla, recall trigger, hide-grace, zmienne env) wyrażonymi
kluczami `X-Kasual-*`. Cel: bardziej natywny, edytowalny format „jeden plik = jedna apka",
łatwy do dystrybucji i rozszerzania.

Decyzje (potwierdzone z użytkownikiem):
- **Ikona**: priorytet `X-Kasual-Icon` (qtawesome, np. `fa5b.steam`); fallback standardowy `Icon=` (motyw, `QIcon.fromTheme`).
- **apps.yml**: usuwany całkowicie; folder jedynym źródłem; przykłady w repo.
- **Kolejność**: klucz `X-Kasual-Order` (int rosnąco); remis → nazwa pliku.
- **Env**: tak — `X-Kasual-Env=KEY1=val1;KEY2=val2`, mergowane do środowiska procesu.

## Format pliku `.desktop`
Lokalizacja: `${XDG_CONFIG_HOME:-~/.config}/kasual-desktop/apps/*.desktop`. Sekcja `[Desktop Entry]`.

| Klucz | → pole app dict | Uwagi |
|---|---|---|
| `Name` | `name` | wymagane |
| `Exec` | `command` + `args` | parsowane `shlex`, usuwane field-codes `%f %F %u %U %i %c %k %d %D %n %N %v %m`, `%%`→`%` |
| `Icon` | `icon_theme` | nazwa motywu/ścieżka; użyte gdy brak `X-Kasual-Icon` |
| `X-Kasual-Icon` | `icon` | qtawesome (priorytet) |
| `X-Kasual-Color` | `color` | domyślnie `#2e3440` |
| `X-Kasual-RecallMenuTrigger` | `recall_menu_trigger` | `BTN_MODE_CLICK`/`BTN_MODE_HOLD_1S`, domyślnie CLICK |
| `X-Kasual-HideGraceMs` | `launch_hide_grace_ms` | int, domyślnie 0 |
| `X-Kasual-Env` | `env` | dict z `K=V;K2=V2` |
| `X-Kasual-Order` | (sortowanie) | int; brak → +∞, remis → nazwa pliku |

Honorowane standardowe: pomiń plik gdy `Type` ≠ `Application`, lub `NoDisplay=true`, lub `Hidden=true`.
`id` (= indeks po sortowaniu) i `type='app'` nadawane jak dziś — kształt dict pozostaje zgodny
z obecnymi konsumentami (`desktop.py`, `tile_bar.py`, `app_manager.py`, `app.py`).

## Implementacja

### 1. Nowy moduł loadera — `src/system/app_config.py`
`load_apps() -> list[dict]` (wolny od Qt — wołany przed `QApplication`):
- katalog z `os.environ.get("XDG_CONFIG_HOME")` lub `Path.home()/".config"`, `/kasual-desktop/apps`;
  `mkdir(parents=True, exist_ok=True)` + log ścieżki (wygodne „tu wrzuć pliki").
- `glob("*.desktop")`; każdy parsowany `configparser.ConfigParser(interpolation=None)` z
  `parser.optionxform = str` (zachowanie wielkości liter — klucze .desktop są case-sensitive,
  a `interpolation=None` chroni `%` w `Exec`).
- pomiń pliki bez `[Desktop Entry]`/`Name`/`Exec`, oraz `Type!=Application`/`NoDisplay`/`Hidden`.
- `Exec` → `shlex.split`, odfiltruj tokeny field-code, `%%`→`%`; pierwszy token = `command`, reszta = `args`.
- `X-Kasual-Env` → dict (split `;` potem `=`, ignoruj puste).
- `X-Kasual-Order` → int (domyślnie duża wartość); sort po `(order, filename)`.
- zwróć dicty z polami jw. (`icon` lub `None`, `icon_theme` lub `None`, `env` dict).
- błąd parsowania jednego pliku → log warning i pomiń (nie wywracaj całości).

### 2. `src/main.py`
- usuń `import yaml` i obecne `_load_apps()` (czytające `apps.yml`).
- `from system.app_config import load_apps`; w `main()` `apps = load_apps()`.
- pusta lista jest OK (KD bez kafli nie może się wywrócić — `tile_bar._clamp_index` obsługuje `total==0`).

### 3. `src/system/app_manager.py` — env per-apka
W `launch()` (już buduje `env = os.environ.copy(); env.pop("QT_WAYLAND_SHELL_INTEGRATION")`):
dołóż `env.update(app.get("env", {}))` przed `Popen(..., env=env)`. Strip integracji zostaje.

### 4. `src/desktop/tile_bar.py` — ikona kafla (kontekst Qt)
W budowie kafli statycznych (ok. linii 84–90) zamiast samego `icon_name=app.get("icon",...)`:
- jeśli `app.get("icon")` (qtawesome) → `AppTile(icon_name=<qta>, color=...)` jak dziś;
- elif `app.get("icon_theme")` → `qicon = QIcon.fromTheme(<name>)`; jeśli nie-null →
  `AppTile(icon_name="fa5s.desktop", qicon=qicon, ...)`, w przeciwnym razie fallback qta;
- else → domyślny `fa5s.desktop`.
`AppTile.__init__` już przyjmuje `qicon` (używane przy kaflach dynamicznych) — wykorzystujemy istniejącą ścieżkę.

### 5. `requirements.txt`
Usuń `PyYAML` (jedyny użytkownik to dawny `_load_apps`; potwierdzone grepem, że nigdzie indziej w `src`/`apps`).

### 6. Przykłady + dokumentacja
- nowy katalog `examples/apps/` z 5 plikami `.desktop` odwzorowującymi obecny `apps.yml`
  (`steam.desktop` z `X-Kasual-RecallMenuTrigger=BTN_MODE_HOLD_1S` i `X-Kasual-HideGraceMs=500`, itd.).
- usuń `apps.yml`.
- README: opis lokalizacji, tabela kluczy, instrukcja „skopiuj `examples/apps/*` do `~/.config/kasual-desktop/apps/`".
- **Uwaga migracyjna (bundled apps)**: `yt`/`file_browser` mają w `apps.yml` ścieżki względne
  (`apps/yt/yt.sh`). W `.desktop` w `~/.config` `Exec` musi być **bezwzględny** (lub skrypt w PATH);
  w przykładach użyć placeholdera ścieżki bezwzględnej + adnotacji do edycji. Loader przekazuje
  `command` 1:1 do `Popen` (rozwiązanie przez PATH) — bez prób „naprawiania" ścieżek względnych.

## Testy
- nowy `tests/test_app_config.py`: parsowanie `Exec` (cytowanie + field-codes), mapowanie
  `X-Kasual-*`, `X-Kasual-Env` → dict, sort wg `X-Kasual-Order`+nazwa, pomijanie
  `NoDisplay`/`Hidden`/`Type!=Application`, plik wadliwy pomijany. Użyć `tmp_path` z plikami `.desktop`.
- `tests/test_app_manager.py`: rozszerz `test_creates_process_with_correct_command` lub dodaj
  przypadek, że `env` zawiera wartości z `app["env"]` (obok dotychczasowego braku `QT_WAYLAND_SHELL_INTEGRATION`).
- reszta testów bez zmian (żaden nie odwołuje się do `apps.yml`/`_load_apps`).

## Weryfikacja
1. `source venv/bin/activate && python -m pytest -q` — całość zielona (185 + nowe).
2. Skopiuj `examples/apps/*.desktop` do `~/.config/kasual-desktop/apps/`, uruchom KD:
   - kafle pojawiają się w kolejności wg `X-Kasual-Order`, z właściwymi kolorami i ikonami
     (qtawesome tam gdzie `X-Kasual-Icon`, motyw tam gdzie samo `Icon`).
   - Steam: recall trigger HOLD_1S i hide-grace 500 ms działają jak dotąd.
   - apka z `X-Kasual-Env` startuje z ustawionymi zmiennymi (np. testowo `X-Kasual-Env=FOO=bar` + apka logująca env).
3. Pusty/nieistniejący folder → KD startuje bez kafli, bez błędu; w logu ścieżka katalogu.
