{
  const { Intent } = KasualPad;

  const PRESS_THRESHOLD = 0.5;
  const STICK_DEAD_ZONE = 0.2;
  const TRIGGER_AXIS_PRESSED_ABOVE = 0;
  const TRIGGER_AXIS_AT_REST = -1;

  const STANDARD_LAYOUT_AS_FIREFOX_REPORTS_IT_ON_LINUX = {
    buttons: [
      [0, Intent.SELECT],
      [1, Intent.CANCEL],
      [2, Intent.ACTIONS],
      [3, Intent.CLOSE],
      [4, Intent.SECTION_PREV],
      [5, Intent.SECTION_NEXT],
      [6, Intent.VOLUME_DOWN],
      [7, Intent.VOLUME_UP],
      [12, Intent.UP],
      [13, Intent.DOWN],
      [14, Intent.LEFT],
      [15, Intent.RIGHT],
    ],
    triggerAxes: [],
    directionAxes: [{ x: 0, y: 1 }],
    scrollAxis: 3,
  };

  const UNMAPPED_EVDEV_LAYOUT = {
    buttons: [
      [0, Intent.SELECT],
      [1, Intent.CANCEL],
      [2, Intent.ACTIONS],
      [3, Intent.CLOSE],
      [4, Intent.SECTION_PREV],
      [5, Intent.SECTION_NEXT],
    ],
    triggerAxes: [
      [2, Intent.VOLUME_DOWN],
      [5, Intent.VOLUME_UP],
    ],
    directionAxes: [{ x: 0, y: 1 }, { x: 6, y: 7 }],
    scrollAxis: 4,
  };

  const isPressed = (pad, index) => {
    const button = pad.buttons[index];
    return button?.pressed === true || (button?.value ?? 0) >= PRESS_THRESHOLD;
  };

  const isTriggerPulled = (pad, index) => (pad.axes[index] ?? TRIGGER_AXIS_AT_REST) > TRIGGER_AXIS_PRESSED_ABOVE;

  const addAxisDirections = (active, pad, axes) => {
    const x = pad.axes[axes.x] ?? 0;
    const y = pad.axes[axes.y] ?? 0;
    if (x <= -PRESS_THRESHOLD) active.add(Intent.LEFT);
    if (x >= PRESS_THRESHOLD) active.add(Intent.RIGHT);
    if (y <= -PRESS_THRESHOLD) active.add(Intent.UP);
    if (y >= PRESS_THRESHOLD) active.add(Intent.DOWN);
  };

  const layoutOf = (pad) =>
    (pad.mapping === "standard" ? STANDARD_LAYOUT_AS_FIREFOX_REPORTS_IT_ON_LINUX : UNMAPPED_EVDEV_LAYOUT);

  const scrollTiltOf = (pad) => {
    const tilt = pad.axes[layoutOf(pad).scrollAxis] ?? 0;
    return Math.abs(tilt) > STICK_DEAD_ZONE ? tilt : 0;
  };

  KasualPad.scrollTilt = (pads) =>
    pads.map(scrollTiltOf).reduce((strongest, tilt) => (Math.abs(tilt) > Math.abs(strongest) ? tilt : strongest), 0);

  KasualPad.activeIntents = (pad) => {
    const layout = layoutOf(pad);
    const active = new Set();
    for (const [index, intent] of layout.buttons) {
      if (isPressed(pad, index)) active.add(intent);
    }
    for (const [index, intent] of layout.triggerAxes) {
      if (isTriggerPulled(pad, index)) active.add(intent);
    }
    for (const axes of layout.directionAxes) addAxisDirections(active, pad, axes);
    return active;
  };
}
