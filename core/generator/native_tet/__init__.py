"""AutoTessell 자체 tet mesh 엔진 (TetWild-lite).

v0.4 native-first. fTetWild / TetGen / Netgen 의존 없이 순수 Python 으로
closed watertight 표면 메쉬를 부피 tet mesh 로 변환.

### 파이프라인 (beta110 → beta630, 55 rounds)

Phase A (기본 on):
    feature detection → Delaunay → triangle recovery → boundary-aware
    sliver filter → interior Laplacian smoothing → inverted tet validator.

Phase B (opt-in; standard/fine 자동):
    edge split / collapse / flip (2-3, 3-2, 4-4) + tangent surface
    smoothing, 벡터화된 local ops.

Phase C (opt-in; fine 자동):
    envelope-based surface preservation + BVH snap + quality stop
    criterion + adaptive scalar sizing + curvature-aligned anisotropic
    metric.

Phase F (opt-in; fine 자동):
    BSP constrained triangle insertion → Bowyer-Watson incremental
    insertion → post-snap → edge recovery (midpoint).

### 지원 기능

- target_cells heuristic
- progress_cb (stage, pct, info)
- tolerance + float128 + fractions.Fraction staged predicates
- input pre-check (duplicate / zero-area / non-watertight / non-manifold /
  self-intersection AABB)
- orphan vertex cleanup + cell-drop rollback + large-mesh auto-conservative
"""
from __future__ import annotations

from core.generator.native_tet.harness import (
    TetHarnessResult,
    run_native_tet_harness,
)
from core.generator.native_tet.mesher import (
    NativeTetResult,
    generate_native_tet,
)
from core.generator.native_tet.quality import (
    QualitySnapshot,
    snapshot as quality_snapshot,
    snapshot_to_dict as quality_snapshot_to_dict,
    should_stop,
    tet_aspect_ratio,
    tet_min_dihedral_deg,
    tet_shape_quality,
)
from core.generator.native_tet.cdt_check import (
    CDTCheckResult,
    check_edge_recovery,
)
from core.generator.native_tet.features import (
    FeatureInfo,
    detect_features,
)
from core.generator.native_tet.input_check import (
    InputCheckResult,
    check_input,
)


__all__ = [
    "NativeTetResult",
    "generate_native_tet",
    "TetHarnessResult",
    "run_native_tet_harness",
    "QualitySnapshot",
    "quality_snapshot",
    "quality_snapshot_to_dict",
    "should_stop",
    "tet_aspect_ratio",
    "tet_min_dihedral_deg",
    "tet_shape_quality",
    "CDTCheckResult",
    "check_edge_recovery",
    "FeatureInfo",
    "detect_features",
    "InputCheckResult",
    "check_input",
]
