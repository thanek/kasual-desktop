{
  const { Intent } = KasualPad;

  const PLAYER_PATH_PREFIX = "/watch/";
  const HOME_PATH = "/browse";
  const SEARCH_REVEAL_TIMEOUT_MS = 1500;
  const CONTROLS_KEEP_AWAKE_EVERY_MS = 1000;
  const LONG_SEEK_STEPS = 3;

  const Selector = {
    PLAYER: '[data-uia="player"], .watch-video',
    PLAY_PAUSE: '[data-uia^="control-play-pause"]',
    PLAYER_BACK: '[data-uia="control-nav-back"]',
    SKIP_OR_NEXT_EPISODE: '[data-uia^="player-skip"], [data-uia^="next-episode-seamless-button"]',
    DETAILS_PLAY: '[data-uia*="play-button"]',
    SEARCH_LAUNCHER: '[data-uia*="search-box-launcher"], button[aria-label="Szukaj"], button[aria-label="Search"]',
    SEARCH_INPUT: '[data-uia*="search-box-input"], input#searchInput, input[type="search"]',
    HOME_LINK: `a[href="${HOME_PATH}"]`,
    PAGE_HEADER: 'header, [role="banner"], nav',
    OPENS_POPUP: "[aria-haspopup], [aria-expanded]",
    OPEN_POPUP_TRIGGER: '[aria-haspopup][aria-expanded="true"]',
    ROW_SCROLL_LEFT: '[data-uia^="carousel"][data-uia$="left-button"]',
    ROW_SCROLL_RIGHT: '[data-uia^="carousel"][data-uia$="right-button"]',
  };

  const { Hints, NetflixFloors } = KasualPad;

  const SCROLL_ROW = Hints.cluster(["LB", "RB"], "scrollRow");
  const JUMP_FLOOR = Hints.cluster(["LT", "RT"], "section");
  const SELECT = Hints.action("A", "select");
  const SKIP = Hints.action("Y", "skip");

  const BROWSING_HINTS = Hints.screen({
    clusters: [Hints.NAVIGATE, SCROLL_ROW, JUMP_FLOOR, Hints.HOME_MENU],
    actions: [SELECT, Hints.action("X", "search"), Hints.action("B", "back")],
  });

  const DETAILS_HINTS = Hints.screen({
    clusters: [Hints.NAVIGATE, Hints.HOME_MENU],
    actions: [SELECT, Hints.action("B", "close")],
  });

  const watchingHints = (actions) => Hints.screen({
    clusters: [
      Hints.cluster([Intent.LEFT, Intent.RIGHT], "seek"),
      Hints.cluster(["LB", "RB"], "seekLong"),
      Hints.cluster([Intent.UP, Intent.DOWN], "controls"),
      Hints.VOLUME,
    ],
    actions,
    autoHide: true,
  });

  const controlsHints = (actions) => Hints.screen({
    clusters: [Hints.NAVIGATE, Hints.VOLUME],
    actions,
  });

  const PLAY_PAUSE = Hints.action("A", "playPause");
  const EXIT_PLAYER = Hints.action("B", "exitPlayer");
  const HIDE_CONTROLS = Hints.action("B", "hideControls");

  const WATCHING_HINTS = watchingHints([PLAY_PAUSE, EXIT_PLAYER]);
  const WATCHING_WITH_SKIP_HINTS = watchingHints([PLAY_PAUSE, SKIP, EXIT_PLAYER]);
  const CONTROLS_HINTS = controlsHints([SELECT, HIDE_CONTROLS]);
  const CONTROLS_WITH_SKIP_HINTS = controlsHints([SELECT, SKIP, HIDE_CONTROLS]);

  const visibleSearchInput = () =>
    Array.from(document.querySelectorAll(Selector.SEARCH_INPUT)).find(KasualPad.isReachable) ?? null;

  const focusedOnPage = () => {
    const active = document.activeElement;
    return active && active !== document.body ? active : null;
  };

  const isDismissible = (element) =>
    KasualPad.isTextInput(element)
    || element?.closest(Selector.PAGE_HEADER) != null
    || element?.matches(Selector.OPENS_POPUP) === true;

  const dismiss = (element) => {
    KasualPad.pressKey("Escape");
    element.blur();
  };

  const closePopup = (trigger, focus) => {
    KasualPad.pressKey("Escape");
    document.activeElement?.blur();
    focus.pointAt(trigger);
  };

  const focusedTextInput = () => (KasualPad.isTextInput(document.activeElement) ? document.activeElement : null);

  const isOnHome = () => location.pathname === HOME_PATH;

  const goHome = () => {
    const homeLink = document.querySelector(Selector.HOME_LINK);
    if (homeLink) homeLink.click();
    else location.assign(HOME_PATH);
  };

  const canSkip = () => document.querySelector(Selector.SKIP_OR_NEXT_EPISODE) !== null;

  const clickIfPresent = (selector) => {
    document.querySelector(selector)?.click();
  };

  const pressKeyTimes = (key, times) => {
    for (let i = 0; i < times; i += 1) KasualPad.pressKey(key);
  };

  const nearestEnclosing = (element, selector) => {
    for (let ancestor = element?.parentElement; ancestor; ancestor = ancestor.parentElement) {
      const match = ancestor.querySelector(selector);
      if (match) return match;
    }
    return null;
  };

  const scrollRow = (focused, buttonSelector) => {
    nearestEnclosing(focused, buttonSelector)?.click();
  };

  const jumpFloor = (focus, step) => {
    if (KasualPad.topmostModal()) return;
    const entry = NetflixFloors.entryNextTo(focus.current, step);
    if (!entry) return;
    if (NetflixFloors.isOnNavigationBar(entry)) scrollTo({ top: 0, behavior: "instant" });
    focus.jumpTo(entry);
  };

  KasualPad.NetflixSite = class {
    #controlsOpen = false;
    #controlsWokenAt = 0;

    #watchingActions = {
      [Intent.SELECT]: () => KasualPad.pressKey(" "),
      [Intent.LEFT]: () => KasualPad.pressKey("ArrowLeft"),
      [Intent.RIGHT]: () => KasualPad.pressKey("ArrowRight"),
      [Intent.SECTION_PREV]: () => pressKeyTimes("ArrowLeft", LONG_SEEK_STEPS),
      [Intent.SECTION_NEXT]: () => pressKeyTimes("ArrowRight", LONG_SEEK_STEPS),
      [Intent.VOLUME_DOWN]: () => KasualPad.pressKey("ArrowDown"),
      [Intent.VOLUME_UP]: () => KasualPad.pressKey("ArrowUp"),
      [Intent.ACTIONS]: () => clickIfPresent(Selector.SKIP_OR_NEXT_EPISODE),
      [Intent.UP]: () => this.#openControls(),
      [Intent.DOWN]: () => this.#openControls(),
      [Intent.CANCEL]: () => this.#leavePlayer(),
    };

    #controlsActions = {
      [Intent.VOLUME_DOWN]: () => KasualPad.pressKey("ArrowDown"),
      [Intent.VOLUME_UP]: () => KasualPad.pressKey("ArrowUp"),
      [Intent.ACTIONS]: () => clickIfPresent(Selector.SKIP_OR_NEXT_EPISODE),
      [Intent.CANCEL]: () => this.#closeControls(),
    };

    #browsingActions = {
      [Intent.CANCEL]: (focus) => this.#stepBack(focus),
      [Intent.SECTION_PREV]: (focus) => scrollRow(focus.current, Selector.ROW_SCROLL_LEFT),
      [Intent.SECTION_NEXT]: (focus) => scrollRow(focus.current, Selector.ROW_SCROLL_RIGHT),
      [Intent.VOLUME_DOWN]: (focus) => jumpFloor(focus, -1),
      [Intent.VOLUME_UP]: (focus) => jumpFloor(focus, +1),
    };

    handle(intent, focus) {
      const action = this.#actionsForContext()[intent];
      if (this.#isPlayerOpen() && this.#controlsOpen) this.#wakeControls();
      action?.(focus);
      return action !== undefined || this.#isWatching();
    }

    tick(now) {
      const controlsDozing = now - this.#controlsWokenAt >= CONTROLS_KEEP_AWAKE_EVERY_MS;
      if (!this.#isPlayerOpen()) this.#controlsOpen = false;
      else if (this.#controlsOpen && controlsDozing) this.#wakeControls(now);
    }

    focusScope() {
      if (!this.#isPlayerOpen()) return KasualPad.topmostModal() ?? document;
      const controlsShown = document.querySelector(Selector.PLAY_PAUSE) !== null;
      return this.#controlsOpen && controlsShown ? document.querySelector(Selector.PLAYER) : null;
    }

    diagnostics(focused) {
      return [
        `modal: ${KasualPad.describeElement(KasualPad.topmostModal())}`,
        `floor: ${NetflixFloors.describeFloorOf(focused)}`,
      ];
    }

    navigableIn(scope) {
      return NetflixFloors.navigableIn(scope);
    }

    sameSection(a, b) {
      return this.#isPlayerOpen() || NetflixFloors.sameFloor(a, b);
    }

    landingFor(from, to) {
      return this.#isPlayerOpen() ? to : NetflixFloors.landingFor(from, to);
    }

    primaryActionIn(scope) {
      const selector = this.#isPlayerOpen() ? Selector.PLAY_PAUSE : Selector.DETAILS_PLAY;
      return Array.from(scope.querySelectorAll(selector)).find(KasualPad.isReachable) ?? null;
    }

    isSearchLauncher(element) {
      return element?.matches(Selector.SEARCH_LAUNCHER) === true;
    }

    revealSearchInput() {
      if (this.#isPlayerOpen() || KasualPad.topmostModal()) return Promise.resolve(null);
      if (!visibleSearchInput()) document.querySelector(Selector.SEARCH_LAUNCHER)?.click();
      return KasualPad.waitFor(() => visibleSearchInput() ?? focusedTextInput(), SEARCH_REVEAL_TIMEOUT_MS);
    }

    hints() {
      if (!this.#isPlayerOpen()) return KasualPad.topmostModal() ? DETAILS_HINTS : BROWSING_HINTS;
      if (this.#controlsOpen) return canSkip() ? CONTROLS_WITH_SKIP_HINTS : CONTROLS_HINTS;
      return canSkip() ? WATCHING_WITH_SKIP_HINTS : WATCHING_HINTS;
    }

    hoversOnFocus() {
      return this.#isPlayerOpen();
    }

    #isPlayerOpen() {
      return location.pathname.startsWith(PLAYER_PATH_PREFIX);
    }

    #isWatching() {
      return this.#isPlayerOpen() && !this.#controlsOpen;
    }

    #actionsForContext() {
      if (!this.#isPlayerOpen()) return this.#browsingActions;
      return this.#controlsOpen ? this.#controlsActions : this.#watchingActions;
    }

    #openControls() {
      this.#controlsOpen = true;
      this.#wakeControls();
    }

    #closeControls() {
      this.#controlsOpen = false;
    }

    #wakeControls(now = performance.now()) {
      const player = document.querySelector(Selector.PLAYER);
      if (player) KasualPad.movePointerOver(player);
      this.#controlsWokenAt = now;
    }

    #leavePlayer() {
      const backButton = document.querySelector(Selector.PLAYER_BACK);
      if (backButton) backButton.click();
      else history.back();
    }

    #stepBack(focus) {
      const openPopupTrigger = document.querySelector(Selector.OPEN_POPUP_TRIGGER);
      const focused = focusedOnPage();
      if (KasualPad.topmostModal()) KasualPad.pressKey("Escape");
      else if (openPopupTrigger) closePopup(openPopupTrigger, focus);
      else if (isDismissible(focused)) dismiss(focused);
      else if (!isOnHome()) goHome();
    }
  };
}
