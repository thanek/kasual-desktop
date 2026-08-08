"""Which half of the layer-shell integration this Qt is missing, if either.

The plugin is looked for first, and not merely for tidiness: it lives inside
*this* Qt's own plugin directory, so its presence is what says the installation
matches the Qt that PyQt6 runs on. The library's soname cannot answer that.
"""

from domain.preflight.layer_shell import LayerShellProbe, LayerShellState
from infrastructure.linux.wayland import layer_shell


class QtLayerShellProbe(LayerShellProbe):
    def state(self) -> LayerShellState:
        if layer_shell.integration_plugin() is None:
            return LayerShellState.NO_PLUGIN
        if not layer_shell.is_available():
            return LayerShellState.NO_LIBRARY
        return LayerShellState.READY
