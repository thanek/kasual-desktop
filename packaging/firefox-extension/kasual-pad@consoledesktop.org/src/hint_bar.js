{
  const AUTO_HIDE_AFTER_MS = 4000;
  const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  const HOME_ICON_PATH = "M8 1 0 8h2v7h4.5v-4.5h3V15H14V8h2z";

  const STYLE = `
    :host {
      all: initial;
      position: fixed;
      left: 0;
      right: 0;
      bottom: 32px;
      display: flex;
      justify-content: center;
      pointer-events: none;
      z-index: 2147483647;
      font: 14px system-ui, sans-serif;
    }
    .bar {
      box-sizing: border-box;
      min-width: 832px;
      height: 60px;
      padding: 0 20px;
      border-radius: 30px;
      background: rgba(46, 52, 64, 0.8);
      display: flex;
      align-items: center;
      gap: 20px;
      transition: opacity 300ms, transform 300ms;
    }
    .bar.dozing { opacity: 0; transform: translateY(16px); }
    .actions { margin-left: auto; display: flex; gap: 22px; }
    .hint, .glyphs { display: flex; align-items: center; }
    .hint { gap: 8px; }
    .glyphs { gap: 4px; }
    .label { color: #d8dee9; white-space: nowrap; }
    .glyph {
      box-sizing: border-box;
      min-width: 26px;
      height: 26px;
      border-radius: 13px;
      display: grid;
      place-items: center;
      color: white;
      font-weight: bold;
    }
    .letter { font-size: 14px; }
    .shoulder { min-width: 38px; font-size: 12px; background: #3b4252; }
    .arrow { font-size: 18px; }
    .icon { background: #3b4252; }
  `;

  const LETTER_COLORS = {
    A: ["#3a9b35", "white"],
    B: ["#cc3a3a", "white"],
    X: ["#2f6fc0", "white"],
    Y: ["#e0b00f", "black"],
  };
  const SHOULDERS = new Set(["LB", "RB", "LT", "RT"]);
  const ARROWS = { up: "↑", down: "↓", left: "←", right: "→" };

  const element = (tag, className, text = "") => {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
  };

  const homeIcon = () => {
    const svg = document.createElementNS(SVG_NAMESPACE, "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("width", "15");
    svg.setAttribute("height", "15");
    const path = document.createElementNS(SVG_NAMESPACE, "path");
    path.setAttribute("d", HOME_ICON_PATH);
    path.setAttribute("fill", "white");
    svg.append(path);
    return svg;
  };

  const ICONS = { home: homeIcon };

  const glyph = (name) => {
    if (name in LETTER_COLORS) {
      const disc = element("span", "glyph letter", name);
      [disc.style.background, disc.style.color] = LETTER_COLORS[name];
      return disc;
    }
    if (SHOULDERS.has(name)) return element("span", "glyph shoulder", name);
    if (name in ARROWS) return element("span", "glyph arrow", ARROWS[name]);
    const disc = element("span", "glyph icon");
    disc.append(ICONS[name]());
    return disc;
  };

  const translated = (key) => browser.i18n.getMessage(key) || key;

  const hint = (glyphNames, label) => {
    const glyphs = element("span", "glyphs");
    glyphs.append(...glyphNames.map(glyph));
    const row = element("span", "hint");
    row.append(glyphs, element("span", "label", translated(label)));
    return row;
  };

  KasualPad.HintBar = class {
    #host = element("div", "");
    #bar = element("div", "bar");
    #shown = null;
    #lastActivityAt = 0;

    constructor() {
      const shadow = this.#host.attachShadow({ mode: "closed" });
      const style = element("style", "", STYLE);
      shadow.append(style, this.#bar);
    }

    wake(now = performance.now()) {
      this.#lastActivityAt = now;
    }

    show(hints, now) {
      if (hints !== this.#shown) this.#render(hints, now);
      const dozing = hints.autoHide && now - this.#lastActivityAt > AUTO_HIDE_AFTER_MS;
      this.#bar.classList.toggle("dozing", dozing);
      KasualPad.keepInOverlayRoot(this.#host);
    }

    #render(hints, now) {
      const actions = element("span", "actions");
      actions.append(...hints.actions.map(({ button, label }) => hint([button], label)));
      this.#bar.replaceChildren(...hints.clusters.map(({ glyphs, label }) => hint(glyphs, label)), actions);
      this.#shown = hints;
      this.wake(now);
    }
  };
}
