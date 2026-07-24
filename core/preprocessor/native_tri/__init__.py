"""Guarded native-tri operator-loop MVP.

The package is intentionally separate from ``native_remesh``.  Phase 0 only
provides transactional safety checks; it does not yet implement remeshing
quality moves.
"""

from .operator_loop import (
    GuardReport,
    MeshState,
    OperatorKind,
    OperatorTransaction,
)

__all__ = [
    "GuardReport",
    "MeshState",
    "OperatorKind",
    "OperatorTransaction",
]
