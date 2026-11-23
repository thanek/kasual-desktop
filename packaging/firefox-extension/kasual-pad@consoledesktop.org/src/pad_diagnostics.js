{
  const TOGGLE_KEY = "F9";
  const ABOVE_EVERYTHING = "2147483647";

  const createPanel = () => {
    const panel = document.createElement("pre");
    Object.assign(panel.style, {
      position: "fixed",
      top: "16px",
      right: "16px",
      margin: "0",
      padding: "12px 16px",
      zIndex: ABOVE_EVERYTHING,
      pointerEvents: "none",
      background: "rgba(0, 0, 0, 0.8)",
      color: "#0f0",
      font: "16px/1.4 monospace",
      borderRadius: "8px",
    });
    return panel;
  };

  const pressedButtonIndices = (pad) =>
    pad.buttons.flatMap((button, index) => (button.pressed ? [index] : []));

  const LABEL_PREVIEW_LENGTH = 40;

  const describeElement = (element) => {
    if (element === document) return "document";
    if (!element || element === document.body) return "-";
    const uia = element.closest("[data-uia]")?.getAttribute("data-uia") ?? "";
    const label = (element.getAttribute("aria-label") ?? element.textContent).trim().slice(0, LABEL_PREVIEW_LENGTH);
    return `${element.tagName.toLowerCase()} [${uia}] "${label}"`;
  };

  KasualPad.describeElement = describeElement;

  const describePad = (pad) => [
    pad.id,
    `  mapping: ${pad.mapping || "(none)"}`,
    `  pressed: ${pressedButtonIndices(pad).join(" ") || "-"}`,
    `  axes: ${Array.from(pad.axes, (value) => value.toFixed(2)).join(" ")}`,
    `  intents: ${Array.from(KasualPad.activeIntents(pad)).join(" ") || "-"}`,
  ];

  const describe = (pads, state) => {
    const padLines = pads.length ? pads.flatMap(describePad) : ["no gamepad visible yet: press any button"];
    return [`focus: ${describeElement(document.activeElement)}`, ...state, ...padLines].join("\n");
  };

  KasualPad.PadDiagnostics = class {
    #panel = createPanel();
    #visible = false;
    #describeState;

    constructor(describeState) {
      this.#describeState = describeState;
      addEventListener("keydown", (event) => {
        if (event.key === TOGGLE_KEY) this.#toggle();
      }, true);
    }

    show(pads) {
      if (!this.#visible) return;
      KasualPad.keepInOverlayRoot(this.#panel);
      this.#panel.textContent = describe(pads, this.#describeState());
    }

    #toggle() {
      this.#visible = !this.#visible;
      if (!this.#visible) this.#panel.remove();
    }
  };
}
