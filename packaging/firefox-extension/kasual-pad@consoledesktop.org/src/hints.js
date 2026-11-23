{
  const { Intent } = KasualPad;

  const cluster = (glyphs, label) => Object.freeze({ glyphs, label });
  const action = (button, label) => Object.freeze({ button, label });
  const screen = ({ clusters, actions, autoHide = false }) => Object.freeze({ clusters, actions, autoHide });

  KasualPad.Hints = Object.freeze({
    cluster,
    action,
    screen,
    NAVIGATE: cluster([Intent.UP, Intent.DOWN, Intent.LEFT, Intent.RIGHT], "navigate"),
    VOLUME: cluster(["LT", "RT"], "volume"),
    HOME_MENU: cluster(["home"], "showHideMenu"),
  });
}
