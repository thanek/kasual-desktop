"""Windows gamepad input adapters — pygame reader + ViGEmBus/HidHide exclusive mode.

Imports are kept lazy (per submodule) so this package has no import-time side
effects — the composition root (``windows_main``) imports the concrete adapter
it needs directly.
"""
