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

  const OUT_EVENTS = [
    ["pointerout", PointerEvent, BUBBLES],
    ["mouseout", MouseEvent, BUBBLES],
  ];

  const LEAVE_EVENTS = [
    ["pointerleave", PointerEvent, STAYS_ON_TARGET],
    ["mouseleave", MouseEvent, STAYS_ON_TARGET],
  ];

  const centerOf = (element, nudgeX) => {
    const rect = element.getBoundingClientRect();
    return { clientX: rect.left + rect.width / 2 + nudgeX, clientY: rect.top + rect.height / 2 };
  };

  const dispatchAt = (target, events, point, nudgeX) => {
    for (const [type, EventType, bubbles] of events) {
      target.dispatchEvent(new EventType(type, { bubbles, composed: true, ...point, movementX: nudgeX }));
    }
  };

  const innermostAt = (element, { clientX, clientY }) => {
    const hit = document.elementFromPoint(clientX, clientY);
    return hit && element.contains(hit) ? hit : element;
  };

  const selfAndAncestorsUpTo = (innermost, outermost) => {
    const chain = [];
    for (let node = innermost; node && node !== outermost.parentElement; node = node.parentElement) chain.push(node);
    return chain;
  };

  KasualPad.hover = (element) => dispatchAt(element, HOVER_EVENTS, centerOf(element, 0), 0);

  KasualPad.movePointerOver = (element, nudgeX) => {
    const point = centerOf(element, nudgeX);
    dispatchAt(innermostAt(element, point), MOVE_EVENTS, point, nudgeX);
  };

  KasualPad.movePointerOut = (element) => {
    const point = centerOf(element, 0);
    const innermost = innermostAt(element, point);
    dispatchAt(innermost, OUT_EVENTS, point, 0);
    for (const node of selfAndAncestorsUpTo(innermost, element)) dispatchAt(node, LEAVE_EVENTS, point, 0);
  };
}
