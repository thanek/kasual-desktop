{
  const { Intent, Cue, KeyKind, Hints } = KasualPad;

  const KEY_UNIT_PX = 64;
  const KEY_GAP_PX = 8;
  const PASSWORD_MASK = "•";

  const STYLE = `
    :host {
      all: initial;
      position: fixed;
      left: 0;
      right: 0;
      bottom: 108px;
      display: flex;
      justify-content: center;
      pointer-events: none;
      z-index: 2147483647;
      font: 22px system-ui, sans-serif;
    }
    .panel {
      padding: 20px;
      border-radius: 24px;
      background: rgba(46, 52, 64, 0.95);
      box-shadow: 0 12px 48px rgba(0, 0, 0, 0.6);
      display: flex;
      flex-direction: column;
      gap: ${KEY_GAP_PX}px;
    }
    .preview {
      box-sizing: border-box;
      height: 56px;
      padding: 0 16px;
      margin-bottom: 8px;
      border-radius: 12px;
      background: #2e3440;
      color: white;
      display: flex;
      align-items: center;
      white-space: pre;
      overflow: hidden;
    }
    .preview::after { content: "▏"; color: #88c0d0; }
    .row { display: flex; gap: ${KEY_GAP_PX}px; }
    .key {
      box-sizing: border-box;
      height: ${KEY_UNIT_PX}px;
      border-radius: 12px;
      background: #434c5e;
      color: white;
      display: grid;
      place-items: center;
      transition: background 80ms, transform 80ms;
    }
    .key.selected { background: #88c0d0; color: #2e3440; transform: scale(1.08); font-weight: bold; }
    .key.active { box-shadow: inset 0 0 0 3px #88c0d0; }
  `;

  const KEYBOARD_HINTS = Hints.screen({
    clusters: [Hints.NAVIGATE, Hints.cluster(["LT"], "diacritics")],
    actions: [
      Hints.action("A", "type"),
      Hints.action("X", "delete"),
      Hints.action("Y", "space"),
      Hints.action("B", "close"),
    ],
  });

  const SPECIAL_LABELS = {
    [KeyKind.DIACRITICS]: () => "ĄĘ",
    [KeyKind.SPACE]: () => browser.i18n.getMessage("space"),
    [KeyKind.BACKSPACE]: () => "⌫",
    [KeyKind.DONE]: () => browser.i18n.getMessage("done"),
  };

  const element = (tag, className) => {
    const node = document.createElement(tag);
    node.className = className;
    return node;
  };

  const widthOf = (units) => units * KEY_UNIT_PX + (units - 1) * KEY_GAP_PX;

  const buildRows = () => KasualPad.KEYBOARD_ROWS.map(({ keys, offset }) => {
    const rowNode = element("div", "row");
    rowNode.style.paddingLeft = `${offset * (KEY_UNIT_PX + KEY_GAP_PX)}px`;
    const keyNodes = keys.map(({ units }) => {
      const keyNode = element("div", "key");
      keyNode.style.width = `${widthOf(units)}px`;
      return keyNode;
    });
    rowNode.append(...keyNodes);
    return { rowNode, keyNodes };
  });

  KasualPad.OnScreenKeyboard = class {
    #feedback;
    #cursor = new KasualPad.KeyboardCursor();
    #input = null;
    #diacritics = false;
    #host = element("div", "");
    #preview = element("div", "preview");
    #rows = buildRows();

    #intentActions = {
      [Intent.UP]: () => this.#move(Intent.UP),
      [Intent.DOWN]: () => this.#move(Intent.DOWN),
      [Intent.LEFT]: () => this.#move(Intent.LEFT),
      [Intent.RIGHT]: () => this.#move(Intent.RIGHT),
      [Intent.SELECT]: () => this.#pressSelectedKey(),
      [Intent.CLOSE]: () => this.#deleteLastCharacter(),
      [Intent.ACTIONS]: () => this.#type(" "),
      [Intent.VOLUME_DOWN]: () => this.#toggleDiacritics(),
      [Intent.CANCEL]: () => this.close(),
    };

    #keyActions = {
      [KeyKind.CHARACTER]: (key) => this.#type(this.#labelOf(key)),
      [KeyKind.DIACRITICS]: () => this.#toggleDiacritics(),
      [KeyKind.SPACE]: () => this.#type(" "),
      [KeyKind.BACKSPACE]: () => this.#deleteLastCharacter(),
      [KeyKind.DONE]: () => this.close(),
    };

    constructor(feedback) {
      this.#feedback = feedback;
      const panel = element("div", "panel");
      panel.append(this.#preview, ...this.#rows.map(({ rowNode }) => rowNode));
      const style = element("style", "");
      style.textContent = STYLE;
      this.#host.attachShadow({ mode: "closed" }).append(style, panel);
    }

    get isOpen() {
      return this.#input !== null;
    }

    hints() {
      return KEYBOARD_HINTS;
    }

    open(input) {
      this.#input = input;
      this.#diacritics = false;
      input.focus({ preventScroll: true });
      this.#render();
      KasualPad.keepInOverlayRoot(this.#host);
      this.#feedback.play(Cue.POPUP_OPEN);
    }

    close() {
      this.#input = null;
      this.#host.remove();
      this.#feedback.play(Cue.POPUP_CLOSE);
    }

    handle(intent) {
      if (!this.#input.isConnected) {
        this.close();
        return;
      }
      this.#intentActions[intent]?.();
    }

    #move(direction) {
      if (!this.#cursor.move(direction)) return;
      this.#feedback.play(Cue.CURSOR);
      this.#render();
    }

    #pressSelectedKey() {
      const { key } = this.#cursor;
      this.#feedback.play(Cue.SELECT);
      this.#keyActions[key.kind](key);
    }

    #type(text) {
      KasualPad.replaceText(this.#input, this.#input.value + text);
      this.#render();
    }

    #deleteLastCharacter() {
      KasualPad.replaceText(this.#input, this.#input.value.slice(0, -1));
      this.#render();
    }

    #toggleDiacritics() {
      this.#diacritics = !this.#diacritics;
      this.#render();
    }

    #labelOf(key) {
      if (key.kind !== KeyKind.CHARACTER) return SPECIAL_LABELS[key.kind]();
      return this.#diacritics ? KasualPad.withDiacritic(key.value) : key.value;
    }

    #render() {
      const { value, type } = this.#input;
      this.#preview.textContent = type === "password" ? PASSWORD_MASK.repeat(value.length) : value;
      KasualPad.KEYBOARD_ROWS.forEach(({ keys }, rowIndex) => {
        keys.forEach((key, column) => {
          const keyNode = this.#rows[rowIndex].keyNodes[column];
          keyNode.textContent = this.#labelOf(key);
          keyNode.classList.toggle("selected", this.#cursor.isAt(rowIndex, column));
          keyNode.classList.toggle("active", key.kind === KeyKind.DIACRITICS && this.#diacritics);
        });
      });
    }
  };
}
