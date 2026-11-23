{
  const Intent = Object.freeze({
    UP: "up",
    DOWN: "down",
    LEFT: "left",
    RIGHT: "right",
    SELECT: "select",
    CANCEL: "cancel",
    CLOSE: "close",
    ACTIONS: "actions",
    SECTION_PREV: "section_prev",
    SECTION_NEXT: "section_next",
    VOLUME_DOWN: "volume_down",
    VOLUME_UP: "volume_up",
  });

  const DIRECTIONS = new Set([Intent.UP, Intent.DOWN, Intent.LEFT, Intent.RIGHT]);
  const REPEATABLE = new Set([
    ...DIRECTIONS,
    Intent.SECTION_PREV,
    Intent.SECTION_NEXT,
    Intent.VOLUME_DOWN,
    Intent.VOLUME_UP,
  ]);

  KasualPad.Intent = Intent;
  KasualPad.isDirection = (intent) => DIRECTIONS.has(intent);
  KasualPad.isHorizontal = (intent) => intent === Intent.LEFT || intent === Intent.RIGHT;
  KasualPad.isRepeatable = (intent) => REPEATABLE.has(intent);
}
