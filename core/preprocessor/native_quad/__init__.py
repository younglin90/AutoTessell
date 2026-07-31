"""Runtime-disconnected strict-quad product diagnostics.

Nothing in this package selects a preprocessor route or emits mesh output.
"""

from .strict_pair_preflight import diagnose_strict_quad_pair_preflight

__all__ = ["diagnose_strict_quad_pair_preflight"]
