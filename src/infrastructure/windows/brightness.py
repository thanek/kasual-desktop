"""Windows display-brightness control (the BrightnessControl port).

Backed by ``screen_brightness_control`` (WMI for laptop panels, DDC/CI for
external monitors). Many desktop monitors don't answer DDC/CI, so every call is
guarded: an unsupported display degrades to a no-op (set) / the default level
(get) rather than crashing the brightness overlay.
"""

import logging

from domain.system.brightness import Brightness, BrightnessControl

logger = logging.getLogger(__name__)


class WindowsBrightnessControl(BrightnessControl):
    def get(self) -> Brightness:
        try:
            import screen_brightness_control as sbc
            values = sbc.get_brightness()
            if values:
                return Brightness(int(values[0]))
        except Exception as exc:
            logger.warning("Brightness unavailable (get): %s", exc)
        return Brightness(Brightness.DEFAULT)

    def set(self, brightness: Brightness) -> None:
        try:
            import screen_brightness_control as sbc
            sbc.set_brightness(brightness.value)
        except Exception as exc:
            logger.warning("Brightness unavailable (set): %s", exc)
