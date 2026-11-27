{
  KasualPad.ignoreStrayPointerHover();
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

  const stickScroll = new KasualPad.StickScroll((pixels) => controller.scrollBy(pixels));

  const handle = (intent) => {
    hintBar.wake();
    controller.handle(intent);
  };

  new KasualPad.KeySource(handle, keyboard).start();
  new KasualPad.GamepadSource(
    handle,
    (pads, now) => {
      controller.tick(now);
      stickScroll.follow(pads, now);
      hintBar.show(controller.hints(), now);
      diagnostics.show(pads);
    },
  ).start();
}
