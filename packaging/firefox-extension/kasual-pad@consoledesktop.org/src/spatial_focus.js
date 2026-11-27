{
  const { Intent } = KasualPad;

  const CROSS_AXIS_PENALTY = 3;
  const MIN_STEP_PX = 1;
  const COMFORT_MARGIN_RATIO = 0.2;
  const SCROLL = true;
  const STAY_PUT = false;

  const centerOf = (rect) => ({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
  const centerOfElement = (element) => centerOf(element.getBoundingClientRect());

  const OFFSETS_TOWARDS = {
    [Intent.UP]: (from, to) => ({ along: from.y - to.y, across: Math.abs(from.x - to.x) }),
    [Intent.DOWN]: (from, to) => ({ along: to.y - from.y, across: Math.abs(from.x - to.x) }),
    [Intent.LEFT]: (from, to) => ({ along: from.x - to.x, across: Math.abs(from.y - to.y) }),
    [Intent.RIGHT]: (from, to) => ({ along: to.x - from.x, across: Math.abs(from.y - to.y) }),
  };

  const lowestScoring = (candidates, scoreOf) => {
    let best = null;
    let bestScore = Infinity;
    for (const candidate of candidates) {
      const score = scoreOf(candidate);
      if (score < bestScore) {
        best = candidate;
        bestScore = score;
      }
    }
    return best;
  };

  const nearestTowards = (origin, candidates, direction) =>
    lowestScoring(candidates, (candidate) => {
      const { along, across } = OFFSETS_TOWARDS[direction](origin, centerOfElement(candidate));
      return along >= MIN_STEP_PX ? along + across * CROSS_AXIS_PENALTY : Infinity;
    });

  const nearestTo = (point, candidates) =>
    lowestScoring(candidates, (candidate) => {
      const center = centerOfElement(candidate);
      return Math.hypot(center.x - point.x, center.y - point.y);
    });

  const firstInViewport = (candidates) =>
    candidates
      .map((element) => ({ element, rect: element.getBoundingClientRect() }))
      .filter(({ rect }) => rect.top >= 0 && rect.top < innerHeight)
      .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left)
      .at(0)?.element ?? null;

  const canScrollVertically = (element) => {
    const { overflowY } = getComputedStyle(element);
    return (overflowY === "auto" || overflowY === "scroll") && element.scrollHeight > element.clientHeight;
  };

  const verticalScrollerOf = (element) => {
    for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
      if (canScrollVertically(ancestor)) return ancestor;
    }
    return document.scrollingElement;
  };

  const isOffScreen = (element) => {
    const rect = element.getBoundingClientRect();
    return rect.bottom <= 0 || rect.top >= innerHeight;
  };

  const startOfMiddleRow = () => ({ x: 0, y: innerHeight / 2 });

  const keepComfortablyVisible = (element) => {
    const rect = element.getBoundingClientRect();
    const margin = innerHeight * COMFORT_MARGIN_RATIO;
    const tooCloseToEdge = rect.top < margin || rect.bottom > innerHeight - margin;
    if (tooCloseToEdge) {
      verticalScrollerOf(element).scrollBy({ top: centerOf(rect).y - innerHeight / 2, behavior: "instant" });
    }
  };

  KasualPad.SpatialFocus = class {
    #site;
    #highlight;
    #feedback;
    #scope = document;
    #current = null;
    #lastKnownCenter = null;
    #pageFocusBeforeLeaving = { element: null, center: null };
    #dismissedScope = null;

    constructor(site, highlight, feedback) {
      this.#site = site;
      this.#highlight = highlight;
      this.#feedback = feedback;
    }

    get current() {
      return this.#current?.isConnected ? this.#current : null;
    }

    get isInOverlay() {
      return this.#scope !== null && this.#scope !== document;
    }

    followScope() {
      const scope = this.#scopeStillOnScreen();
      if (scope !== this.#scope) this.#switchTo(scope);
      else if (scope) this.#keepAnchored();
    }

    diagnostics() {
      const candidateCount = this.#scope ? this.#candidates().length : 0;
      return [
        `ring: ${KasualPad.describeElement(this.#current)}`,
        `scope: ${KasualPad.describeElement(this.#scope)} (${candidateCount} candidates)`,
      ];
    }

    leaveOverlay() {
      if (!this.isInOverlay) return;
      this.#dismissedScope = this.#scope;
      this.#leaveTo(null);
    }

    move(direction) {
      if (!this.#scope) return;
      const origin = this.current;
      const keepsToSection = origin && KasualPad.isHorizontal(direction);
      const candidates = this.#candidates().filter((element) =>
        element !== this.#current && (!keepsToSection || this.#site.sameSection(origin, element)));
      const target = this.#lastKnownCenter
        ? nearestTowards(this.#lastKnownCenter, candidates, direction)
        : firstInViewport(candidates);
      if (target) this.jumpTo(this.current ? this.#site.landingFor(this.current, target) : target);
    }

    scrollBy(pixels) {
      if (!this.#scope) return;
      verticalScrollerOf(this.current ?? document.body).scrollBy({ top: pixels, behavior: "instant" });
      if (!this.current || isOffScreen(this.current)) this.#reanchorNear(startOfMiddleRow());
    }

    jumpTo(element) {
      this.#focus(element, SCROLL);
      this.#feedback.play(KasualPad.Cue.CURSOR);
    }

    focusOn(element) {
      this.#focus(element, SCROLL);
    }

    pointAt(element) {
      this.#current = element;
      this.#lastKnownCenter = centerOfElement(element);
      this.#highlight.follow(element);
    }

    activate() {
      const { current } = this;
      if (!current) return;
      this.#feedback.play(KasualPad.Cue.SELECT);
      current.click();
    }

    #scopeStillOnScreen() {
      const scope = this.#site.focusScope();
      if (scope === this.#dismissedScope) return null;
      this.#dismissedScope = null;
      return scope;
    }

    #candidates() {
      return this.#site.navigableIn(this.#scope);
    }

    #switchTo(scope) {
      if (scope === document) this.#returnToPage();
      else if (scope) this.#enter(scope);
      else this.#leaveTo(null);
    }

    #enter(scope) {
      const entry = this.#site.primaryActionIn(scope) ?? firstInViewport(this.#site.navigableIn(scope));
      if (!entry) return;
      this.#leaveTo(scope);
      this.#focus(entry, SCROLL);
      this.#feedback.play(KasualPad.Cue.POPUP_OPEN);
    }

    #leaveTo(scope) {
      if (this.#scope === document) {
        this.#pageFocusBeforeLeaving = { element: this.#current, center: this.#lastKnownCenter };
      }
      this.#scope = scope;
      if (!scope) this.#forget();
    }

    #returnToPage() {
      const { element, center } = this.#pageFocusBeforeLeaving;
      this.#scope = document;
      if (element?.isConnected) this.#focus(element, SCROLL);
      else if (center) this.#reanchorNear(center);
      else this.#forget();
    }

    #keepAnchored() {
      if (!this.#current) return;
      if (this.#current.isConnected && KasualPad.isReachable(this.#current)) {
        this.#lastKnownCenter = centerOfElement(this.#current);
      } else if (this.#pageMovedFocusToCandidate()) {
        this.#focus(document.activeElement, STAY_PUT);
      } else {
        this.#reanchorNear(this.#lastKnownCenter);
      }
    }

    #pageMovedFocusToCandidate() {
      const active = document.activeElement;
      return active !== this.#current
        && this.#scope.contains(active)
        && this.#candidates().includes(active);
    }

    #reanchorNear(point) {
      const nearest = nearestTo(point, this.#candidates());
      if (nearest) this.#focus(nearest, STAY_PUT);
    }

    #focus(element, scroll) {
      element.focus({ preventScroll: true });
      if (scroll) keepComfortablyVisible(element);
      if (this.#site.hoversOnFocus()) KasualPad.hover(element);
      this.pointAt(element);
    }

    #forget() {
      this.#current?.blur();
      this.#current = null;
      this.#lastKnownCenter = null;
      this.#highlight.follow(null);
    }
  };
}
