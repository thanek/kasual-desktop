{
  const KEYS = {
    " ": { code: "Space", keyCode: 32 },
    Escape: { code: "Escape", keyCode: 27 },
    ArrowLeft: { code: "ArrowLeft", keyCode: 37 },
    ArrowUp: { code: "ArrowUp", keyCode: 38 },
    ArrowRight: { code: "ArrowRight", keyCode: 39 },
    ArrowDown: { code: "ArrowDown", keyCode: 40 },
  };

  KasualPad.pressKey = (key) => {
    const { code, keyCode } = KEYS[key];
    const target = document.activeElement ?? document.body;
    for (const type of ["keydown", "keyup"]) {
      target.dispatchEvent(new KeyboardEvent(type, {
        key, code, keyCode, bubbles: true, cancelable: true, composed: true,
      }));
    }
  };
}
