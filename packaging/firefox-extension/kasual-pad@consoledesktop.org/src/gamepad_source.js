{
  const FIRST_REPEAT_DELAY_MS = 400;
  const REPEAT_INTERVAL_MS = 120;
  const NEVER = Infinity;

  const connectedPads = () => Array.from(navigator.getGamepads()).filter((pad) => pad?.connected);

  const activeIntentsOfAll = (pads) => new Set(pads.flatMap((pad) => Array.from(KasualPad.activeIntents(pad))));

  KasualPad.GamepadSource = class {
    #onIntent;
    #onFrame;
    #nextDispatchAt = new Map();

    constructor(onIntent, onFrame) {
      this.#onIntent = onIntent;
      this.#onFrame = onFrame;
    }

    start() {
      requestAnimationFrame(this.#tick);
    }

    #tick = (now) => {
      const pads = connectedPads();
      this.#dispatchChanges(activeIntentsOfAll(pads), now);
      this.#onFrame(pads, now);
      requestAnimationFrame(this.#tick);
    };

    #dispatchChanges(active, now) {
      for (const intent of this.#nextDispatchAt.keys()) {
        if (!active.has(intent)) this.#nextDispatchAt.delete(intent);
      }
      for (const intent of active) this.#dispatchIfDue(intent, now);
    }

    #dispatchIfDue(intent, now) {
      const dueAt = this.#nextDispatchAt.get(intent);
      if (dueAt === undefined) {
        this.#onIntent(intent);
        this.#nextDispatchAt.set(intent, KasualPad.isRepeatable(intent) ? now + FIRST_REPEAT_DELAY_MS : NEVER);
      } else if (now >= dueAt) {
        this.#onIntent(intent);
        this.#nextDispatchAt.set(intent, now + REPEAT_INTERVAL_MS);
      }
    }
  };
}
