{
  const ABOVE_EVERYTHING = "2147483647";
  const RING_OFFSET_PX = 4;
  const MOVE_TO_NEW_TARGET_MS = 0;
  const MOVE_TO_NEW_TARGET = ["top", "left", "width", "height"]
    .map((property) => `${property} ${MOVE_TO_NEW_TARGET_MS}ms ease-out`)
    .join(", ");
  const STICK_TO_TARGET = "none";

  const createRing = () => {
    const ring = document.createElement("div");
    Object.assign(ring.style, {
      position: "fixed",
      pointerEvents: "none",
      zIndex: ABOVE_EVERYTHING,
      border: "4px solid #fff",
      borderRadius: "8px",
      boxShadow: "0 0 0 3px rgba(0, 0, 0, 0.7), 0 0 24px rgba(255, 255, 255, 0.6)",
      display: "none",
    });
    return ring;
  };

  KasualPad.FocusHighlight = class {
    #ring = createRing();
    #target = null;
    #targetChangedAt = -Infinity;

    constructor() {
      requestAnimationFrame(this.#track);
    }

    follow(element) {
      if (element === this.#target) return;
      this.#target = element;
      this.#targetChangedAt = performance.now();
    }

    #track = (now) => {
      this.#place(now);
      requestAnimationFrame(this.#track);
    };

    #place(now) {
      if (!this.#target?.isConnected) {
        this.#ring.style.display = "none";
        return;
      }
      const wasHidden = this.#ring.style.display === "none";
      const movingToNewTarget = !wasHidden && now - this.#targetChangedAt < MOVE_TO_NEW_TARGET_MS;
      KasualPad.keepInOverlayRoot(this.#ring);
      const rect = this.#target.getBoundingClientRect();
      Object.assign(this.#ring.style, {
        transition: movingToNewTarget ? MOVE_TO_NEW_TARGET : STICK_TO_TARGET,
        display: "block",
        top: `${rect.top - RING_OFFSET_PX}px`,
        left: `${rect.left - RING_OFFSET_PX}px`,
        width: `${rect.width + 2 * RING_OFFSET_PX}px`,
        height: `${rect.height + 2 * RING_OFFSET_PX}px`,
      });
    }
  };
}
