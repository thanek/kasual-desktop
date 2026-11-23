{
  const BUBBLES = true;
  const STAYS_ON_TARGET = false;

  const HOVER_EVENTS = [
    ["pointerover", PointerEvent, BUBBLES],
    ["pointerenter", PointerEvent, STAYS_ON_TARGET],
    ["mouseover", MouseEvent, BUBBLES],
    ["mouseenter", MouseEvent, STAYS_ON_TARGET],
  ];

  const MOVE_EVENTS = [
    ["pointermove", PointerEvent, BUBBLES],
    ["mousemove", MouseEvent, BUBBLES],
  ];

  const dispatchAt = (target, events) => {
    const rect = target.getBoundingClientRect();
    const clientX = rect.left + rect.width / 2;
    const clientY = rect.top + rect.height / 2;
    for (const [type, EventType, bubbles] of events) {
      target.dispatchEvent(new EventType(type, { bubbles, composed: true, clientX, clientY }));
    }
  };

  KasualPad.hover = (element) => dispatchAt(element, HOVER_EVENTS);
  KasualPad.movePointerOver = (element) => dispatchAt(element, MOVE_EVENTS);
}
