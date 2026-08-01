"""Guarded native-tri operator-loop MVP.

The package is intentionally separate from ``native_remesh``.  Phase 0 only
provides transactional safety checks; it does not yet implement remeshing
quality moves.
"""

from .bijective_shell import (
    BijectiveShell,
    PointProvenance,
    RoundContainmentReport,
    ShellBuildResult,
    ShellCheckpointReport,
    ShellCoordinate,
    ShellProjectionStatus,
    ShellProvenanceReport,
    SourceFacePayload,
    build_linear_bijective_shell,
)
from .operator_loop import (
    GuardReport,
    MeshState,
    OperatorKind,
    OperatorTransaction,
    estimate_curvature_sizing,
    shell_provenance_reporting_enabled,
)
from .metric import BLHandoffReport, audit_bl_handoff
from .release_route import NativeTriReleaseResult, NativeTriSourceAuthority, run_native_tri_release

__all__ = [
    "BijectiveShell",
    "BLHandoffReport",
    "GuardReport",
    "MeshState",
    "OperatorKind",
    "OperatorTransaction",
    "PointProvenance",
    "RoundContainmentReport",
    "ShellBuildResult",
    "ShellCheckpointReport",
    "ShellCoordinate",
    "ShellProjectionStatus",
    "ShellProvenanceReport",
    "SourceFacePayload",
    "build_linear_bijective_shell",
    "audit_bl_handoff",
    "estimate_curvature_sizing",
    "shell_provenance_reporting_enabled",
    "NativeTriReleaseResult",
    "NativeTriSourceAuthority",
    "run_native_tri_release",
]
