KasualPad.keepInOverlayRoot = (node) => {
  const root = document.fullscreenElement ?? document.documentElement;
  if (node.parentNode !== root) root.append(node);
};
