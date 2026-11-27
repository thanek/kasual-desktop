{
  const { Intent } = KasualPad;

  const KeyKind = Object.freeze({
    CHARACTER: "character",
    DIACRITICS: "diacritics",
    SPACE: "space",
    BACKSPACE: "backspace",
    DONE: "done",
  });

  const DIACRITIC_OF = { a: "ą", c: "ć", e: "ę", l: "ł", n: "ń", o: "ó", s: "ś", z: "ż", x: "ź" };
  const BASE_OF = Object.fromEntries(Object.entries(DIACRITIC_OF).map(([base, diacritic]) => [diacritic, base]));

  const SPECIAL_KEY_TYPED_AS = { " ": KeyKind.SPACE, Backspace: KeyKind.BACKSPACE, Enter: KeyKind.DONE };

  const character = (value) => Object.freeze({ kind: KeyKind.CHARACTER, value, units: 1 });
  const special = (kind, units) => Object.freeze({ kind, units });
  const row = (keys, offset = 0) => Object.freeze({ keys, offset });

  const ROWS = Object.freeze([
    row([..."1234567890"].map(character)),
    row([..."qwertyuiop"].map(character)),
    row([..."asdfghjkl"].map(character), 0.5),
    row([..."zxcvbnm.@-"].map(character)),
    row([
      special(KeyKind.DIACRITICS, 2),
      special(KeyKind.SPACE, 4),
      special(KeyKind.BACKSPACE, 2),
      special(KeyKind.DONE, 2),
    ]),
  ]);

  const STARTING_ROW = 1;

  const centerOf = (rowIndex, column) => {
    const { keys, offset } = ROWS[rowIndex];
    const unitsBefore = keys.slice(0, column).reduce((sum, key) => sum + key.units, 0);
    return offset + unitsBefore + keys[column].units / 2;
  };

  const nearestColumn = (rowIndex, x) => {
    let nearest = 0;
    ROWS[rowIndex].keys.forEach((_, column) => {
      if (Math.abs(centerOf(rowIndex, column) - x) < Math.abs(centerOf(rowIndex, nearest) - x)) nearest = column;
    });
    return nearest;
  };

  const baseOf = (character) => BASE_OF[character] ?? character;

  const isKeyFor = (typed) => (key) => {
    const specialKind = SPECIAL_KEY_TYPED_AS[typed];
    if (specialKind) return key.kind === specialKind;
    return key.kind === KeyKind.CHARACTER && key.value === baseOf(typed.toLowerCase());
  };

  KasualPad.KeyKind = KeyKind;
  KasualPad.KEYBOARD_ROWS = ROWS;
  KasualPad.withDiacritic = (value) => DIACRITIC_OF[value] ?? value;
  KasualPad.isDiacritic = (typed) => typed.toLowerCase() in BASE_OF;
  KasualPad.typesSpecialKey = (typed) => typed in SPECIAL_KEY_TYPED_AS;

  KasualPad.KeyboardCursor = class {
    #row = STARTING_ROW;
    #column = 0;

    get key() {
      return ROWS[this.#row].keys[this.#column];
    }

    isAt(rowIndex, column) {
      return this.#row === rowIndex && this.#column === column;
    }

    moveToKeyFor(typed) {
      const rowIndex = ROWS.findIndex(({ keys }) => keys.some(isKeyFor(typed)));
      if (rowIndex < 0) return false;
      this.#row = rowIndex;
      this.#column = ROWS[rowIndex].keys.findIndex(isKeyFor(typed));
      return true;
    }

    move(direction) {
      if (direction === Intent.LEFT) return this.#moveColumn(-1);
      if (direction === Intent.RIGHT) return this.#moveColumn(+1);
      return this.#moveRow(direction === Intent.UP ? -1 : +1);
    }

    #moveColumn(step) {
      const column = this.#column + step;
      if (column < 0 || column >= ROWS[this.#row].keys.length) return false;
      this.#column = column;
      return true;
    }

    #moveRow(step) {
      const rowIndex = this.#row + step;
      if (rowIndex < 0 || rowIndex >= ROWS.length) return false;
      this.#column = nearestColumn(rowIndex, centerOf(this.#row, this.#column));
      this.#row = rowIndex;
      return true;
    }
  };
}
