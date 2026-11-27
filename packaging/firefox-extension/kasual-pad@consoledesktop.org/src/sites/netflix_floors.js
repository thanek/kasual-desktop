{
  const NAVIGATION_BAR = "navigation-bar";

  const Selector = {
    FLOOR: '[data-uia="browse-page-sections"] > *',
    BILLBOARD: '[data-uia="billboard"]',
    BILLBOARD_PLAY: '[data-uia="play-video-button"]',
    TILE: '[data-uia="standard-card"]',
    LOGO_LINK: '[data-uia="navigation+logo"], #clcs-header a[href="/"]',
  };

  const navigableIn = (scope) =>
    KasualPad.interactiveElementsIn(scope).filter((element) => !element.closest(Selector.LOGO_LINK));

  const floorOf = (element) => element.closest(Selector.FLOOR) ?? NAVIGATION_BAR;
  const allFloors = () => [NAVIGATION_BAR, ...document.querySelectorAll(Selector.FLOOR)];
  const isBillboard = (floor) => floor !== NAVIGATION_BAR && floor.querySelector(Selector.BILLBOARD) !== null;
  const isCarousel = (floor) => floor !== NAVIGATION_BAR && floor.querySelector(Selector.TILE) !== null;

  const leftmost = (elements) =>
    elements.sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left).at(0) ?? null;

  const navigationBarElements = () =>
    navigableIn(document).filter((element) => floorOf(element) === NAVIGATION_BAR);

  const entryOf = (floor) => {
    if (floor === NAVIGATION_BAR) return leftmost(navigationBarElements());
    const reachable = navigableIn(floor);
    const firstReachable = reachable.at(0) ?? null;
    const reachableMatching = (selector) => reachable.filter((element) => element.matches(selector));
    if (isBillboard(floor)) return reachableMatching(Selector.BILLBOARD_PLAY).at(0) ?? firstReachable;
    return leftmost(reachableMatching(Selector.TILE)) ?? firstReachable;
  };

  const nextFloorWithEntry = (floors, startIndex, step) => {
    for (let index = startIndex + step; index >= 0 && index < floors.length; index += step) {
      const entry = entryOf(floors[index]);
      if (entry) return { floor: floors[index], entry };
    }
    return null;
  };

  const entersThroughEntry = (fromFloor, toFloor) =>
    isBillboard(toFloor) || (isCarousel(toFloor) && !isCarousel(fromFloor));

  KasualPad.NetflixFloors = Object.freeze({
    navigableIn,

    landingFor(from, to) {
      const floors = allFloors();
      const fromIndex = floors.indexOf(floorOf(from));
      const toFloor = floorOf(to);
      const toIndex = floors.indexOf(toFloor);
      if (fromIndex === toIndex) return to;
      const adjacent = nextFloorWithEntry(floors, fromIndex, Math.sign(toIndex - fromIndex));
      if (adjacent && adjacent.floor !== toFloor) return adjacent.entry;
      return entersThroughEntry(floors[fromIndex], toFloor) ? entryOf(toFloor) ?? to : to;
    },

    sameFloor(a, b) {
      return floorOf(a) === floorOf(b);
    },

    entryNextTo(element, step) {
      const floors = allFloors();
      const startIndex = element ? floors.indexOf(floorOf(element)) : 0;
      return nextFloorWithEntry(floors, startIndex, step)?.entry ?? null;
    },

    describeFloorOf(element) {
      if (!element) return "-";
      const floors = allFloors();
      const floor = floorOf(element);
      const kind = (floor === NAVIGATION_BAR && "navigation bar")
        || (isBillboard(floor) && "billboard")
        || (isCarousel(floor) && "carousel")
        || "other";
      return `${floors.indexOf(floor)}/${floors.length - 1} ${kind}`;
    },

    isOnNavigationBar(element) {
      return floorOf(element) === NAVIGATION_BAR;
    },
  });
}
