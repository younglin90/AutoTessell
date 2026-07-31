"""Runtime-disconnected strict-quad product diagnostics.

Nothing in this package selects a preprocessor route or emits mesh output.
"""

from .strict_pair_preflight import diagnose_strict_quad_pair_preflight
from .strict_pair_product_l0 import materialize_strict_quad_fixed_pair_product_l0

__all__ = [
    "diagnose_strict_quad_pair_preflight",
    "materialize_strict_quad_fixed_pair_product_l0",
]
