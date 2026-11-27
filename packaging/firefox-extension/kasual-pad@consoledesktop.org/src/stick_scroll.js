{
  const FULL_TILT_PX_PER_S = 2400;
  const LONGEST_FRAME_MS = 50;
  const MS_PER_S = 1000;

  const easedSpeed = (tilt) => Math.sign(tilt) * tilt * tilt * FULL_TILT_PX_PER_S;

  KasualPad.StickScroll = class {
    #scrollBy;
    #lastFrameAt = null;
    #pendingPx = 0;

    constructor(scrollBy) {
      this.#scrollBy = scrollBy;
    }

    follow(pads, now) {
      const tilt = KasualPad.scrollTilt(pads);
      const elapsedMs = Math.min(now - (this.#lastFrameAt ?? now), LONGEST_FRAME_MS);
      this.#lastFrameAt = now;
      this.#pendingPx = tilt === 0 ? 0 : this.#pendingPx + (easedSpeed(tilt) * elapsedMs) / MS_PER_S;
      const wholePx = Math.trunc(this.#pendingPx);
      if (wholePx === 0) return;
      this.#pendingPx -= wholePx;
      this.#scrollBy(wholePx);
    }
  };
}
