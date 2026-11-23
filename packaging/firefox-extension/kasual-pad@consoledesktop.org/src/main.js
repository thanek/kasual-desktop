{
  KasualPad.ignoreHoverFromStillPointer();
  KasualPad.fitViewportToTvLayout();

  const site = new KasualPad.NetflixSite();
  const feedback = new KasualPad.SoundFeedback();
  const focus = new KasualPad.SpatialFocus(site, new KasualPad.FocusHighlight(), feedback);
  const keyboard = new KasualPad.OnScreenKeyboard(feedback);
  const controller = new KasualPad.PadController(site, focus, keyboard, feedback);
  const hintBar = new KasualPad.HintBar();
  const diagnostics = new KasualPad.PadDiagnostics(() => [
    ...focus.diagnostics(),
    ...site.diagnostics(focus.current),
  ]);

  new KasualPad.GamepadSource(
    (intent) => {
      hintBar.wake();
      controller.handle(intent);
    },
    (pads, now) => {
      controller.tick(now);
      hintBar.show(controller.hints(), now);
      diagnostics.show(pads);
    },
  ).start();
}
