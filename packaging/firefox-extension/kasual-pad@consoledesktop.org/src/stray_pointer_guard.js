{
  const HOVER_EVENTS = [
    "mouseover", "mouseout", "mouseenter", "mouseleave", "mousemove",
    "pointerover", "pointerout", "pointerenter", "pointerleave", "pointermove",
  ];

  KasualPad.ignoreStrayPointerHover = () => {
    let lastScreenPoint = null;

    const pointerStayedPut = (event) =>
      lastScreenPoint !== null && event.screenX === lastScreenPoint.x && event.screenY === lastScreenPoint.y;

    const swallowStrayHover = (event) => {
      if (!event.isTrusted) return;
      if (KasualPad.isTvMode() || pointerStayedPut(event)) event.stopImmediatePropagation();
      else lastScreenPoint = { x: event.screenX, y: event.screenY };
    };

    for (const type of HOVER_EVENTS) addEventListener(type, swallowStrayHover, { capture: true });
  };
}
