{
  const { Intent } = KasualPad;

  const NAVIGATION_KEYS = {
    ArrowUp: Intent.UP,
    ArrowDown: Intent.DOWN,
    ArrowLeft: Intent.LEFT,
    ArrowRight: Intent.RIGHT,
    Enter: Intent.SELECT,
    Escape: Intent.CANCEL,
  };

  const SHORTCUT_KEYS = {
    KeyQ: Intent.CLOSE,
    BracketLeft: Intent.SECTION_PREV,
    BracketRight: Intent.SECTION_NEXT,
    Minus: Intent.VOLUME_DOWN,
    Equal: Intent.VOLUME_UP,
  };

  const hasModifier = (event) => event.ctrlKey || event.altKey || event.metaKey;

  const isTyping = () => KasualPad.isTextInput(document.activeElement);

  const intentOf = (event) => {
    if (!event.isTrusted || hasModifier(event)) return undefined;
    return NAVIGATION_KEYS[event.key] ?? (isTyping() ? undefined : SHORTCUT_KEYS[event.code]);
  };

  const isDue = (event, intent) => !event.repeat || KasualPad.isRepeatable(intent);

  const consume = (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
  };

  KasualPad.KeySource = class {
    #onIntent;
    #onScreenKeyboard;

    constructor(onIntent, onScreenKeyboard) {
      this.#onIntent = onIntent;
      this.#onScreenKeyboard = onScreenKeyboard;
    }

    start() {
      addEventListener("keydown", this.#onKeyDown, true);
      addEventListener("keyup", this.#onKeyUp, true);
    }

    #onKeyDown = (event) => {
      if (this.#typedOnScreenKeyboard(event)) {
        consume(event);
        return;
      }
      const intent = intentOf(event);
      if (intent === undefined) return;
      consume(event);
      if (isDue(event, intent)) this.#onIntent(intent);
    };

    #onKeyUp = (event) => {
      if (intentOf(event) !== undefined) consume(event);
    };

    #typedOnScreenKeyboard(event) {
      return event.isTrusted
        && !hasModifier(event)
        && this.#onScreenKeyboard.isOpen
        && this.#onScreenKeyboard.typeFromKeyboard(event.key);
    }
  };
}
