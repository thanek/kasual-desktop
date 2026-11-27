{
  const FULLSCREEN_WINDOW = "(display-mode: fullscreen)";

  KasualPad.isTvMode = () => matchMedia(FULLSCREEN_WINDOW).matches;
}
