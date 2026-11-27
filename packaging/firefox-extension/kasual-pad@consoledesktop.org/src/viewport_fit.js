{
  const TV_LAYOUT_WIDTH_PX = 1440;
  const UNZOOMED = 1;

  let fitOutcome = "not requested";
  let pageZoom = UNZOOMED;

  const describeReply = ({ zoom, error }) => (error ? `failed: ${error}` : `zoom ${zoom.toFixed(3)}`);

  const requestFit = async () => {
    const fullscreen = KasualPad.isTvMode();
    const reply = await browser.runtime.sendMessage({
      fitViewport: { width: innerWidth, targetWidth: TV_LAYOUT_WIDTH_PX, fullscreen },
    }).catch((error) => ({ error: `no reply: ${error.message}` }));
    pageZoom = reply.zoom ?? UNZOOMED;
    fitOutcome = `${fullscreen ? "fullscreen" : "windowed"}, ${describeReply(reply)}`;
  };

  KasualPad.fitViewportToTvLayout = () => {
    requestFit();
    addEventListener("resize", requestFit);
  };

  KasualPad.viewportFitOutcome = () => fitOutcome;
  KasualPad.pageZoom = () => pageZoom;
}
