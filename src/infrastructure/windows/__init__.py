"""Windows-specific infrastructure implementations for Kasual Desktop.

Imports are kept lazy (per submodule) so this package has no import-time side
effects — the composition root (``windows_main``) imports the concrete adapters
it needs directly.
"""
