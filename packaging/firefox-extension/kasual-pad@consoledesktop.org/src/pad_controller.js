{
  const { Intent, Cue } = KasualPad;

  KasualPad.PadController = class {
    #site;
    #focus;
    #keyboard;
    #feedback;

    constructor(site, focus, keyboard, feedback) {
      this.#site = site;
      this.#focus = focus;
      this.#keyboard = keyboard;
      this.#feedback = feedback;
    }

    handle(intent) {
      if (this.#keyboard.isOpen) this.#keyboard.handle(intent);
      else if (intent === Intent.CLOSE) this.#openSearch();
      else this.#handleOnPage(intent);
    }

    hints() {
      return this.#keyboard.isOpen ? this.#keyboard.hints() : this.#site.hints();
    }

    scrollBy(pixels) {
      if (!this.#keyboard.isOpen && this.#site.scrollsFreely()) this.#focus.scrollBy(pixels);
    }

    tick(now) {
      this.#site.tick(now);
      this.#focus.followScope();
    }

    #handleOnPage(intent) {
      const closesOverlay = intent === Intent.CANCEL && this.#focus.isInOverlay;
      const handledBySite = this.#site.handle(intent, this.#focus);
      if (closesOverlay) this.#leaveOverlay();
      if (handledBySite) return;
      if (intent === Intent.SELECT) this.#select();
      else if (KasualPad.isDirection(intent)) this.#focus.move(intent);
    }

    #leaveOverlay() {
      this.#feedback.play(Cue.POPUP_CLOSE);
      this.#focus.leaveOverlay();
    }

    #select() {
      const { current } = this.#focus;
      if (KasualPad.isTextInput(current)) this.#keyboard.open(current);
      else if (this.#site.isSearchLauncher(current)) this.#openSearch();
      else this.#focus.activate();
    }

    async #openSearch() {
      const input = await this.#site.revealSearchInput();
      if (!input || this.#keyboard.isOpen) return;
      this.#focus.focusOn(input);
      this.#keyboard.open(input);
    }
  };
}
