{
  const TV_LAYOUT_WIDTH_PX = 1920;
  const FULLSCREEN_WINDOW = "(display-mode: fullscreen)";

  const requestFit = () => {
    browser.runtime.sendMessage({
      fitViewport: {
        width: innerWidth,
        targetWidth: TV_LAYOUT_WIDTH_PX,
        fullscreen: matchMedia(FULLSCREEN_WINDOW).matches,
      },
    });
  };

  KasualPad.fitViewportToTvLayout = () => {
    requestFit();
    addEventListener("resize", requestFit);
  };
}
