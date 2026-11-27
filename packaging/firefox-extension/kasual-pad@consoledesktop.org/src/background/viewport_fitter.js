{
  const ZOOM_TOLERANCE = 0.01;
  const UNZOOMED = 1;
  const fittedTabs = new Set();

  const zoomTo = async (tabId, wanted) => {
    const current = await browser.tabs.getZoom(tabId);
    if (Math.abs(wanted - current) > ZOOM_TOLERANCE) await browser.tabs.setZoom(tabId, wanted);
  };

  const fitToTargetWidth = async (tabId, { width, targetWidth }) => {
    const current = await browser.tabs.getZoom(tabId);
    fittedTabs.add(tabId);
    await zoomTo(tabId, (width * current) / targetWidth);
  };

  const undoFit = async (tabId) => {
    if (!fittedTabs.delete(tabId)) return;
    await zoomTo(tabId, UNZOOMED);
  };

  const reportZoom = async (tabId) => ({ zoom: await browser.tabs.getZoom(tabId) });

  const fit = (tabId, request) => (request.fullscreen ? fitToTargetWidth(tabId, request) : undoFit(tabId))
    .then(() => reportZoom(tabId))
    .catch((error) => ({ error: error.message }));

  browser.runtime.onMessage.addListener(({ fitViewport }, sender) => {
    if (!fitViewport || !sender.tab) return undefined;
    return fit(sender.tab.id, fitViewport);
  });

  browser.tabs.onRemoved.addListener((tabId) => fittedTabs.delete(tabId));
}
