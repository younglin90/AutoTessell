"""native_tet MVP 메쉬 생성기."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)

if TYPE_CHECKING:
    from core.generator.native_tet.rescue_gate import TetBoundaryAudit


@dataclass(frozen=True, slots=True)
class _PhaseAProvenanceCheckpoint:
    """Immutable test-only arrays observed at a fixed native-tet boundary."""

    stage: str
    source_points: np.ndarray
    source_faces: np.ndarray
    candidate_points: np.ndarray
    candidate_tets: np.ndarray


def _immutable_observability_snapshot(values: np.ndarray) -> np.ndarray:
    """Return C-order diagnostic snapshot backed by immutable bytes."""
    contiguous = np.ascontiguousarray(values)
    return np.frombuffer(
        contiguous.tobytes(order="C"), dtype=contiguous.dtype
    ).reshape(contiguous.shape)


def _report_phase_a_provenance_checkpoint(
    observer: Any,
    *,
    stage: str,
    source_points: np.ndarray,
    source_faces: np.ndarray,
    candidate_points: np.ndarray,
    candidate_tets: np.ndarray,
) -> None:
    """Report immutable evidence; observer failure never changes mesh output."""
    try:
        observer(
            _PhaseAProvenanceCheckpoint(
                stage=stage,
                source_points=_immutable_observability_snapshot(source_points),
                source_faces=_immutable_observability_snapshot(source_faces),
                candidate_points=_immutable_observability_snapshot(candidate_points),
                candidate_tets=_immutable_observability_snapshot(candidate_tets),
            )
        )
    except Exception as exc:
        log.warning(
            "native_tet_phase_a_provenance_observer_failed",
            stage=stage,
            error=str(exc)[:120],
        )


def _input_vertices_exactly_present_l0(
    source_vertices: object,
    candidate_vertices: object,
) -> tuple[bool, int]:
    """Audit exact source-coordinate presence without changing either array.

    This L0-only helper deliberately does not use an epsilon: accepting a
    displaced source corner as present would be a false provenance
    certificate.  Malformed or non-finite coordinates cannot be certified and
    therefore fail closed.  Candidate order and duplicate coordinates are
    irrelevant to this read-only membership check.
    """
    try:
        source = np.asarray(source_vertices)
        candidate = np.asarray(candidate_vertices)
    except (TypeError, ValueError):
        return False, 0

    if source.ndim != 2 or source.shape[1:] != (3,):
        return False, 0
    missing_if_uncertified = int(source.shape[0])
    if missing_if_uncertified == 0 or candidate.ndim != 2 or candidate.shape[1:] != (3,):
        return False, missing_if_uncertified

    arrays = (source, candidate)
    if any(
        not np.issubdtype(vertices.dtype, np.number)
        or np.issubdtype(vertices.dtype, np.complexfloating)
        or not bool(np.all(np.isfinite(vertices)))
        for vertices in arrays
    ):
        return False, missing_if_uncertified

    candidate_keys = {tuple(vertex) for vertex in candidate}
    missing = sum(tuple(vertex) not in candidate_keys for vertex in source)
    return missing == 0, missing


def _p4c_candidate_meets_acceptance_l0(
    source_vertices: object,
    source_faces: object,
    candidate_vertices: object,
    candidate_tets: object,
    *,
    old_mean_quality: float,
    candidate_mean_quality: float,
    old_cell_count: int,
    candidate_cell_count: int,
) -> tuple[bool, int, TetBoundaryAudit]:
    """Apply the immutable-source gate before accepting a P4C candidate.

    Cell count is deliberately only a coarse safety floor here.  An external
    fallback may improve quality while simplifying away an exact source
    corner; that candidate must never replace the shape-preserving native
    mesh.
    """
    source_preserved, missing_source_vertices = _input_vertices_exactly_present_l0(
        source_vertices, candidate_vertices
    )
    from core.generator.native_tet.rescue_gate import (
        audit_source_topology,
        audit_tet_boundary,
    )

    try:
        source_topology = audit_source_topology(
            np.asarray(source_vertices, dtype=np.float64),
            np.asarray(source_faces, dtype=np.int64),
            np.asarray(candidate_vertices, dtype=np.float64),
            np.asarray(candidate_tets, dtype=np.int64),
        )
        topology = source_topology.boundary
        source_topology_valid = bool(source_topology.valid)
    except Exception:
        topology = audit_tet_boundary(candidate_vertices, candidate_tets)
        source_topology_valid = False
    topology_preserved = source_topology_valid
    accepted = bool(
        source_preserved
        and topology_preserved
        and float(candidate_mean_quality) > float(old_mean_quality)
        and int(candidate_cell_count) >= max(50, int(old_cell_count) // 4)
    )
    return accepted, missing_source_vertices, topology


def _measure_final_shape_evidence_l0(
    source_vertices: object,
    source_faces: object,
    candidate_vertices: object,
    candidate_tets: object,
) -> tuple[float, float, float]:
    """Measure shape evidence from the arrays that will actually be returned."""
    from core.generator.native_tet.hausdorff import hausdorff_vs_input
    from core.generator.native_tet.plane_coverage import plane_coverage

    source = np.asarray(source_vertices, dtype=np.float64)
    faces = np.asarray(source_faces, dtype=np.int64)
    points = np.asarray(candidate_vertices, dtype=np.float64)
    tets = np.asarray(candidate_tets, dtype=np.int64)
    coverage = plane_coverage(source, faces, points, tets)
    distance = hausdorff_vs_input(
        source,
        faces,
        points,
        tets,
        n_samples_per_tri=2,
    )
    diagonal = float(np.linalg.norm(np.ptp(source, axis=0))) + 1e-30
    return (
        float(coverage.plane_coverage),
        float(coverage.area_coverage),
        float(distance.h_symmetric / diagonal),
    )


def _native_tet_large_pass_enabled(n_cells: int) -> bool:
    """Return whether optional large-mesh passes may run.

    The optional passes are intentionally disabled for tiny cavities/fixtures:
    below 500 cells their fixed overhead and fallback behavior are not useful.
    Keep this as a small, testable contract instead of duplicating the cutoff
    at each call site.
    """
    return int(n_cells) >= 500


def _best_of_candidate_meets_target_floor(
    n_cells: int,
    target_cells: int | None,
) -> bool:
    """Check the conservative minimum cell floor for a candidate mesh."""
    if target_cells is None:
        return True
    target = int(target_cells)
    if target <= 0:
        return True
    return int(n_cells) >= int(np.ceil(0.30 * target))


def _commit_sidedness_nonincreasing_candidate(
    before_points: np.ndarray,
    before_tets: np.ndarray,
    candidate_points: np.ndarray,
    candidate_tets: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, int | bool]]:
    """Commit a geometry candidate only when both sidedness debts do not grow.

    Same-side overlap and near-coplanar ambiguity are independent hard debts;
    decreasing one must never compensate for increasing the other.  Rejection
    returns the exact input objects so the caller's transaction is lossless.
    """
    from core.generator.native_tet.rescue_gate import (
        audit_internal_face_sidedness,
    )

    before = audit_internal_face_sidedness(before_points, before_tets)
    candidate = audit_internal_face_sidedness(candidate_points, candidate_tets)
    accepted = bool(
        candidate.n_same_side_internal_faces
        <= before.n_same_side_internal_faces
        and candidate.n_ambiguous_internal_faces
        <= before.n_ambiguous_internal_faces
    )
    report: dict[str, int | bool] = {
        "accepted": accepted,
        "before_same_side_internal_faces": before.n_same_side_internal_faces,
        "candidate_same_side_internal_faces": (
            candidate.n_same_side_internal_faces
        ),
        "before_ambiguous_internal_faces": before.n_ambiguous_internal_faces,
        "candidate_ambiguous_internal_faces": (
            candidate.n_ambiguous_internal_faces
        ),
        "exact_rollback": not accepted,
    }
    if accepted:
        return candidate_points, candidate_tets, report
    return before_points, before_tets, report


def _commit_cvt3d_sidedness_nonincreasing_candidate(
    before_points: np.ndarray,
    before_tets: np.ndarray,
    candidate_points: np.ndarray,
    candidate_tets: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, int | bool]]:
    """Commit a CVT candidate only when both strict internal-face debts hold.

    CVT can improve a degenerate-cell count while moving two opposite apexes
    onto the same side of an internal face.  That is not a valid trade.  Keep
    the generic sidedness transaction's exact-object rollback and attach the
    degenerate counts solely as diagnostic evidence for the fail-closed path.
    """
    from core.generator.native_tet.rescue_gate import audit_tet_boundary

    selected_points, selected_tets, report = (
        _commit_sidedness_nonincreasing_candidate(
            before_points,
            before_tets,
            candidate_points,
            candidate_tets,
        )
    )
    before = audit_tet_boundary(before_points, before_tets)
    candidate = audit_tet_boundary(candidate_points, candidate_tets)
    return selected_points, selected_tets, {
        **report,
        "before_degenerate_tets": int(before.n_degenerate_tets),
        "candidate_degenerate_tets": int(candidate.n_degenerate_tets),
    }


def _commit_degenerate_removal_source_candidate(
    source_points: np.ndarray,
    source_faces: np.ndarray,
    before_points: np.ndarray,
    before_tets: np.ndarray,
    candidate_points: np.ndarray,
    candidate_tets: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, int | bool]]:
    """Commit a BETA2825 candidate only with immutable-source provenance.

    The local 3-2/collapse/flap operations may remove a degenerate tet while
    also changing the exterior's source ownership.  Area and absolute-volume
    checks cannot certify that contract.  Each source-provenance predicate and
    inversion count is therefore an independent commit condition.  Rejection
    returns the exact pre-candidate objects; no repair is attempted here.
    """
    from core.generator.native_tet.rescue_gate import (
        audit_source_component_bijection,
        audit_tet_boundary,
    )

    before_components = audit_source_component_bijection(
        source_points,
        source_faces,
        before_points,
        before_tets,
    )
    candidate_components = audit_source_component_bijection(
        source_points,
        source_faces,
        candidate_points,
        candidate_tets,
    )
    before_boundary = audit_tet_boundary(before_points, before_tets)
    candidate_boundary = audit_tet_boundary(candidate_points, candidate_tets)
    accepted = bool(
        candidate_components.bijective
        and candidate_components.source_faces_preserved
        and candidate_components.n_unowned_candidate_faces == 0
        and candidate_boundary.n_inverted_tets
        <= before_boundary.n_inverted_tets
    )
    report: dict[str, int | bool] = {
        "accepted": accepted,
        "before_component_bijective": bool(before_components.bijective),
        "candidate_component_bijective": bool(candidate_components.bijective),
        "before_source_faces_preserved": bool(
            before_components.source_faces_preserved
        ),
        "candidate_source_faces_preserved": bool(
            candidate_components.source_faces_preserved
        ),
        "before_unowned_candidate_faces": int(
            before_components.n_unowned_candidate_faces
        ),
        "candidate_unowned_candidate_faces": int(
            candidate_components.n_unowned_candidate_faces
        ),
        "before_inverted_tets": int(before_boundary.n_inverted_tets),
        "candidate_inverted_tets": int(candidate_boundary.n_inverted_tets),
        "exact_rollback": not accepted,
    }
    if accepted:
        return candidate_points, candidate_tets, report
    return before_points, before_tets, report


def _optional_pass_result(result: Any, n_expected: int) -> tuple[Any, str | None]:
    """Normalize an optional-pass return value without raising downstream.

    Optional native-tet passes must either return a tuple with the expected
    arity or be treated as a guarded no-op.  ``n_expected`` is kept in the
    signature for callers that record the expected local mesh size; it is not
    used to reinterpret a helper's return contract.
    """
    del n_expected
    if result is None:
        return None, "helper_returned_none"
    if not isinstance(result, tuple) or len(result) != 3:
        return None, "helper_return_contract_mismatch"
    return result, None


def _run_near_wall_prewrite(
    points: np.ndarray,
    tets: np.ndarray,
    surface_vertices: np.ndarray,
    surface_faces: np.ndarray,
    *,
    target_cells: int | None,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Run the opt-in near-wall refinement immediately before serialization.

    The measurement lane is default-off.  When enabled, the current mesh must
    already satisfy the conservative target-cell floor; otherwise returning
    the original objects unchanged avoids making a tiny fixture look like a
    refinement success.
    """
    if os.environ.get("AUTO_TESSELL_NEAR_WALL_OFF", "0") == "1":
        return points, tets, False
    if os.environ.get("AUTO_TESSELL_NEAR_WALL", "0") != "1":
        return points, tets, False
    if not _best_of_candidate_meets_target_floor(
        int(np.asarray(tets).shape[0]), target_cells
    ):
        return points, tets, False
    try:
        from core.generator.native_tet.near_wall import refine_near_wall

        threshold = float(
            os.environ.get("AUTO_TESSELL_NEAR_WALL_SKEW_THRESHOLD", "0.0")
        )
        max_owners = max(
            1, int(os.environ.get("AUTO_TESSELL_NEAR_WALL_MAX_OWNERS", "32"))
        )
        result = refine_near_wall(
            np.asarray(points, dtype=np.float64),
            np.asarray(tets, dtype=np.int64),
            np.asarray(surface_vertices, dtype=np.float64),
            np.asarray(surface_faces, dtype=np.int64),
            max_owners=max_owners,
        )
        if result.accepted <= 0 or result.after_skew >= max(
            threshold, result.before_skew
        ):
            return points, tets, False
        return result.points, result.tets, True
    except Exception as exc:  # pragma: no cover - defensive optional lane
        log.debug("native_tet_near_wall_prewrite_skipped", reason=str(exc)[:160])
        return points, tets, False


@dataclass
class NativeTetResult:
    success: bool
    elapsed: float
    n_cells: int = 0
    n_points: int = 0
    message: str = ""
    # v0.4: dual 변환 등 downstream 사용을 위해 tet array 와 points 를 함께 반환.
    tet_points: np.ndarray | None = None
    tets: np.ndarray | None = None
    # beta830: quality metric 요약 (min_q, mean_q, min_dihedral_deg 등).
    quality: "Any" = None
    # beta1090 (R171) — 비치명 경고 + 개발자 디버그 정보.
    warnings: list[str] | None = None
    debug_info: dict | None = None
    # beta1420 (Q4) — 통합 PASS gate 평가.
    quality_grade: str = "?"           # 'A' / 'B' / 'C' / '?'
    cdt_ratio: float = -1.0
    cdt_face_ratio: float = -1.0       # T3 — surface face 회복률 (strict).
    plane_coverage: float = -1.0       # V1 — fTetWild-style plane conformity.
    plane_area_coverage: float = -1.0
    hausdorff_relative: float = -1.0   # h_symmetric / bbox_diag.
    # beta2336 — pre-mesh self-intersect (P2.6 chain). None = 측정 안 됨
    # (>5000 face), 0 = clean, >0 = 입력 SI 존재.
    n_self_intersect_pre: int | None = None
    # C-QUAL-1 / beta2382 — mesh integrity 의심 플래그.
    # n_cells < n_surface_v / 8 면 True. validator 가 hard mesh 에서
    # 2-cell collapse 케이스 발견 (V=3116, F=6272 → tet=2). 이 플래그가
    # downstream (BL / Hausdorff / GUI) 에서 의심 사례 자동 표시.
    mesh_integrity_suspect: bool = False

    @property
    def ok(self) -> bool:
        """success alias (R171)."""
        return bool(self.success)


def _seed_points_uniform(
    bbox_min: np.ndarray, bbox_max: np.ndarray, spacing: float,
) -> np.ndarray:
    """bbox 내부 uniform grid 시드. spacing 이 bbox 보다 크면 빈 array."""
    diag = float(np.linalg.norm(bbox_max - bbox_min))
    if spacing <= 0 or diag == 0:
        return np.zeros((0, 3))
    # safety: 한 축 당 최대 60 개 (grid size 제한)
    nxyz = np.maximum(
        np.ceil((bbox_max - bbox_min) / spacing).astype(int),
        1,
    )
    nxyz = np.minimum(nxyz, 60)
    xs = np.linspace(bbox_min[0], bbox_max[0], nxyz[0])
    ys = np.linspace(bbox_min[1], bbox_max[1], nxyz[1])
    zs = np.linspace(bbox_min[2], bbox_max[2], nxyz[2])
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    return np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)


# web-QA (2026-07-02): 쓰레기 표면 강건화 — inside_robust 디스패처.
from core.utils.geometry import inside_robust as _inside_winding_number


def _inside_boolean_inputs(
    points: np.ndarray,
    input_paths: list[str],
    boolean_operation: str = "union",
) -> np.ndarray:
    """Classify points against original surfaces using ordered boolean masks."""
    from core.analyzer.readers import read_stl
    from core.utils.geometry import inside_boolean_winding_number

    surfaces: list[tuple[np.ndarray, np.ndarray]] = []
    for input_path in input_paths:
        mesh = read_stl(Path(input_path))
        surfaces.append(
            (
                np.asarray(mesh.vertices, dtype=np.float64),
                np.asarray(mesh.faces, dtype=np.int64),
            )
        )
    if not surfaces:
        raise ValueError("boolean operation requires at least one input surface")
    return inside_boolean_winding_number(
        points, surfaces, operation=boolean_operation
    )


def _inside_boolean_union_inputs(
    points: np.ndarray,
    input_paths: list[str],
) -> np.ndarray:
    """Backward-compatible union wrapper."""
    return _inside_boolean_inputs(points, input_paths, "union")


def _surf_edges_from_faces(F: np.ndarray) -> set:
    """F (N,3) → sorted edge set. Vectorized (beta2210)."""
    if F.shape[0] == 0:
        return set()
    e0 = np.stack([F[:, 0], F[:, 1]], axis=1)
    e1 = np.stack([F[:, 1], F[:, 2]], axis=1)
    e2 = np.stack([F[:, 2], F[:, 0]], axis=1)
    all_e = np.concatenate([e0, e1, e2], axis=0)
    all_e_s = np.sort(all_e, axis=1)
    return set(map(tuple, all_e_s.tolist()))


def _surf_faces_from_F(F: np.ndarray) -> set:
    """F (N,3) → sorted canonical face set. Vectorized (beta2210)."""
    if F.shape[0] == 0:
        return set()
    Fs = np.sort(F, axis=1)
    return set(map(tuple, Fs.tolist()))


def _skew_proxy(pts: np.ndarray, tets: np.ndarray) -> float:
    """Evaluator-faithful max-skewness proxy (BETA2828).

    Reproduces core/evaluator/native_checker.py internal (698-721) and
    boundary (762-779) skewness on an in-memory tet mesh so the pre-write
    locked-smooth accept guard can veto any net worsening of the reported
    metric.  Orientation-free: internal own/nbr order and boundary normal
    sign both cancel out of the projection distance.  Single face-map build.
    """
    T = int(tets.shape[0])
    if T == 0:
        return 0.0
    faces = np.concatenate([
        tets[:, [0, 1, 2]],
        tets[:, [0, 1, 3]],
        tets[:, [0, 2, 3]],
        tets[:, [1, 2, 3]],
    ], axis=0)                                    # (4T, 3)
    owners = np.tile(np.arange(T, dtype=np.int64), 4)  # (4T,)
    sfaces = np.sort(faces, axis=1)
    uniq, inv, counts = np.unique(
        sfaces, axis=0, return_inverse=True, return_counts=True
    )
    inv = np.asarray(inv).ravel()
    cc = pts[tets].mean(axis=1)                   # (T, 3) cell centres
    fc_all = pts[uniq].mean(axis=1)               # (U, 3) face centres
    own_sorted = owners[np.argsort(inv, kind="stable")]  # grouped by face id
    starts = np.zeros(counts.shape[0], dtype=np.int64)
    starts[1:] = np.cumsum(counts)[:-1]

    internal_max = 0.0
    int_mask = counts == 2
    if bool(int_mask.any()):
        st = starts[int_mask]
        p_own = cc[own_sorted[st]]
        p_nbr = cc[own_sorted[st + 1]]
        fc = fc_all[int_mask]
        d = p_nbr - p_own
        d_mag = np.linalg.norm(d, axis=1)
        v = d_mag > 1e-30
        if bool(v.any()):
            diff = fc[v] - p_own[v]
            t = np.einsum("ij,ij->i", diff, d[v]) / (d_mag[v] ** 2)
            proj = p_own[v] + t[:, None] * d[v]
            internal_max = float(
                (np.linalg.norm(fc[v] - proj, axis=1) / d_mag[v]).max()
            )

    boundary_max = 0.0
    bnd_mask = counts == 1
    if bool(bnd_mask.any()):
        st = starts[bnd_mask]
        fv = pts[uniq[bnd_mask]]                   # (B, 3, 3)
        n = np.cross(fv[:, 1] - fv[:, 0], fv[:, 2] - fv[:, 0])
        n_mag = np.linalg.norm(n, axis=1)
        vn = n_mag > 1e-30
        if bool(vn.any()):
            n_unit = n[vn] / n_mag[vn, None]
            cc_own = cc[own_sorted[st]][vn]
            fc = fc_all[bnd_mask][vn]
            nd = np.einsum("ij,ij->i", fc - cc_own, n_unit)
            proj = cc_own + nd[:, None] * n_unit
            denom = np.maximum(np.abs(nd), 1e-30)
            skew = np.linalg.norm(fc - proj, axis=1) / denom
            if skew.size:
                boundary_max = float(np.nanmax(skew))

    return max(internal_max, boundary_max)


def _nonortho_proxy(pts: np.ndarray, tets: np.ndarray) -> float:
    """Evaluator-faithful max non-orthogonality proxy (CYLSKEW4/beta2831).

    Angle (deg) between the internal-face owner/neighbour centroid line and
    the face normal, maximised over all internal faces. 0 = perfectly
    orthogonal, up to 90 = worst. Reuses the `_skew_proxy` face-map build.
    """
    T = int(tets.shape[0])
    if T == 0:
        return 0.0
    faces = np.concatenate([
        tets[:, [0, 1, 2]], tets[:, [0, 1, 3]],
        tets[:, [0, 2, 3]], tets[:, [1, 2, 3]],
    ], axis=0)
    owners = np.tile(np.arange(T, dtype=np.int64), 4)
    sfaces = np.sort(faces, axis=1)
    uniq, inv, counts = np.unique(
        sfaces, axis=0, return_inverse=True, return_counts=True
    )
    inv = np.asarray(inv).ravel()
    cc = pts[tets].mean(axis=1)
    own_sorted = owners[np.argsort(inv, kind="stable")]
    starts = np.zeros(counts.shape[0], dtype=np.int64)
    starts[1:] = np.cumsum(counts)[:-1]

    int_mask = counts == 2
    if not bool(int_mask.any()):
        return 0.0
    st = starts[int_mask]
    p_own = cc[own_sorted[st]]
    p_nbr = cc[own_sorted[st + 1]]
    fv = pts[uniq[int_mask]]                      # (I, 3, 3)
    n = np.cross(fv[:, 1] - fv[:, 0], fv[:, 2] - fv[:, 0])
    n_mag = np.linalg.norm(n, axis=1)
    d = p_nbr - p_own
    d_mag = np.linalg.norm(d, axis=1)
    valid = (n_mag > 1e-30) & (d_mag > 1e-30)
    if not bool(valid.any()):
        return 0.0
    cos_a = np.clip(
        np.abs(np.einsum("ij,ij->i", n[valid], d[valid]))
        / (n_mag[valid] * d_mag[valid]),
        -1.0, 1.0,
    )
    angle_deg = np.degrees(np.arccos(cos_a))
    return float(np.nanmax(angle_deg)) if angle_deg.size else 0.0


_OFFSET_RING_AUTO_MAX_VERTICES = 1000
_OFFSET_RING_AUTO_MAX_FACES = 2000
_OFFSET_RING_VOLUME_REL_TOL = 1e-12


def _offset_ring_mode(
    value: str | None, n_vertices: int, n_faces: int,
) -> tuple[str, bool]:
    """Resolve unset as off; explicit auto remains size-bounded."""
    mode = "off" if value is None else value.strip().lower()
    if mode in {"0", "off", "false"}:
        return "off", False
    if mode in {"1", "on", "true"}:
        return "on", True
    if mode == "auto":
        enabled = (
            n_vertices <= _OFFSET_RING_AUTO_MAX_VERTICES
            and n_faces <= _OFFSET_RING_AUTO_MAX_FACES
        )
        return "auto", enabled
    return "invalid", False


def _raw_proxy_metrics(
    pts: np.ndarray,
    tets: np.ndarray,
    rel_volume_tol: float = _OFFSET_RING_VOLUME_REL_TOL,
) -> tuple[dict[str, float], int, int]:
    """Compute proxy metrics after removing scale-relative degenerate tets."""
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    raw_count = int(tets.shape[0]) if tets.ndim >= 1 else 0
    if pts.ndim != 2 or pts.shape[1:] != (3,) or tets.ndim != 2:
        return {}, raw_count, 0
    if tets.shape[1:] != (4,) or raw_count == 0 or not np.isfinite(pts).all():
        return {}, raw_count, 0

    bbox_diag = float(np.linalg.norm(np.ptp(pts, axis=0)))
    if not np.isfinite(bbox_diag) or bbox_diag <= 0.0:
        return {}, raw_count, 0
    try:
        tet_pts = pts[tets]
    except (IndexError, ValueError):
        return {}, raw_count, 0
    volumes = np.abs(np.einsum(
        "ij,ij->i",
        np.cross(tet_pts[:, 1] - tet_pts[:, 0], tet_pts[:, 2] - tet_pts[:, 0]),
        tet_pts[:, 3] - tet_pts[:, 0],
    )) / 6.0
    volume_floor = bbox_diag ** 3 * max(0.0, float(rel_volume_tol))
    valid = np.isfinite(volumes) & (volumes > volume_floor)
    valid_count = int(valid.sum())
    if valid_count == 0:
        return {}, raw_count, 0

    clean_tets = tets[valid]
    try:
        metrics = {
            "skew": _skew_proxy(pts, clean_tets),
            "nonortho": _nonortho_proxy(pts, clean_tets),
        }
    except Exception:
        return {}, raw_count, valid_count
    if not all(np.isfinite(value) for value in metrics.values()):
        return {}, raw_count, valid_count
    return metrics, raw_count, valid_count


def generate_native_tet(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 12,
    sliver_quality_threshold: float = 0.05,
    max_input_vertices: int = 100000,
    # JJ1 (beta1800) — 입력 자동 수리 (dedup + winding align).
    enable_auto_fix_input: bool = True,
    # beta104 Phase A — TetWild-lite 1 단계.
    enable_phase_a: bool = True,
    feature_angle_deg: float = 30.0,
    recovery_iterations: int = 2,
    protect_boundary_faces: bool = True,
    smooth_iterations: int = 2,
    smooth_relax: float = 0.5,
    # beta160 Phase F — BSP constrained triangle insertion (opt-in fallback).
    # BETA2826 (B-1) — env AUTO_TESSELL_NATIVE_FTETWILD_MODE 자동 활성:
    #   wildmesh-parity 정렬 모드에서 BSP insertion + envelope-aware ops 강제.
    enable_bsp_insertion: bool = False,
    bsp_max_inserts_per_triangle: int = 50,
    # beta630 — edge recovery (opt-in; draft 기본 경로 비활성화 해 성능 유지).
    enable_edge_recovery: bool = False,
    edge_recovery_max_iter: int = 2,
    # beta120 Phase B — local ops + tangent smoothing.
    # 기본 off: O(T^2) / O(V^2) Python 루프라 대형 메쉬에서 느림. 명시 opt-in.
    enable_phase_b: bool = False,
    local_ops_iterations: int = 1,
    split_ratio: float = 4.0 / 3.0,
    collapse_ratio: float = 4.0 / 5.0,
    flip_iterations: int = 1,
    tangent_smooth_iterations: int = 1,
    tangent_smooth_relax: float = 0.3,
    # beta220 — collapse 보수화: iteration 당 최대 cap + cell-drop guard.
    max_collapses_per_iter: int = 200,
    cell_drop_rollback_ratio: float = 0.5,
    # beta810 — extreme sliver drop threshold.
    sliver_drop_min_dihedral_deg: float = 0.5,
    sliver_drop_max_aspect: float = 1e5,
    # beta125 Phase C — envelope + quality stop.
    enable_phase_c: bool = False,
    envelope_eps_relative: float = 0.001,
    quality_target_min_q: float = 0.3,
    quality_improvement_eps: float = 0.005,
    quality_window: int = 3,
    # beta330 — volume target: 사용자가 희망 cell 수 지정 시 seed_density
    # 자동 조정 (bbox 기반 heuristic: target_edge = (V_bbox / target_cells)^(1/3)).
    target_cells: int | None = None,
    # Native-poly opt-in: the dual creates one cell per retained primal point.
    # Generic tet callers leave this unset and retain the legacy contract.
    min_final_vertices: int | None = None,
    # beta410 — progress_cb(stage: str, pct: float, info: dict): 진행 보고.
    progress_cb: "Any" = None,
    # beta140 Phase E2 — curvature-adaptive sizing (split/collapse 기준).
    use_adaptive_sizing: bool = False,
    # beta500 — anisotropic metric 활성 (curvature-aligned SPD tensor).
    use_anisotropic_metric: bool = False,
    anisotropic_ratio: float = 0.5,
    adaptive_min_ratio: float = 0.25,
    adaptive_max_ratio: float = 2.0,
    adaptive_curvature_gain: float = 2.0,
    # beta1350 — AMIPS 통합 (P2).
    enable_amips_smooth: bool = False,
    amips_iterations: int = 2,
    amips_alpha: float = 1.0,
    # beta1360 — chunked Delaunay 자동 스위칭 (P5).
    chunked_delaunay_threshold: int = 30000,
    enable_chunked_delaunay: bool = True,
    chunked_n_div: int = 2,
    # V2 (beta1580) — Steiner edge midpoint 사전 삽입.
    enable_edge_steiner: bool = False,
    edge_steiner_count: int = 1,
    # beta1370 — CDT recovery 통합 (P1).
    enable_cdt_recovery: bool = False,
    cdt_recovery_max_cycles: int = 2,
    cdt_recovery_points_budget: int = 100,
    # beta1430 (Q6) — outer loop: B 등급 이하면 추가 cycle 까지.
    cdt_recovery_outer_iter: int = 1,
    cdt_recovery_target_ratio: float = 0.9,
    # beta1530 (V3) — boundary clipping (외부 tet 제거).
    enable_boundary_clip: bool = False,
    boundary_clip_threshold: float = 0.5,
    # W4 (beta1610) — best-of-two score 가중 (area / cdt / mq).
    # JJ2 (beta1810) — mq 가중 0.2 → 0.35 으로 강화 (hard mesh sliver 회피).
    score_weight_area: float = 0.4,
    score_weight_cdt: float = 0.25,
    score_weight_mq: float = 0.35,
    prefer_base_threshold: float = 0.02,
    # P2.2 / beta2310 — AMIPS smoothing 의 torch (CUDA 가용 시 GPU) 라우팅.
    # HARNESS_PARAMS["tier_native_tet"]["fine"] 에서 자동 활성. CPU 환경
    # 에서는 torch CPU 텐서 batch (numpy 대비 약간 느릴 수 있어 fine only).
    use_torch_amips: bool = False,
    # C1.5 / beta2373 — tier-aware QED min-face threshold override (Hu 2018 §3.4).
    # None 이면 env / default (20000). HARNESS_PARAMS 에서 fine 은 10000 로
    # 더 적극적으로 simplification.
    qed_min_faces: int | None = None,
    # C1.7 / beta2378 — Stellar split-pass tier-gated activation. fine 에서
    # 자동 ON (HARNESS_PARAMS), 다른 tier 는 OFF. AUTO_TESSELL_STELLAR_SPLIT
    # env 가 우선 (사용자 explicit override).
    enable_stellar_split: bool = False,
    # BOOLMERGE4 compatibility key; prefer boolean_input_paths for new callers.
    boolean_union_input_paths: list[str] | None = None,
    # BOOLMERGE5b: JSON-safe ordered STL provenance and volume boolean mask.
    boolean_input_paths: list[str] | None = None,
    boolean_operation: str = "union",
    _phase_a_observer: Any = None,
) -> NativeTetResult:
    """입력 표면 메쉬 → tet polyMesh (MVP).

    Args:
        vertices: (V, 3) 표면 점.
        faces: (F, 3) 표면 triangles (watertight 가정).
        case_dir: OpenFOAM case 디렉터리 (constant/polyMesh 생성됨).
        target_edge_length: 내부 grid spacing. None 이면 bbox_diag / seed_density.
        seed_density: target_edge_length 가 None 일 때 bbox_diag 분할 수.
        sliver_quality_threshold: shape quality (정사면체≈1, sliver≈0) 하한. 이
            값 미만 tet 은 제거. beta62: 0.05 기본이었으나 복잡 형상에서 모든 tet
            이 탈락해 harness 수렴 실패 → 기본값을 quality 별로 조정 가능하게 노출.

    Returns:
        NativeTetResult.
    """
    t0 = time.perf_counter()
    _smooth_then_drop_sidedness_transaction: dict[str, int | bool] | None = None
    _degenerate_removal_source_transaction: dict[str, int | bool] | None = None
    try:
        from scipy.spatial import Delaunay
    except Exception as exc:
        return NativeTetResult(False, 0.0, message=f"scipy 필요: {exc}")

    try:
        from core.generator.polymesh_writer import PolyMeshWriter
    except Exception as exc:
        return NativeTetResult(False, 0.0, message=f"polymesh_writer import 실패: {exc}")

    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    if V.size == 0 or F.size == 0:
        return NativeTetResult(False, 0.0, message="빈 입력 mesh")

    # Preserve the caller-visible source before any repair or reconstruction
    # rebinds ``V``/``F``.  Final shape, topology, and provenance evidence must
    # certify this immutable input, never a convenient repaired surrogate.
    # One owning copy per array is intentional: callers may pass writable views,
    # while later native-tet stages are allowed to mutate or replace working
    # arrays.  Read-only flags make accidental aliasing fail immediately.
    _input_source_vertices = np.array(V, dtype=np.float64, order="C", copy=True)
    _input_source_faces = np.array(F, dtype=np.int64, order="C", copy=True)
    _input_source_vertices.setflags(write=False)
    _input_source_faces.setflags(write=False)

    # BETA2833 (B-8) — env AUTO_TESSELL_USE_FTETWILD_LOOP=1 시 dedicated
    # ftetwild_main_loop 직접 호출 → 기존 mesher pipeline 우회. wildmesh parity
    # T 94.5% 도달 path. polyMesh write + NativeTetResult 채운 후 즉시 return.
    if os.environ.get("AUTO_TESSELL_USE_FTETWILD_LOOP", "0") == "1":
        import time as _time
        _t_ftw = _time.perf_counter()
        try:
            from core.generator.native_tet.ftetwild_main_loop import (
                ftetwild_main_loop,
            )
            from core.generator.polymesh_writer import PolyMeshWriter as _PMW
            _r_ftw = ftetwild_main_loop(
                V, F,
                target_edge_length=target_edge_length,
                edge_length_r=float(
                    os.environ.get("AUTO_TESSELL_NATIVE_EDGE_LENGTH_R", "0.06")
                ),
                epsilon=float(
                    os.environ.get("AUTO_TESSELL_NATIVE_FTETWILD_EPSILON", "1e-3")
                ),
                max_its=int(
                    os.environ.get("AUTO_TESSELL_NATIVE_FTETWILD_MAX_ITS", "20")
                ),
                stop_quality=float(
                    os.environ.get("AUTO_TESSELL_NATIVE_FTETWILD_STOP_Q", "10.0")
                ),
            )
            if _r_ftw.success and _r_ftw.tets.shape[0] > 0:
                from core.generator.native_tet.rescue_gate import (
                    audit_source_topology as _audit_source_topology_ftw,
                )

                _ftw_topology_audit = _audit_source_topology_ftw(
                    _input_source_vertices,
                    _input_source_faces,
                    np.asarray(_r_ftw.pts, dtype=np.float64),
                    np.asarray(_r_ftw.tets, dtype=np.int64),
                )
                if not _ftw_topology_audit.valid:
                    return NativeTetResult(
                        False,
                        _time.perf_counter() - _t_ftw,
                        n_cells=int(_r_ftw.tets.shape[0]),
                        n_points=int(_r_ftw.pts.shape[0]),
                        message=(
                            "ftetwild loop source-aware strict topology is invalid"
                        ),
                        tet_points=_r_ftw.pts,
                        tets=_r_ftw.tets,
                    )
                try:
                    _PMW().write(
                        _r_ftw.pts,
                        _r_ftw.tets,
                        case_dir,
                        point_precision=17,
                    )
                except Exception as _exc_w:
                    log.warning(
                        "ftetwild_polymesh_write_failed",
                        reason=str(_exc_w)[:200],
                    )
                    return NativeTetResult(
                        False,
                        _time.perf_counter() - _t_ftw,
                        n_cells=int(_r_ftw.tets.shape[0]),
                        n_points=int(_r_ftw.pts.shape[0]),
                        message=(
                            "native_tet writer rejected output topology: "
                            f"{_exc_w}"
                        ),
                    )
                _elapsed = _time.perf_counter() - _t_ftw
                log.info(
                    "ftetwild_loop_used",
                    n_iters=int(_r_ftw.n_iters_used),
                    n_cells=int(_r_ftw.tets.shape[0]),
                    n_points=int(_r_ftw.pts.shape[0]),
                    mean_q=round(float(_r_ftw.final_mean_q), 4),
                    elapsed=round(_elapsed, 3),
                )
                return NativeTetResult(
                    success=True,
                    elapsed=_elapsed,
                    n_cells=int(_r_ftw.tets.shape[0]),
                    n_points=int(_r_ftw.pts.shape[0]),
                    tet_points=_r_ftw.pts,
                    tets=_r_ftw.tets,
                    quality_grade=(
                        "A" if _r_ftw.final_mean_q >= 0.20 else "?"
                    ),
                    message=_r_ftw.message,
                )
        except Exception as _exc_ftw:
            log.warning(
                "ftetwild_loop_failed_fallback",
                reason=str(_exc_ftw)[:200],
            )

    def _prog(stage: str, pct: float, **info: object) -> None:
        if progress_cb is None:
            return
        try:
            progress_cb(stage, float(pct), dict(info))
        except Exception:
            pass

    _prog("start", 0.0, n_verts=V.shape[0], n_faces=F.shape[0])

    # UUU2 (beta2099) — self-intersect 탐지 활성 (식별만).
    from core.preprocessor.native_remesh import (
        _UUU1_SI_DETECT, _detect_self_intersections,
        _UUU3_REPAIR_CANDIDATES, _si_repair_candidates,
        _UUU5_FACE_SPLIT, _apply_face_split,
    )
    # beta2336 — UUU2 si_pairs count 를 mesher local 에 capture (NativeTetResult
    # 의 n_self_intersect_pre 에 후속 채우기 위함).
    _pre_mesh_si_count: int | None = None
    try:
        if _UUU1_SI_DETECT:
            si_pairs = _detect_self_intersections(V, F)
            _pre_mesh_si_count = int(len(si_pairs))
            log.info("native_tet_uuu2_si_detect", n_si=int(len(si_pairs)))
            if _UUU3_REPAIR_CANDIDATES and len(si_pairs) > 0:
                cands = _si_repair_candidates(V, F, si_pairs)
                n_split = sum(1 for c in cands if c["op"] == "split")
                n_merge = sum(1 for c in cands if c["op"] == "merge")
                log.info("native_tet_uuu4_candidates",
                         n_candidates=len(cands), n_split=n_split, n_merge=n_merge)
                # UUU6 (beta2107) — face split 실제 적용 (단조 가드 try/except).
                # beta2350 — split 후 SI 재검출 → 늘어났으면 revert (SI 악화 방지).
                if _UUU5_FACE_SPLIT and len(cands) > 0:
                    try:
                        V_cand, F_cand, n_split = _apply_face_split(V, F, cands, max_split=20)
                        if n_split > 0:
                            # beta2350: post-split SI count 검증.
                            try:
                                si_post = _detect_self_intersections(V_cand, F_cand)
                                _accept = int(len(si_post)) <= int(len(si_pairs))
                            except Exception:
                                _accept = True   # detect 실패 시 split 결과 그대로 채택 (이전 동작).
                            if _accept:
                                V, F = V_cand, F_cand
                                log.info(
                                    "native_tet_uuu6_face_split_applied",
                                    n_split=int(n_split),
                                    si_pre=int(len(si_pairs)),
                                    si_post=int(len(si_post)) if "si_post" in dir() else None,
                                )
                            else:
                                log.info(
                                    "native_tet_uuu6_face_split_reverted",
                                    n_split=int(n_split),
                                    si_pre=int(len(si_pairs)),
                                    si_post=int(len(si_post)),
                                    reason="SI_increased",
                                )
                    except Exception as exc:
                        log.debug("native_tet_uuu6_face_split_skipped", reason=str(exc))
    except Exception as exc:
        log.debug("native_tet_uuu2_si_detect_skipped", reason=str(exc))

    # beta420 — 입력 건강성 pre-check (경고만, 실행 계속).
    chk = None
    try:
        from core.generator.native_tet.input_check import check_input

        chk = check_input(V, F)
        # JJ1 (beta1800) — 자동 입력 수리: dedup + zero-area drop + winding align.
        # KK1 (beta1850) — chk 가 비-watertight 또는 non-manifold 감지 시 aggressive=True.
        if enable_auto_fix_input:
            try:
                from core.generator.native_tet.input_check import auto_fix_input
                aggressive = False
                if chk is not None:
                    if chk.n_boundary_edges > 0 or chk.n_nonmanifold_edges > 0:
                        aggressive = True
                V_fix, F_fix, fix_info = auto_fix_input(
                    V, F, dup_tol=1e-9, drop_zero_area=True, align_winding=True,
                    aggressive=aggressive,
                )
                if (
                    fix_info.get("n_dedup", 0)
                    or fix_info.get("n_zero_area_drop", 0)
                    or fix_info.get("n_winding_flip", 0)
                    or aggressive
                ):
                    log.info(
                        "native_tet_auto_fix",
                        n_dedup=int(fix_info.get("n_dedup", 0)),
                        n_zero_area=int(fix_info.get("n_zero_area_drop", 0)),
                        n_winding_flip=int(fix_info.get("n_winding_flip", 0)),
                        aggressive=bool(aggressive),
                    )
                    V = V_fix.astype(np.float64)
                    F = F_fix.astype(np.int64)
            except Exception as exc:
                log.debug("native_tet_auto_fix_skipped", reason=str(exc))

            # L3-AI / beta2807 — voxel SDF + marching cubes 재구성.
            # extreme fragile input (SI > 500) 강제 회복.
            # env AUTO_TESSELL_L3_AI_REPAIR=1 활성 (default OFF — 시간 비싸).
            if os.environ.get("AUTO_TESSELL_L3_AI_REPAIR", "0") == "1":
                try:
                    from core.preprocessor.l3_ai_surface_repair import (
                        voxel_sdf_repair,
                    )
                    from core.preprocessor.native_repair.self_intersect import (
                        detect_self_intersections,
                    )
                    _si_chk = detect_self_intersections(V, F)
                    if int(_si_chk.n_intersections) > 500:
                        _l3_res_size = int(os.environ.get(
                            "AUTO_TESSELL_L3_VOXEL_RES", "64",
                        ))
                        V_l3, F_l3, l3_res = voxel_sdf_repair(
                            V, F,
                            voxel_resolution=_l3_res_size,
                            smooth_iters=2,
                            iso_value=0.0,
                        )
                        if l3_res.success and F_l3.shape[0] >= 4:
                            V = V_l3.astype(np.float64)
                            F = F_l3.astype(np.int64)
                            log.info(
                                "native_tet_l3_ai_voxel_repair",
                                method=l3_res.method,
                                voxel_res=l3_res.voxel_resolution,
                                pre_si=l3_res.pre_si_count,
                                post_si=l3_res.post_si_count,
                                pre_mq=round(l3_res.pre_mq, 4),
                                post_mq=round(l3_res.post_mq, 4),
                                v_after=l3_res.post_n_vertices,
                                f_after=l3_res.post_n_faces,
                            )
                except Exception as exc:
                    log.debug("native_tet_l3_ai_skipped",
                              reason=str(exc)[:120])

            # AGGRESSIVE-REPAIR / beta2805 — input fragility (high SI count
            # or low surface mq) 케이스 강력 pre-pass.
            # env AUTO_TESSELL_AGGR_REPAIR=1 활성 (default OFF — 안전).
            if os.environ.get("AUTO_TESSELL_AGGR_REPAIR", "0") == "1":
                try:
                    from core.preprocessor.aggressive_input_repair import (
                        aggressive_input_repair,
                    )
                    V_ar, F_ar, ar_res = aggressive_input_repair(
                        V, F,
                        max_sweep=3,
                        si_threshold=100,
                        mq_threshold=0.05,
                    )
                    if (
                        ar_res.success
                        and (ar_res.post_si_count <= ar_res.pre_si_count
                             or ar_res.post_min_quality > ar_res.pre_min_quality)
                        and F_ar.shape[0] >= 4
                    ):
                        V = V_ar.astype(np.float64)
                        F = F_ar.astype(np.int64)
                        log.info(
                            "native_tet_aggressive_repair",
                            iterations=ar_res.n_iterations,
                            si_before=ar_res.pre_si_count,
                            si_after=ar_res.post_si_count,
                            mq_before=round(ar_res.pre_min_quality, 4),
                            mq_after=round(ar_res.post_min_quality, 4),
                            v_before=ar_res.pre_n_vertices,
                            v_after=ar_res.post_n_vertices,
                        )
                except Exception as exc:
                    log.debug("native_tet_aggr_repair_skipped",
                              reason=str(exc)[:120])

            # P4-B-4 (beta2243) + P1.4 (beta2308) — quadric error decimation
            # pre-pass. 입력 face > AUTO_TESSELL_QED_MIN_F 시 face 수 절반으로
            # 감소 (G&H 1997). MM1 직전 sliver 격감.
            #
            # beta2308 (P1.4 from sharded-weaving-raccoon plan):
            #   default OFF → "auto" — 50k face 초과 입력에 대해 자동 활성화.
            #   AUTO_TESSELL_QED=0 으로 강제 OFF, =1 로 강제 ON 여전히 가능.
            #   default min_F 2000 → 50000 으로 raise (small mesh 영향 0).
            # C1.5 / beta2364: threshold 50k → 20k 로 lower — Hu 2018 §3.4
            #   simplification 더 적극. medium tier (5k-50k face) 의 sliver
            #   격감 효과. small mesh (<20k) 영향 여전히 0.
            try:
                _qed_env = os.environ.get("AUTO_TESSELL_QED", "auto")
                # C1.5 / beta2373 — tier-aware override 우선, 없으면 env, default 20k.
                if qed_min_faces is not None:
                    _qed_min = int(qed_min_faces)
                else:
                    _qed_min = int(os.environ.get("AUTO_TESSELL_QED_MIN_F", "20000"))
                if _qed_env == "0":
                    _qed_on = False
                elif _qed_env == "1":
                    _qed_on = True
                else:  # "auto" 또는 미설정 — large input 자동 활성.
                    _qed_on = (F.shape[0] > _qed_min)
                if _qed_on and F.shape[0] > _qed_min:
                    from core.preprocessor.native_remesh.quadric_decimate import (
                        quadric_decimate,
                    )
                    _f_before = int(F.shape[0])
                    _v_before = int(V.shape[0])
                    _target = max(int(_f_before * 0.5), 200)
                    V_qed, F_qed = quadric_decimate(
                        V, F, target_n_faces=_target, max_iters=20000,
                    )
                    if (
                        F_qed.shape[0] > 50
                        and V_qed.shape[0] > 30
                        and F_qed.shape[0] < _f_before
                    ):
                        log.info(
                            "native_tet_qed_decimate",
                            v_before=_v_before, v_after=int(V_qed.shape[0]),
                            f_before=_f_before, f_after=int(F_qed.shape[0]),
                            target=_target,
                            mode=_qed_env,
                        )
                        V = V_qed.astype(np.float64)
                        F = F_qed.astype(np.int64)
            except Exception as exc:
                log.debug("native_tet_qed_decimate_skipped", reason=str(exc))

            # MM1 (beta1900) — hard self-intersect input 의 사전 isotropic remesh.
            # V > 500 + (boundary>0 또는 nonmanifold>0) 면 input 단순화로 sliver 격감.
            try:
                if (
                    aggressive
                    and V.shape[0] > 500
                    and F.shape[0] > 1000
                ):
                    from core.preprocessor.native_remesh import isotropic_remesh
                    # target_edge: 입력 평균 edge 의 ~ 1.2× — vertex 30-50% 감소 목표.
                    e0 = V[F[:, 0]]; e1 = V[F[:, 1]]; e2 = V[F[:, 2]]
                    elens = np.concatenate([
                        np.linalg.norm(e1 - e0, axis=1),
                        np.linalg.norm(e2 - e1, axis=1),
                        np.linalg.norm(e0 - e2, axis=1),
                    ])
                    h_avg = float(np.median(elens)) if elens.size else 0.0
                    if h_avg > 0:
                        h_target = h_avg * 1.5
                        V_rm, F_rm = isotropic_remesh(
                            V, F, target_edge_length=h_target,
                            n_iter=3, project_to_surface=True,
                            feature_angle_deg=45.0, lock_features=True,
                        )
                        if (
                            V_rm.shape[0] > 30
                            and F_rm.shape[0] > 50
                            and V_rm.shape[0] < V.shape[0]
                        ):
                            log.info(
                                "native_tet_hard_pre_remesh",
                                v_before=int(V.shape[0]),
                                v_after=int(V_rm.shape[0]),
                                f_before=int(F.shape[0]),
                                f_after=int(F_rm.shape[0]),
                                h_target=round(h_target, 5),
                            )
                            V = V_rm.astype(np.float64)
                            F = F_rm.astype(np.int64)
            except Exception as exc:
                log.debug("native_tet_hard_pre_remesh_skipped", reason=str(exc))

        if chk.warnings:
            log.warning(
                "native_tet_input_warnings",
                duplicate=chk.n_duplicate_vertices,
                zero_area=chk.n_zero_area_triangles,
                boundary_edges=chk.n_boundary_edges,
                nonmanifold=chk.n_nonmanifold_edges,
                warnings=chk.warnings,
            )
    except Exception as exc:
        log.debug("native_tet_input_check_skipped", reason=str(exc))

    # PRE1 (beta2127) — input sliver triangle merge (before BSP/Delaunay).
    try:
        from core.generator.native_tet.sliver_merge import (
            merge_sliver_triangles, _PRE1_ON,
        )
        if _PRE1_ON and F.shape[0] >= 100:
            _f_before = int(F.shape[0])
            V_pre1, F_pre1, n_merged = merge_sliver_triangles(V, F)
            if n_merged > 0:
                V = V_pre1.astype(np.float64)
                F = F_pre1.astype(np.int64)
                log.info(
                    "native_tet_sliver_merge",
                    n_merged=int(n_merged),
                    faces_before=_f_before,
                    faces_after=int(F.shape[0]),
                )
    except Exception as exc:
        log.debug("native_tet_sliver_merge_skipped", reason=str(exc))

    # PRE3 (beta2140) — input CVT isotropic remesh on high edge-length-ratio.
    # Botsch & Kobbelt 2004 isotropic remesh — gated by edge_length_ratio > 100
    # or n_faces > 200 000. Default ON; set AUTO_TESSELL_PRE3_OFF=1 to disable.
    import os as _os
    if not _os.environ.get("AUTO_TESSELL_PRE3_OFF") and F.shape[0] >= 100:
        try:
            _pre3_edges = np.concatenate([
                V[F[:, 0]] - V[F[:, 1]],
                V[F[:, 1]] - V[F[:, 2]],
                V[F[:, 2]] - V[F[:, 0]],
            ], axis=0)
            _pre3_lens = np.linalg.norm(_pre3_edges, axis=1)
            _pre3_lens = _pre3_lens[_pre3_lens > 0]
            _pre3_ratio = float(_pre3_lens.max() / _pre3_lens.min()) if len(_pre3_lens) > 0 else 0.0
            _pre3_nf = int(F.shape[0])
            if _pre3_ratio > 100.0 or _pre3_nf > 200_000:
                from core.preprocessor.native_remesh import isotropic_remesh
                _pre3_bmin = V.min(axis=0); _pre3_bmax = V.max(axis=0)
                _pre3_diag = float(np.linalg.norm(_pre3_bmax - _pre3_bmin))
                _pre3_target = _pre3_diag / 100.0
                V_pre3, F_pre3 = isotropic_remesh(V, F, target_edge_length=_pre3_target)
                # Guard: skip if remesh explodes face count (> 2× original) to
                # prevent tet recovery loop slowdown on already-dense inputs.
                if F_pre3.shape[0] > _pre3_nf * 2:
                    log.debug(
                        "native_tet_pre3_remesh_skipped_facecount",
                        faces_before=_pre3_nf,
                        faces_after=int(F_pre3.shape[0]),
                    )
                else:
                    V = V_pre3.astype(np.float64)
                    F = F_pre3.astype(np.int64)
                    log.info(
                        "native_tet_pre3_remesh",
                        edge_length_ratio=round(_pre3_ratio, 2),
                        faces_before=_pre3_nf,
                        faces_after=int(F.shape[0]),
                        target_edge_length=round(_pre3_target, 6),
                    )
        except Exception as _pre3_exc:
            log.warning("pre3_remesh_failed", reason=str(_pre3_exc))

    # beta77: large input guardrail — scipy.Delaunay 가 100k+ vertex 에서 OOM.
    cap = max(1, int(max_input_vertices))
    if V.shape[0] > cap:
        log.warning(
            "native_tet_input_too_large",
            n_vertices=V.shape[0], cap=cap,
            hint="max_input_vertices 늘리거나 표면 리메쉬로 decimation 권장",
        )
        return NativeTetResult(
            False, 0.0,
            message=(
                f"입력 mesh 가 너무 큽니다: {V.shape[0]} vertices > "
                f"max_input_vertices={cap}. "
                "표면 리메쉬(--force-remesh) 또는 max_input_vertices 상향 권장."
            ),
            n_self_intersect_pre=_pre_mesh_si_count,
        )

    bmin = V.min(axis=0); bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    if target_edge_length is None or target_edge_length <= 0:
        # beta330: target_cells 가 지정되면 bbox volume 기반 heuristic 으로
        # target_edge 유도. 정사면체 V ≈ edge^3 / (6√2) ≈ 0.118 × edge^3.
        if target_cells is not None and int(target_cells) > 0:
            span = (bmax - bmin).prod()
            if span > 0:
                # total_vol / (0.118 × edge^3) ≈ n_cells → edge = (vol / (0.118 × n))^(1/3).
                target_edge_length = float((span / (0.118 * int(target_cells))) ** (1.0 / 3.0))
            else:
                target_edge_length = diag / max(1, int(seed_density))
            log.info(
                "native_tet_target_cells_adjusted",
                target_cells=int(target_cells),
                derived_target_edge=target_edge_length,
            )
        else:
            # BETA2823 — wildmesh edge_length_r 정렬 모드 (env-gated, default OFF).
            # AUTO_TESSELL_NATIVE_WILDMESH_DENSITY=1 일 때 fTetWild 의
            # `edge_length_r × bbox_diag` 와 동일한 표준 격자 간격을 사용.
            _wm_align = os.environ.get("AUTO_TESSELL_NATIVE_WILDMESH_DENSITY", "0") == "1"
            if _wm_align:
                # 0.072 = grid-snap sweet spot (cube V/T count parity ~98%/84%).
                _r = float(os.environ.get("AUTO_TESSELL_NATIVE_EDGE_LENGTH_R", "0.072"))
                target_edge_length = max(1e-12, _r * diag)
                log.info(
                    "native_tet_wildmesh_density_align",
                    edge_length_r=_r, derived_target_edge=target_edge_length,
                )
            else:
                target_edge_length = diag / max(1, int(seed_density))

    # LL1 (beta1880) — 입력 V 가 작으면 셀 폭증 방지 위해 target_edge 키움.
    # 11k vertex 입력에서 156k tet 폭증 → mean_q 0.12 sliver. cell 수
    # ≈ V^1.25 정도가 fTetWild 비교 시 적절 (sliver 격감).
    # MM1 (beta1900) — exponent 1.4 → 1.25 (cells 9897 → ~3700 for V=664).
    try:
        nv = int(V.shape[0])
        if nv > 200:
            n_target = int(nv ** 1.25)
            span = (bmax - bmin).prod()
            if span > 0 and n_target > 0:
                te_cap = float((span / (0.118 * n_target)) ** (1.0 / 3.0))
                if te_cap > target_edge_length:
                    log.info(
                        "native_tet_target_edge_auto_tune",
                        prev=round(float(target_edge_length), 5),
                        new=round(te_cap, 5),
                        n_input_v=nv, n_target_cells=n_target,
                    )
                    target_edge_length = te_cap
    except Exception:
        pass

    # BETA2826 (B-1) — fTetWild-mode 자동 활성: wildmesh density alignment
    # 모드에선 BSP insertion + envelope-aware ops 강제 ON. 이미 사용자가 명시
    # 활성한 경우 그대로 유지.
    _ftetwild_mode = (
        os.environ.get("AUTO_TESSELL_NATIVE_FTETWILD_MODE", "0") == "1"
        or os.environ.get("AUTO_TESSELL_NATIVE_WILDMESH_DENSITY", "0") == "1"
    )
    if _ftetwild_mode:
        if not enable_bsp_insertion:
            enable_bsp_insertion = True
            log.info("native_tet_ftetwild_mode_bsp_force", source="env")

    log.info(
        "native_tet_start",
        n_surf_verts=V.shape[0], n_surf_faces=F.shape[0],
        bbox_diag=diag, target_edge_length=float(target_edge_length),
        ftetwild_mode=bool(_ftetwild_mode),
    )

    # 1) 시드 = 표면 vertex + 내부 uniform grid
    grid = _seed_points_uniform(bmin, bmax, float(target_edge_length))
    # grid 중 outside 제거 (아니면 bbox 밖으로 tet 이 많이 생김).
    # C-QUAL-5 / beta2392 — env AUTO_TESSELL_SEED_GWN=1 이면 Jacobson 2013
    # generalized winding number (SI-robust) 사용.
    # C-QUAL-6 / beta2394 — 자동 fallback: 입력에 self-intersect 검출 시
    # (_pre_mesh_si_count > 0) GWN 자동 활성. mesh #1 (V=3116, SI) 류
    # hard 케이스 자동 회복. env=0 강제 OFF, =1 강제 ON, 기타 (auto) 자동.
    if grid.shape[0] > 0:
        _gwn_env = os.environ.get("AUTO_TESSELL_SEED_GWN", "auto")
        _has_si = bool(_pre_mesh_si_count is not None and _pre_mesh_si_count > 0)
        if _gwn_env == "0":
            _use_gwn = False
        elif _gwn_env == "1":
            _use_gwn = True
        else:  # "auto" 또는 미설정 — SI 검출 시 자동 ON.
            _use_gwn = _has_si
        if _use_gwn:
            try:
                from core.utils.geometry import inside_generalized_winding_number
                inside_mask = inside_generalized_winding_number(grid, V, F)
                log.info(
                    "native_tet_seed_gwn_used",
                    component="native_tet", phase="beta2394",
                    n_grid=int(grid.shape[0]),
                    n_inside=int(inside_mask.sum()),
                    si_detected=_has_si,
                    mode=_gwn_env,
                )
            except Exception as _gwn_exc:
                log.debug("native_tet_seed_gwn_skipped", reason=str(_gwn_exc)[:120])
                inside_mask = _inside_winding_number(grid, V, F)
        else:
            inside_mask = _inside_winding_number(grid, V, F)
        grid = grid[inside_mask]

    all_pts = np.vstack([V, grid]) if grid.shape[0] else V.copy()

    # V2 (beta1580) — Steiner edge midpoint 사전 삽입.
    # 입력 F 의 각 edge midpoint 를 점으로 추가하면 Delaunay 결과 surface
    # face 분할이 입력과 더 일치한다 (chained CDT 회복률 ↑).
    if enable_edge_steiner and F.shape[0] > 0:
        try:
            from core.generator.native_tet.cdt_check import _tet_edges  # noqa
            surf_edges_set: set[tuple[int, int]] = _surf_edges_from_faces(F)
            extras: list[list[float]] = []
            n_per = max(1, int(edge_steiner_count))
            for (u, vv) in surf_edges_set:
                a = V[u]; b = V[vv]
                for k in range(1, n_per + 1):
                    t = k / (n_per + 1)
                    p = a + t * (b - a)
                    d = np.linalg.norm(all_pts - p, axis=1).min() \
                        if all_pts.shape[0] else 1.0
                    if d > 1e-7:
                        extras.append(p.tolist())
            if extras:
                all_pts = np.vstack(
                    [all_pts, np.asarray(extras, dtype=np.float64)],
                )
                log.info(
                    "native_tet_steiner_edges",
                    n_steiner=len(extras), n_surface_edges=len(surf_edges_set),
                )
        except Exception as exc:
            log.debug("native_tet_steiner_skipped", reason=str(exc))

    # CYLSKEW5 — bounded auto offset ring with cleaned raw-Delaunay proxies.
    _offset_ring_pts = np.zeros((0, 3), dtype=np.float64)
    _offset_mode, _offset_enabled = _offset_ring_mode(
        os.environ.get("AUTO_TESSELL_TET_OFFSET_RING"),
        int(V.shape[0]),
        int(F.shape[0]),
    )
    _decision = "disabled"
    off_metrics: dict[str, float] = {}
    on_metrics: dict[str, float] = {}
    off_raw = off_valid = on_raw = on_valid = 0
    if _offset_enabled:
        from core.generator.native_tet.offset_ring import (
            offset_ring_seed_points,
            select_offset_ring_variant,
        )

        _cand_pts, _or_info = offset_ring_seed_points(V, F, float(target_edge_length))
        log.info("native_tet_offset_ring", **_or_info)
        _decision = "no_candidates"
        if _cand_pts.shape[0]:
            try:
                from scipy.spatial import Delaunay as _RawDelaunay
                off_tri = _RawDelaunay(all_pts)
                on_pts = np.vstack([all_pts, _cand_pts])
                on_tri = _RawDelaunay(on_pts)
                off_metrics, off_raw, off_valid = _raw_proxy_metrics(
                    all_pts, off_tri.simplices,
                )
                on_metrics, on_raw, on_valid = _raw_proxy_metrics(
                    on_pts, on_tri.simplices,
                )
            except Exception as _proxy_exc:
                log.debug(
                    "native_tet_offset_ring_proxy_failed",
                    reason=str(_proxy_exc)[:120],
                )
            _offset_ring_pts, _sel_info = select_offset_ring_variant(
                _cand_pts, off_metrics, on_metrics,
            )
            _decision = str(_sel_info.get("decision"))
        if _offset_ring_pts.shape[0]:
            all_pts = np.vstack([all_pts, _offset_ring_pts])
    log.info(
        "native_tet_offset_ring_select",
        mode=_offset_mode,
        enabled=_offset_enabled,
        decision=_decision,
        off_raw_tets=off_raw,
        off_valid_tets=off_valid,
        on_raw_tets=on_raw,
        on_valid_tets=on_valid,
        off_skew=off_metrics.get("skew"),
        on_skew=on_metrics.get("skew"),
        off_nonortho=off_metrics.get("nonortho"),
        on_nonortho=on_metrics.get("nonortho"),
    )

    log.info("native_tet_seed", n_points=all_pts.shape[0], n_grid_inside=grid.shape[0])

    # 2) Delaunay (Phase A3: missing triangle 감지 후 시드 추가 재시도).
    n_surface = V.shape[0]
    extra_seeds = np.zeros((0, 3), dtype=np.float64)

    def _run_delaunay(seed_pts: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        # beta1360 (P5) — 임계 초과 시 chunked Delaunay 자동 사용.
        # C5 / beta2366 — AUTO_TESSELL_PARALLEL_DELAUNAY=1 + V > 30000 →
        # ProcessPoolExecutor 기반 multithreaded chunked.
        if (
            enable_chunked_delaunay
            and seed_pts.shape[0] > int(chunked_delaunay_threshold)
        ):
            # C5.2 / beta2375 — auto-detect: cpu_count >= 2 + seed > threshold
            # 시 자동 활성. env=0 강제 OFF, =1 강제 ON, 기타 (auto) 자동.
            _ppar_env = os.environ.get("AUTO_TESSELL_PARALLEL_DELAUNAY", "auto")
            if _ppar_env == "0":
                _use_parallel = False
            elif _ppar_env == "1":
                _use_parallel = True
            else:  # "auto" — cpu_count >= 2 면 자동 ON.
                _use_parallel = bool((os.cpu_count() or 1) >= 2)
            if _use_parallel:
                try:
                    from core.generator.native_tet.parallel import (
                        parallel_chunked_delaunay,
                    )
                    _, _tets, _pinfo = parallel_chunked_delaunay(
                        seed_pts, n_div=int(chunked_n_div), overlap_ratio=0.15,
                    )
                    log.info(
                        "native_tet_parallel_delaunay",
                        n_points=int(seed_pts.shape[0]),
                        n_chunks=int(_pinfo.n_chunks),
                        n_workers=int(_pinfo.n_workers),
                        n_tets=int(_tets.shape[0]),
                        elapsed=round(_pinfo.elapsed_s, 3),
                    )
                    if _tets.shape[0] > 0:
                        return seed_pts, _tets
                except Exception as _exc:
                    log.warning("native_tet_parallel_failed", error=str(_exc))
            try:
                from core.generator.native_tet.chunked import chunked_delaunay
                _, _tets, _info = chunked_delaunay(
                    seed_pts, n_div=int(chunked_n_div), overlap_ratio=0.15,
                )
                log.info(
                    "native_tet_chunked_delaunay",
                    n_points=int(seed_pts.shape[0]),
                    n_chunks=int(_info.n_chunks),
                    n_tets=int(_info.n_tets),
                    n_overlap=int(_info.n_overlap_filtered),
                    elapsed=round(_info.elapsed_s, 3),
                )
                if _tets.shape[0] > 0:
                    return seed_pts, _tets
            except Exception as _exc:
                log.warning("native_tet_chunked_failed", error=str(_exc))
        try:
            _dl = Delaunay(seed_pts)
        except Exception as _exc:
            log.warning("native_tet_delaunay_failed", error=str(_exc))
            return None
        _tets = np.asarray(_dl.simplices, dtype=np.int64)
        if _tets.shape[0] == 0:
            return None
        return seed_pts, _tets

    _prog("delaunay", 0.2, n_points=int(all_pts.shape[0]))
    dl_res = _run_delaunay(all_pts)
    if dl_res is None:
        return NativeTetResult(
            False, time.perf_counter() - t0, message="Delaunay 실패 또는 0 tet",
            n_self_intersect_pre=_pre_mesh_si_count,
        )
    all_pts, tets = dl_res
    _prog("delaunay_done", 0.3, n_tets=int(tets.shape[0]))

    # V8 (beta1570) — base Delaunay 의 surface plane area 보존. 마지막에
    # 이보다 떨어지면 fallback.
    base_pts_for_fallback = all_pts.copy()
    base_tets_for_fallback = tets.copy()
    try:
        from core.generator.native_tet.plane_coverage import (
            plane_coverage as _pc_base,
        )
        base_area_for_fallback = float(
            _pc_base(V, F, base_pts_for_fallback, base_tets_for_fallback).area_coverage
        )
    except Exception:
        base_area_for_fallback = -1.0

    if enable_phase_a and recovery_iterations > 0:
        from core.generator.native_tet.insertion import (
            find_missing_triangles, recovery_seeds,
        )

        for it in range(int(recovery_iterations)):
            rec = recovery_seeds(
                all_pts, F, tets,
                bump_distance=0.05 * float(target_edge_length),
                max_seeds=2000,
            )
            if rec.n_missing == 0:
                log.info(
                    "native_tet_recovery_complete",
                    iter=it, n_input=rec.n_input_triangles,
                )
                break
            log.info(
                "native_tet_recovery_iter",
                iter=it, n_missing=rec.n_missing,
                n_new_seeds=int(rec.extra_seeds.shape[0]),
            )
            if rec.extra_seeds.shape[0] == 0:
                break
            inside_new = _inside_winding_number(rec.extra_seeds, V, F)
            good = rec.extra_seeds[inside_new]
            if good.shape[0] == 0:
                break
            extra_seeds = np.vstack([extra_seeds, good])
            # Round 59 시도: B-W incremental — 큰 메시에서 per-point cavity
            # 스캔 O(T) 가 반복되어 느림 (harness 벤치 timeout). 반려 — full
            # re-Delaunay 유지 (scipy.Delaunay 는 C-level 이라 더 빠름).
            augmented = np.vstack([all_pts, good])
            dl_res2 = _run_delaunay(augmented)
            if dl_res2 is None:
                break
            all_pts, tets = dl_res2

        # beta1370+1430 — 통합 CDT recovery + outer iteration.
        if enable_cdt_recovery:
            try:
                from core.generator.native_tet.cdt_recovery import (
                    run_cdt_recovery,
                )
                from core.generator.native_tet.cdt_check import (
                    check_edge_recovery, cdt_ratio as _cdt_ratio_fn,
                )

                outer_iter = max(1, int(cdt_recovery_outer_iter))
                target_ratio = float(cdt_recovery_target_ratio)
                # C-PERF / dual_torus plateau-exit — profiling on the
                # high-genus dual_torus benchmark showed run_cdt_recovery
                # settling into inserted=0 / reverted=N repeats every outer
                # round once the (b) insertion-cycle sub-loop has hit a
                # structural wall (coplanar/unrecoverable wedges — see
                # tests/test_native_tet_dual_torus_limit.py). The existing
                # ratio-delta plateau check (below) doesn't catch this
                # because the (a) flip / (a2) cavity-retri pre-steps keep
                # nudging ratio up a little each round even while the
                # expensive (b) loop contributes nothing — so track
                # consecutive zero-insertion outer rounds independently and
                # bail out once the point-insertion mechanism itself has
                # plateaued, instead of burning the full outer_iter budget.
                _CDT_OUTER_PLATEAU_N = 3
                _cdt_consec_zero_insert = 0
                for outer_i in range(outer_iter):
                    cur_check = check_edge_recovery(F, tets)
                    cur_ratio = _cdt_ratio_fn(cur_check)
                    if cur_ratio >= target_ratio:
                        break
                    pts_new, tets_new, cdt_info = run_cdt_recovery(
                        all_pts, tets, V, F,
                        max_cycles=int(cdt_recovery_max_cycles),
                        points_budget=int(cdt_recovery_points_budget),
                        snap_final=False,
                    )
                    if (
                        cdt_info.ratio_after >= cdt_info.ratio_before
                        and tets_new.shape[0] > 0
                    ):
                        all_pts = pts_new
                        tets = tets_new
                        log.info(
                            "native_tet_cdt_recovery",
                            outer=outer_i,
                            cycles=cdt_info.cycles,
                            ratio_before=round(cdt_info.ratio_before, 3),
                            ratio_after=round(cdt_info.ratio_after, 3),
                            missing_before=cdt_info.n_edges_before,
                            missing_after=cdt_info.n_edges_after,
                            inserted=cdt_info.n_inserted_points,
                            reverted=cdt_info.reverted,
                            stage_seconds=cdt_info.stage_seconds,
                        )
                        if cdt_info.n_inserted_points == 0:
                            _cdt_consec_zero_insert += 1
                        else:
                            _cdt_consec_zero_insert = 0
                        if _cdt_consec_zero_insert >= _CDT_OUTER_PLATEAU_N:
                            log.info(
                                "native_tet_cdt_recovery_zero_insert_plateau_exit",
                                outer=outer_i,
                                consecutive_zero_insert=_cdt_consec_zero_insert,
                            )
                            break  # (b) 삽입 메커니즘이 N 회 연속 무의미 — 조기 종료.
                        if cdt_info.ratio_after - cdt_info.ratio_before < 1e-3:
                            break   # 더 이상 개선 안 됨.
                    else:
                        break
            except Exception as _exc:
                log.debug("native_tet_cdt_recovery_skipped", reason=str(_exc))

        # Round 50-51: iterative missing edge recovery (midpoint 삽입 + B-W).
        # Round 55: enable_edge_recovery=True 일 때만 (draft 성능 보호).
        _edge_recovery_snapshot: tuple[np.ndarray, np.ndarray] | None = None
        if enable_edge_recovery:
            _edge_recovery_snapshot = (all_pts.copy(), tets.copy())
            try:
                from core.generator.native_tet.cdt_check import check_edge_recovery
                from core.generator.native_tet.edge_recovery import propose_edge_midpoints
                from core.generator.native_tet.bowyer_watson import (
                    bowyer_watson_insert as _bw_edge,
                )

                cdt_initial = check_edge_recovery(F, tets)
                n_miss_initial = cdt_initial.n_missing
                cur_missing = cdt_initial.missing_edges
                total_inserted = 0
                # Round 58: 현재 tet edge set 중 surface edge 인 것은 보호.
                # recovered 된 surface edge 가 B-W cavity 로 다시 제거되지
                # 않도록 protected set 전달.
                surf_edges_all: set[tuple[int, int]] = _surf_edges_from_faces(F)
                for rec_i in range(int(edge_recovery_max_iter)):
                    if not cur_missing:
                        break
                    prop = propose_edge_midpoints(V, cur_missing, max_points=200)
                    if prop.new_points.shape[0] == 0:
                        break
                    inside_new = _inside_winding_number(prop.new_points, V, F)
                    good = prop.new_points[inside_new]
                    if good.shape[0] == 0:
                        good = prop.new_points
                    # 현재 tet 에 존재하는 surface edge (= 이미 recovered) 를 보호.
                    from core.generator.native_tet.cdt_check import _tet_edges

                    cur_tet_edges = _tet_edges(tets)
                    protected = surf_edges_all & cur_tet_edges
                    ap_new, ts_new, er_res = _bw_edge(
                        all_pts, tets, good,
                        protected_edges=protected,
                    )
                    if er_res.n_inserted == 0:
                        break
                    cdt_candidate = check_edge_recovery(F, ts_new)
                    if cdt_candidate.n_missing > len(cur_missing):
                        log.info(
                            "native_tet_edge_recovery_reverted",
                            iter=rec_i, before=len(cur_missing),
                            candidate_after=cdt_candidate.n_missing,
                        )
                        break
                    all_pts, tets = ap_new, ts_new
                    total_inserted += er_res.n_inserted
                    log.info(
                        "native_tet_edge_recovery_iter",
                        iter=rec_i, missing=cdt_candidate.n_missing,
                        inserted_this_iter=er_res.n_inserted,
                    )
                    if cdt_candidate.n_missing >= len(cur_missing):
                        break
                    cur_missing = cdt_candidate.missing_edges
                if total_inserted > 0:
                    cdt_final = check_edge_recovery(F, tets)
                    log.info(
                        "native_tet_edge_recovery_done",
                        missing_before=n_miss_initial,
                        missing_after=cdt_final.n_missing,
                        total_inserted=total_inserted,
                    )

                # Round 67-68: iterative targeted 2-3 flip (최대 3 패스).
                try:
                    from core.generator.native_tet.edge_flip_recovery import (
                        recover_edges_via_flip,
                    )

                    for _flip_pass in range(3):
                        cdt_now = check_edge_recovery(F, tets)
                        if cdt_now.n_missing == 0:
                            break
                        tets_flip, flip_res = recover_edges_via_flip(
                            all_pts, tets, cdt_now.missing_edges,
                            max_attempts=200,
                        )
                        if flip_res.n_edges_recovered == 0:
                            break
                        tets = tets_flip
                        cdt_after = check_edge_recovery(F, tets)
                        log.info(
                            "native_tet_edge_recovery_flip_iter",
                            pass_=_flip_pass,
                            recovered=flip_res.n_edges_recovered,
                            missing_after=cdt_after.n_missing,
                        )
                        if cdt_after.n_missing >= cdt_now.n_missing:
                            break
                except Exception as exc:
                    log.debug(
                        "native_tet_edge_recovery_flip_skipped", reason=str(exc),
                    )
            except Exception as exc:
                log.debug("native_tet_edge_recovery_skipped", reason=str(exc))

        # Diagnostic-only: separate edge-recovery boundary effects from the
        # later BSP insertion stage.  The snapshot is captured only for the
        # existing opt-in lane and never participates in acceptance.
        if _edge_recovery_snapshot is not None:
            try:
                from core.generator.native_tet.boundary_invariant import (
                    check_boundary_invariant,
                )

                edge_report = check_boundary_invariant(
                    _edge_recovery_snapshot[0],
                    _edge_recovery_snapshot[1],
                    all_pts,
                    tets,
                    "edge_recovery_before_to_after",
                    log_only=True,
                )
                log.info(
                    "native_tet_edge_recovery_boundary_snapshot",
                    preserved=edge_report.preserved,
                    before_boundary_faces=edge_report.before_face_count,
                    after_boundary_faces=edge_report.after_face_count,
                    before_boundary_area=round(edge_report.before_area, 12),
                    after_boundary_area=round(edge_report.after_area, 12),
                )
            except Exception as exc:
                log.debug(
                    "native_tet_edge_recovery_boundary_snapshot_skipped",
                    reason=str(exc),
                )

        # Phase F — BSP constrained insertion fallback.
        if enable_bsp_insertion:
            _bsp_batch_optin = os.environ.get(
                "AUTO_TESSELL_TET_BSP_BATCH", "0",
            ).strip().lower() in {"1", "true", "on", "yes"}
            if _bsp_batch_optin:
                from core.generator.native_tet.bsp_insert import (
                    bsp_insert_triangles_batch as _bsp_insert,
                )
            else:
                from core.generator.native_tet.bsp_insert import (
                    bsp_insert_triangles as _bsp_insert,
                )
            from core.generator.native_tet.bowyer_watson import bowyer_watson_insert

            remaining = find_missing_triangles(F, tets)
            if remaining.size > 0:
                def _nonpositive_tet_count(
                    candidate_pts: np.ndarray,
                    candidate_tets: np.ndarray,
                ) -> int:
                    from core.generator.native_tet.validate import signed_volume6

                    if candidate_tets.size == 0:
                        return 0
                    bbox_diag = float(
                        np.linalg.norm(
                            candidate_pts.max(axis=0) - candidate_pts.min(axis=0),
                        )
                    )
                    volume_tol = max(bbox_diag ** 3, 1.0) * 1e-14
                    volumes = signed_volume6(candidate_pts, candidate_tets)
                    return int(
                        (~np.isfinite(volumes) | (volumes <= volume_tol)).sum()
                    )

                bsp_base_nonpositive = _nonpositive_tet_count(all_pts, tets)
                log.info(
                    "native_tet_bsp_insert_start",
                    n_missing=int(remaining.size),
                    mode="batch" if _bsp_batch_optin else "scalar",
                )
                _bsp_insert_budget = int(
                    bsp_max_inserts_per_triangle
                ) * int(remaining.size)
                _bsp_budget_override = os.environ.get(
                    "AUTO_TESSELL_TET_BSP_MAX_POINTS",
                )
                if _bsp_budget_override:
                    try:
                        _bsp_insert_budget = min(
                            _bsp_insert_budget,
                            max(1, int(_bsp_budget_override)),
                        )
                    except ValueError:
                        pass
                log.info(
                    "native_tet_bsp_insert_budget",
                    max_inserts=int(_bsp_insert_budget),
                )
                # BSP 가 신규 점을 제안 (삽입 위치 계산).
                pts_with_new, _tets_after, bsp_res = _bsp_insert(
                    all_pts, tets, V, F, remaining,
                    max_inserts=_bsp_insert_budget,
                )
                if bsp_res.n_inserted_points > 0:
                    # 신규 점들만 추출해 Bowyer-Watson incremental insertion.
                    # beta480: full re-Delaunay 대신 B-W 로 O(K log T) 점진 삽입.
                    new_pts = pts_with_new[all_pts.shape[0]:]
                    all_pts_new, tets_new, bw_res = bowyer_watson_insert(
                        all_pts, tets, new_pts,
                    )
                    if bw_res.n_inserted > 0:
                        bsp_base_pts = all_pts
                        bsp_base_tets = tets
                        all_pts, tets = all_pts_new, tets_new
                        # Round 48: B-W 로 삽입된 신규 점을 입력 표면 BVH 로
                        # 한 번 snap — Hausdorff 오차 감소.
                        try:
                            from core.generator.native_tet.surface_snap import (
                                snap_surface_vertices,
                            )
                            from core.utils.aabb import TriangleBVH

                            n_before_bw = all_pts.shape[0] - bw_res.n_inserted
                            new_ids = np.arange(
                                n_before_bw, all_pts.shape[0], dtype=np.int64,
                            )
                            bvh_surf = TriangleBVH.build(V, F)
                            bbox_diag = float(
                                np.linalg.norm(V.max(axis=0) - V.min(axis=0))
                            )
                            snap_r = snap_surface_vertices(
                                all_pts, bvh_surf, new_ids,
                                max_distance=bbox_diag * 0.02,
                            )
                            log.info(
                                "native_tet_bw_post_snap",
                                snapped=snap_r.n_snapped,
                                max_disp=snap_r.max_displacement,
                            )
                        except Exception as exc:
                            log.debug(
                                "native_tet_bw_post_snap_skipped",
                                reason=str(exc),
                            )
                        from core.generator.native_tet.boundary_invariant import (
                            check_boundary_invariant,
                        )

                        bw_boundary = check_boundary_invariant(
                            bsp_base_pts,
                            bsp_base_tets,
                            all_pts,
                            tets,
                            "bsp_bowyer_watson_candidate",
                            log_only=True,
                        )
                        remaining_after = find_missing_triangles(F, tets)
                        bw_nonpositive = _nonpositive_tet_count(all_pts, tets)
                        if (
                            remaining_after.size >= remaining.size
                            or not bw_boundary.area_equal
                            or bw_nonpositive > bsp_base_nonpositive
                        ):
                            # A point insertion is not recovery by itself.  If
                            # the constrained-face census did not improve, or
                            # the candidate changed the physical boundary
                            # area, discard the whole BSP/B-W candidate,
                            # including any post-snap coordinates.
                            all_pts = bsp_base_pts
                            tets = bsp_base_tets
                            if remaining_after.size >= remaining.size:
                                reject_reason = "missing_faces_not_reduced"
                            elif not bw_boundary.area_equal:
                                reject_reason = "boundary_area_changed"
                            else:
                                reject_reason = "nonpositive_tets_increased"
                            log.warning(
                                "native_tet_bsp_bw_insert_rejected",
                                reason=reject_reason,
                                bsp_proposed_points=bsp_res.n_inserted_points,
                                bw_inserted=bw_res.n_inserted,
                                missing_before=int(remaining.size),
                                missing_after=int(remaining_after.size),
                                boundary_area_before=bw_boundary.before_area,
                                boundary_area_after=bw_boundary.after_area,
                                nonpositive_before=bsp_base_nonpositive,
                                nonpositive_after=bw_nonpositive,
                            )
                        else:
                            log.info(
                                "native_tet_bsp_bw_insert_done",
                                bsp_proposed_points=bsp_res.n_inserted_points,
                                bw_inserted=bw_res.n_inserted,
                                bw_cavity_total=bw_res.n_cavity_total,
                                missing_before=bsp_res.n_missing_before,
                                missing_after=int(remaining_after.size),
                                nonpositive_before=bsp_base_nonpositive,
                                nonpositive_after=bw_nonpositive,
                            )
                    else:
                        # B-W 실패 → full re-Delaunay fallback.
                        fallback_base_pts = all_pts
                        fallback_base_tets = tets
                        all_pts = pts_with_new
                        dl_res3 = _run_delaunay(all_pts)
                        if dl_res3 is not None:
                            candidate_pts, candidate_tets = dl_res3
                            from core.generator.native_tet.boundary_invariant import (
                                check_boundary_invariant,
                            )

                            fallback_boundary = check_boundary_invariant(
                                fallback_base_pts,
                                fallback_base_tets,
                                candidate_pts,
                                candidate_tets,
                                "bsp_redelaunay_candidate",
                                log_only=True,
                            )
                            fallback_missing = find_missing_triangles(
                                F, candidate_tets,
                            )
                            fallback_nonpositive = _nonpositive_tet_count(
                                candidate_pts, candidate_tets,
                            )
                            if (
                                fallback_missing.size < remaining.size
                                and fallback_boundary.area_equal
                                and fallback_nonpositive <= bsp_base_nonpositive
                            ):
                                all_pts, tets = candidate_pts, candidate_tets
                                log.info(
                                    "native_tet_bsp_insert_redelaunay_fallback",
                                    missing_before=int(remaining.size),
                                    missing_after=int(fallback_missing.size),
                                    nonpositive_before=bsp_base_nonpositive,
                                    nonpositive_after=fallback_nonpositive,
                                )
                            else:
                                all_pts = fallback_base_pts
                                tets = fallback_base_tets
                                log.warning(
                                    "native_tet_bsp_redelaunay_rejected",
                                    missing_before=int(remaining.size),
                                    missing_after=int(fallback_missing.size),
                                    boundary_area_before=fallback_boundary.before_area,
                                    boundary_area_after=fallback_boundary.after_area,
                                    nonpositive_before=bsp_base_nonpositive,
                                    nonpositive_after=fallback_nonpositive,
                                )
                        else:
                            all_pts = fallback_base_pts
                            tets = fallback_base_tets
                            log.warning("native_tet_bsp_redelaunay_failed")

    # 3) Classify final centroids against each original surface. Combined soup
    # remains the geometry source for bbox, seeding, and surface vertices.
    centroids = all_pts[tets].mean(axis=1)
    inside_tet: np.ndarray | None = None
    ordered_boolean_paths = boolean_input_paths or boolean_union_input_paths
    boolean_operation = str(boolean_operation).strip().lower()
    boundary_patch_classifier: Any | None = None
    boundary_patch_classifier_attempted = False

    def _get_boundary_patch_classifier() -> Any | None:
        nonlocal boundary_patch_classifier, boundary_patch_classifier_attempted
        if not ordered_boolean_paths or len(ordered_boolean_paths) < 2:
            return None
        if boundary_patch_classifier_attempted:
            return boundary_patch_classifier
        boundary_patch_classifier_attempted = True
        try:
            from core.utils.boundary_provenance import (
                SourceSurfacePatchClassifier,
            )

            boundary_patch_classifier = SourceSurfacePatchClassifier(
                list(ordered_boolean_paths)
            )
        except Exception as exc:
            log.warning(
                "native_tet_boundary_provenance_fallback",
                error=str(exc)[:160],
            )
        return boundary_patch_classifier

    def _classify_output_points(points: np.ndarray) -> np.ndarray:
        if ordered_boolean_paths:
            return _inside_boolean_inputs(
                points,
                list(ordered_boolean_paths),
                boolean_operation,
            )
        return _inside_winding_number(points, V, F)

    if ordered_boolean_paths:
        try:
            inside_tet = _classify_output_points(centroids)
            log.info(
                "native_tet_boolean_filter",
                operation=boolean_operation,
                n_inputs=len(ordered_boolean_paths),
                n_tets=int(tets.shape[0]),
                n_inside=int(inside_tet.sum()),
            )
        except Exception as exc:
            if boolean_operation != "union":
                message = (
                    f"boolean {boolean_operation} classification failed: {exc}"
                )
                log.warning(
                    "native_tet_boolean_filter_failed_closed",
                    operation=boolean_operation,
                    error=str(exc)[:160],
                )
                return NativeTetResult(
                    False,
                    time.perf_counter() - t0,
                    message=message,
                    n_self_intersect_pre=_pre_mesh_si_count,
                )
            log.warning(
                "native_tet_boolean_union_filter_fallback",
                error=str(exc)[:160],
            )
    if inside_tet is None:
        inside_tet = _inside_winding_number(centroids, V, F)

    # 3b) Phase A2 — boundary-aware sliver filter. V6 — surface-area revert.
    q_thresh = max(0.0, float(sliver_quality_threshold))
    if enable_phase_a:
        from core.generator.native_tet.filter import filter_slivers
        from core.generator.native_tet.plane_coverage import (
            plane_coverage as _pc_pre_filter,
        )

        # 사전 area (filter 전).
        try:
            prev_area_filter = float(
                _pc_pre_filter(V, F, all_pts, tets).area_coverage
            )
        except Exception:
            prev_area_filter = -1.0

        fr = filter_slivers(
            tets, all_pts, inside_tet,
            n_surface_vertices=n_surface,
            q_threshold_interior=q_thresh,
            q_threshold_boundary=max(0.0, q_thresh * 0.1),
            protect_boundary_faces=protect_boundary_faces,
        )
        keep_mask = fr.keep_mask

        # filter 적용 후 area 측정.
        try:
            new_area_filter = float(
                _pc_pre_filter(V, F, all_pts, tets[keep_mask]).area_coverage
            )
        except Exception:
            new_area_filter = prev_area_filter
        if (
            prev_area_filter > 0
            and new_area_filter + 0.05 < prev_area_filter
        ):
            log.warning(
                "native_tet_sliver_filter_revert",
                prev_area=round(prev_area_filter, 3),
                new_area=round(new_area_filter, 3),
                reason="filter_slivers 가 surface plane 깨뜨림",
            )
            # 보수: inside_tet 만 keep, sliver drop 안 함.
            keep_mask = inside_tet.copy()
        else:
            log.info(
                "native_tet_sliver_filter_phase_a",
                kept=int(keep_mask.sum()),
                dropped_total=fr.n_dropped,
                interior_dropped=fr.n_interior_dropped,
                boundary_protected=fr.n_boundary_protected,
                q_thresh_interior=fr.q_thresh_interior,
                q_thresh_boundary=fr.q_thresh_boundary,
            )
    else:
        # legacy: 일괄 q_thresh 적용.
        v = all_pts[tets]
        e01 = np.linalg.norm(v[:, 1] - v[:, 0], axis=1)
        e02 = np.linalg.norm(v[:, 2] - v[:, 0], axis=1)
        e03 = np.linalg.norm(v[:, 3] - v[:, 0], axis=1)
        e12 = np.linalg.norm(v[:, 2] - v[:, 1], axis=1)
        e13 = np.linalg.norm(v[:, 3] - v[:, 1], axis=1)
        e23 = np.linalg.norm(v[:, 3] - v[:, 2], axis=1)
        edge_max = np.maximum.reduce([e01, e02, e03, e12, e13, e23])
        vol6 = np.abs(
            np.einsum(
                "ij,ij->i",
                v[:, 1] - v[:, 0],
                np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
            )
        )
        safe = edge_max > 1e-30
        q = np.zeros_like(edge_max)
        q[safe] = (8.48 * (vol6[safe] / 6.0)) / (edge_max[safe] ** 3)
        keep_mask = inside_tet & (q >= q_thresh)
        log.info(
            "native_tet_sliver_filter",
            kept=int(keep_mask.sum()),
            dropped_sliver=int(inside_tet.sum() - keep_mask.sum()),
            q_threshold=q_thresh,
        )
    kept = tets[keep_mask]
    if kept.shape[0] == 0:
        return NativeTetResult(
            False, time.perf_counter() - t0,
            message="inside tet 0 — target_edge_length 조정 필요",
            n_self_intersect_pre=_pre_mesh_si_count,
        )

    # 4) 사용된 vertex 만 추출 + 인덱스 압축.
    #    v0.4.0-beta5: Hausdorff 보존을 위해 모든 surface vertex (V) 는 사용
    #    여부와 무관하게 최종 mesh 에 강제 포함.
    used_set = set(np.unique(kept.ravel()).tolist())
    surface_vert_ids = set(range(V.shape[0]))
    used_set |= surface_vert_ids
    used = np.array(sorted(used_set), dtype=np.int64)
    remap = -np.ones(all_pts.shape[0], dtype=np.int64)
    remap[used] = np.arange(used.shape[0])
    final_tets = remap[kept].astype(np.int64)
    final_pts = all_pts[used].copy()
    if _phase_a_observer is not None:
        _report_phase_a_provenance_checkpoint(
            _phase_a_observer, stage="post_filter_compaction",
            source_points=_input_source_vertices, source_faces=_input_source_faces,
            candidate_points=final_pts, candidate_tets=final_tets,
        )

    # BSP_ORIENT_FIX (beta2160) — front-load orientation normalize right after BSP
    # boundary recovery so ALL downstream post-passes work on correctly oriented tets.
    # R105 VAL3 showed ~562 neg-vol tets/fid baseline here; fix them before Phase A.
    _t_bsp = time.perf_counter()
    from core.generator.native_tet.stellar import validate_and_fix_orientations as _vaf_bsp  # noqa: PLC0415
    final_tets, _n_flipped_bsp, _n_degen_bsp = _vaf_bsp(final_pts, final_tets)
    log.info("native_tet_bsp_orient_fix", n_flipped=int(_n_flipped_bsp), n_degenerate=int(_n_degen_bsp))
    log.info("native_tet_pass_timing", pass_name="BSP_ORIENT_FIX", dt_ms=int((time.perf_counter() - _t_bsp) * 1000))
    if _phase_a_observer is not None:
        _report_phase_a_provenance_checkpoint(
            _phase_a_observer, stage="post_bsp_orient_fix",
            source_points=_input_source_vertices, source_faces=_input_source_faces,
            candidate_points=final_pts, candidate_tets=final_tets,
        )

    # 4b) Phase A1 + A4 — feature 잠금 + interior Laplacian smoothing.
    # Round 7: feature corner 를 실제 locked set 에 포함.
    feature_info = None
    corner_new_ids_array = np.zeros(0, dtype=np.int64)
    if enable_phase_a and smooth_iterations > 0:
        from core.generator.native_tet.features import detect_features
        from core.generator.native_tet.smooth import smooth_interior

        feature_info = detect_features(
            V, F, feature_angle_deg=float(feature_angle_deg),
        )
        surface_new_ids = remap[np.arange(n_surface)]
        surface_new_ids = surface_new_ids[surface_new_ids >= 0]
        locked_new: list[int] = surface_new_ids.tolist()

        # corner vertex (3+ feature edge 가 만나는 점) 의 new index 추출.
        # 이들은 surface 에 포함되지만 명시적으로 lock 해 smoothing tangent
        # 이동조차 금지.
        if feature_info.corner_vertices.size > 0:
            corner_new_ids = remap[feature_info.corner_vertices]
            corner_new_ids = corner_new_ids[corner_new_ids >= 0]
            corner_new_ids_array = corner_new_ids

        # V4 (beta1540) — smooth 가 surface plane 을 깨뜨리면 revert.
        prev_pts_smooth = final_pts.copy()
        try:
            from core.generator.native_tet.plane_coverage import (
                plane_coverage as _pc_pre,
            )
            prev_area_smooth = float(
                _pc_pre(V, F, final_pts, final_tets).area_coverage
            )
        except Exception:
            prev_area_smooth = -1.0

        sr = smooth_interior(
            final_pts, final_tets,
            locked_vertex_ids=np.asarray(locked_new, dtype=np.int64),
            n_iter=int(smooth_iterations),
            relax=float(smooth_relax),
        )

        try:
            new_area_smooth = float(
                _pc_pre(V, F, final_pts, final_tets).area_coverage
            )
        except Exception:
            new_area_smooth = prev_area_smooth
        if (
            prev_area_smooth > 0
            and new_area_smooth + 0.05 < prev_area_smooth
        ):
            log.warning(
                "native_tet_smooth_revert",
                prev_area=round(prev_area_smooth, 3),
                new_area=round(new_area_smooth, 3),
                reason="surface plane coverage 가 smooth 후 떨어짐",
            )
            final_pts = prev_pts_smooth
        log.info(
            "native_tet_smooth",
            n_iter=sr.n_iter,
            moved=sr.n_interior_moved,
            max_disp=sr.max_displacement,
            n_feature_edges=int(feature_info.feature_edges.shape[0]),
            n_corner=int(feature_info.corner_vertices.shape[0]),
            n_corner_new=int(corner_new_ids_array.size),
        )
    if _phase_a_observer is not None:
        _report_phase_a_provenance_checkpoint(
            _phase_a_observer, stage="post_phase_a_smoothing",
            source_points=_input_source_vertices, source_faces=_input_source_faces,
            candidate_points=final_pts, candidate_tets=final_tets,
        )

    # 4c) Phase B — local operations (split/collapse/flip) + tangent smoothing.
    # Phase C 가 켜져 있으면 envelope-guarded + quality stop 으로 승격.
    _prog("phase_a_done", 0.6, n_tets=int(final_tets.shape[0]))

    # P4-B-5 (beta2245) — Phase A mean_q < 임계 + P4-C fallback ON 시 Phase B/C 스킵.
    # extreme/hard tier 자가-impl 시도 무용 → bench time 큰 폭 단축.
    # env AUTO_TESSELL_PHASE_BC_SKIP_MQ (default 0.10) — 이 미만이면 skip.
    # env AUTO_TESSELL_PHASE_BC_SKIP=0 으로 완전 비활성 가능.
    _phase_bc_skip = False
    try:
        if (
            os.environ.get("AUTO_TESSELL_PHASE_BC_SKIP", "1") != "0"
            and os.environ.get("AUTO_TESSELL_P4C_PYTETWILD", "1") != "0"
            and final_tets.shape[0] > 0
        ):
            from core.generator.native_tet.quality import snapshot as _qsnap_pa
            _pa_q = _qsnap_pa(final_pts, final_tets)
            _pa_mean = float(getattr(_pa_q, "mean_q", 0.0))
            # 기본 0.18 — A grade 임계 0.20 직전. Phase A 가 0.18 미만이면 B/C 가
            # 0.20 도달할 가능성 낮음 (bench 19/20 fallback 케이스 중 0건). 보수적
            # 사용시 env 로 0.10 또는 0.05 로 낮추면 self-impl 우선.
            _skip_thresh = float(os.environ.get("AUTO_TESSELL_PHASE_BC_SKIP_MQ", "0.18"))
            if _pa_mean < _skip_thresh:
                _phase_bc_skip = True
                # Phase B/C 와 함께 후속 heavy 패스 (NNN/RRR/SSS/VVV3b~14) 도 스킵.
                # 어차피 P4-C 가 mesh 를 통째로 재생성하므로 의미 없음.
                _skip_envs = [
                    "AUTO_TESSELL_NNN1_DRYRUN",
                    "AUTO_TESSELL_NNN2_INSERT",
                    "AUTO_TESSELL_NNN3_INSERT",
                    "AUTO_TESSELL_NNN4_AMIPS",
                    "AUTO_TESSELL_RRR2_TARGETED",
                    "AUTO_TESSELL_P3_SSS_REVIVAL",
                    "AUTO_TESSELL_VVV2_QUEUE",
                    "AUTO_TESSELL_VVV5B_OFF",
                    "AUTO_TESSELL_VVV6_OFF",
                    "AUTO_TESSELL_VVV7_OFF",
                    "AUTO_TESSELL_VVV8_OFF",
                    "AUTO_TESSELL_VVV9_OFF",
                    "AUTO_TESSELL_VVV10_OFF",
                    "AUTO_TESSELL_VVV11_OFF",
                    "AUTO_TESSELL_VVV12_OFF",
                    "AUTO_TESSELL_VVV13_OFF",
                    "AUTO_TESSELL_VVV14_OFF",
                    "AUTO_TESSELL_TET_QUALITY1_OFF",
                ]
                # ON-by-default 패스 (env=0 으로 OFF) vs OFF-by-default (env=1 으로 OFF).
                _on_by_default = {
                    "AUTO_TESSELL_NNN1_DRYRUN", "AUTO_TESSELL_NNN2_INSERT",
                    "AUTO_TESSELL_NNN3_INSERT", "AUTO_TESSELL_NNN4_AMIPS",
                    "AUTO_TESSELL_RRR2_TARGETED",
                    "AUTO_TESSELL_P3_SSS_REVIVAL", "AUTO_TESSELL_VVV2_QUEUE",
                }
                _orig_env: dict[str, str | None] = {}
                for _k in _skip_envs:
                    _orig_env[_k] = os.environ.get(_k)
                    os.environ[_k] = "0" if _k in _on_by_default else "1"
                # 함수 종료 시점에 복원되어야 함 — try/finally 패턴 X (early return 없음)
                # 이므로 정상 흐름 후 P4-C 진입까지 그대로 유지.
                log.info(
                    "native_tet_phase_bc_skip",
                    phase_a_mean_q=round(_pa_mean, 4),
                    skip_thresh=round(_skip_thresh, 3),
                    n_tets=int(final_tets.shape[0]),
                    reason="below_threshold_p4c_fallback_will_rescue",
                    skipped_passes=len(_skip_envs),
                )
    except Exception as exc:
        log.debug("native_tet_phase_bc_skip_eval_failed", reason=str(exc))

    if enable_phase_b and local_ops_iterations > 0 and not _phase_bc_skip:
        from core.generator.native_tet.local_ops import (
            collapse_short_edges, compact_unused_vertices, split_long_edges,
        )
        from core.generator.native_tet.flip import face_flip_pass
        from core.generator.native_tet.smooth import (
            _vertex_normal_from_faces, smooth_tangent_surface,
        )

        # beta380 — 대형 메쉬 heuristic: tets > 20k 이면 iteration 과 flip 을
        # 1 로 강제 + tangent smoothing 도 1 회로. Python 루프 비용 폭증 방지.
        if final_tets.shape[0] > 20000:
            log.warning(
                "native_tet_phase_b_large_mesh",
                n_tets=int(final_tets.shape[0]),
                original_iter=int(local_ops_iterations),
                original_flip=int(flip_iterations),
            )
            local_ops_iterations = 1
            flip_iterations = 1
            tangent_smooth_iterations = min(1, int(tangent_smooth_iterations))

        surface_new_ids2 = remap[np.arange(n_surface)]
        surface_new_ids2 = surface_new_ids2[surface_new_ids2 >= 0]

        # anisotropic metric: surface vertex 에 curvature-aligned tensor 구성,
        # 내부 vertex 는 identity. split/collapse 에 metric kwarg 로 주입.
        metric_full: "np.ndarray | None" = None
        if use_anisotropic_metric:
            from core.generator.native_tet.anisotropic import curvature_aligned_metric

            surf_M = curvature_aligned_metric(
                V, F, base_edge=float(target_edge_length),
                aniso_ratio=float(anisotropic_ratio),
            )
            # final_pts 에 대해 metric 배열 구성 (surface new-index → surf_M,
            # interior → identity × 1/target_edge²).
            metric_full = np.zeros((final_pts.shape[0], 3, 3), dtype=np.float64)
            inv_e2 = 1.0 / (float(target_edge_length) ** 2)
            metric_full[:] = np.eye(3) * inv_e2
            _old_ids = np.arange(n_surface, dtype=np.int64)
            _new_ids = remap[_old_ids]
            _valid = (_new_ids >= 0) & (_new_ids < metric_full.shape[0])
            metric_full[_new_ids[_valid]] = surf_M[_old_ids[_valid]]
            log.info(
                "native_tet_anisotropic_metric",
                aniso_ratio=float(anisotropic_ratio),
            )

        # adaptive sizing: vertex 별 target 계산 후 split/collapse 에 사용할
        # scalar target 을 곡률 영향 받은 평균으로 조정.
        effective_target = float(target_edge_length)
        if use_adaptive_sizing:
            from core.generator.native_tet.adaptive import curvature_sizing

            per_v = curvature_sizing(
                V, F,
                target_edge=effective_target if enable_phase_b else float(target_edge_length),
                min_ratio=float(adaptive_min_ratio),
                max_ratio=float(adaptive_max_ratio),
                curvature_gain=float(adaptive_curvature_gain),
            )
            effective_target = float(per_v.mean())
            log.info(
                "native_tet_adaptive_sizing",
                base_target=float(target_edge_length),
                adaptive_mean=effective_target,
                adaptive_min=float(per_v.min()),
                adaptive_max=float(per_v.max()),
            )

        env = None
        q_hist: list = []
        if enable_phase_c:
            from core.generator.native_tet.envelope import Envelope, check_operation
            from core.generator.native_tet.quality import snapshot, should_stop
            from core.generator.native_tet.surface_snap import snap_surface_vertices

            env = Envelope.build(V, F, eps_relative=float(envelope_eps_relative))
            q_hist.append(snapshot(final_pts, final_tets))
            log.info(
                "native_tet_phase_c_init_quality",
                n_tets=q_hist[0].n_tets, min_q=q_hist[0].min_q,
                mean_q=q_hist[0].mean_q, max_aspect=q_hist[0].max_aspect,
                envelope_eps=env.eps,
            )

        for loop_idx in range(int(local_ops_iterations)):
            # 이전 상태 스냅샷 (envelope reject 시 복원용).
            prev_pts = final_pts.copy()
            prev_tets = final_tets.copy()

            # V7 (beta1590) — Phase B iteration 시작 시 surface area 캐시.
            try:
                from core.generator.native_tet.plane_coverage import (
                    plane_coverage as _pc_phb,
                )
                prev_area_phb = float(
                    _pc_phb(V, F, prev_pts, prev_tets).area_coverage
                )
            except Exception:
                prev_area_phb = -1.0

            # Round 66: split 에도 surface edge 보호.
            _split_surf_edges: set[tuple[int, int]] = _surf_edges_from_faces(F)
            # C1.4 / beta2372 — metric_full 활성 진단 (bench 에서 anisotropic
            # path 도달 검증용). 실 wiring 은 이미 존재 (metric=metric_full),
            # 이 로그는 propagation 가시성만 추가.
            if metric_full is not None and metric_full.shape[0] == final_pts.shape[0]:
                log.info(
                    "native_tet_metric_propagated",
                    component="native_tet", phase="beta2372",
                    n_vertices=int(metric_full.shape[0]),
                    target_path="split+collapse",
                )
            final_pts, final_tets, n_s = split_long_edges(
                final_pts, final_tets,
                target_edge=effective_target if enable_phase_b else float(target_edge_length),
                ratio=float(split_ratio),
                metric=metric_full,
                protected_edges=_split_surf_edges,
            )
            # metric_full 은 vertex 수 변경된 이후 길이가 안 맞을 수 있음 — size 다르면 None 처리.
            m_collapse = metric_full if (
                metric_full is not None
                and metric_full.shape[0] == final_pts.shape[0]
            ) else None
            # Round 64: 입력 surface edge 는 collapse 금지.
            _cur_surf_edges: set[tuple[int, int]] = _surf_edges_from_faces(F)
            final_pts, final_tets, n_c = collapse_short_edges(
                final_pts, final_tets,
                target_edge=effective_target if enable_phase_b else float(target_edge_length),
                ratio=float(collapse_ratio),
                locked_vertices=surface_new_ids2,
                max_collapses=int(max_collapses_per_iter),
                metric=m_collapse,
                protected_edges=_cur_surf_edges,
                # P2.1 / beta2311 — fine quality (enable_phase_c=True) 시
                # fTetWild §3.4 식 surface→interior collapse 활성. surface
                # 위치는 keeper guard 로 자동 보존, protected_edges 도 그대로
                # 유지 → safety net 2 중.
                allow_surface_keeper=bool(enable_phase_c),
            )
            # cell 수 급감 rollback: iteration 전 대비 급락하면 이전 상태로.
            if (
                prev_tets.shape[0] > 0
                and final_tets.shape[0] < prev_tets.shape[0] * float(cell_drop_rollback_ratio)
            ):
                log.warning(
                    "native_tet_phase_b_cell_drop_rollback",
                    iter=loop_idx,
                    before=int(prev_tets.shape[0]),
                    after=int(final_tets.shape[0]),
                    threshold=float(cell_drop_rollback_ratio),
                )
                final_pts = prev_pts
                final_tets = prev_tets
                break
            # Round 62/63: 입력 surface face + edge 를 protected set 으로
            # 전달해 2-3/3-2/4-4 flip 모두에서 제거되지 않도록.
            surf_face_set: set[tuple[int, int, int]] = _surf_faces_from_F(F)  # type: ignore[assignment]
            surf_edge_set: set[tuple[int, int]] = _surf_edges_from_faces(F)
            final_tets, fr2 = face_flip_pass(
                final_pts, final_tets,
                n_iter=int(flip_iterations),
                protected_faces=surf_face_set,
                protected_edges=surf_edge_set,
            )

            # V7 (beta1590) — Phase B iteration 후 surface area 검증.
            try:
                new_area_phb = float(
                    _pc_phb(V, F, final_pts, final_tets).area_coverage
                )
            except Exception:
                new_area_phb = prev_area_phb
            if (
                prev_area_phb > 0
                and new_area_phb + 0.05 < prev_area_phb
            ):
                log.warning(
                    "native_tet_phase_b_revert",
                    iter=loop_idx,
                    prev_area=round(prev_area_phb, 3),
                    new_area=round(new_area_phb, 3),
                )
                final_pts = prev_pts
                final_tets = prev_tets
                break

            # 사용 안 된 vertex 제거 (surface vertex 는 보호).
            before_pts = final_pts.shape[0]
            final_pts, final_tets = compact_unused_vertices(
                final_pts, final_tets, keep_first_n=int(n_surface),
            )
            # surface_new_ids2 는 [0, n_surface) 범위로 고정 유지됨.
            if final_pts.shape[0] != before_pts:
                log.info(
                    "native_tet_compact_orphans",
                    iter=loop_idx,
                    removed=int(before_pts - final_pts.shape[0]),
                )

            if env is not None and surface_new_ids2.size > 0:
                # D2: surface vertex 를 입력 표면 BVH 로 projection (drift 복원).
                snap_res = snap_surface_vertices(
                    final_pts, env.bvh, surface_new_ids2,
                    max_distance=env.eps * 2.0,
                    locked_vertex_ids=(
                        corner_new_ids_array if corner_new_ids_array.size else None
                    ),
                )
                log.info(
                    "native_tet_surface_snap",
                    iter=loop_idx, snapped=snap_res.n_snapped,
                    max_disp=snap_res.max_displacement,
                )
                ok, max_d = check_operation(env, final_pts[surface_new_ids2])
                if not ok:
                    # envelope 이탈 → 이전 상태로 복원.
                    final_pts = prev_pts
                    final_tets = prev_tets
                    log.warning(
                        "native_tet_phase_c_envelope_reject",
                        iter=loop_idx, max_surf_distance=max_d,
                        envelope_eps=env.eps,
                    )
                    break

            log.info(
                "native_tet_phase_b_iter",
                iter=loop_idx, splits=n_s, collapses=n_c,
                flips_23=fr2.n_flip_23,
                q_before=fr2.min_quality_before,
                q_after=fr2.min_quality_after,
            )

            if enable_phase_c:
                from core.generator.native_tet.quality import snapshot, should_stop

                q_hist.append(snapshot(final_pts, final_tets))
                stop, reason = should_stop(
                    q_hist,
                    target_min_q=float(quality_target_min_q),
                    improvement_eps=float(quality_improvement_eps),
                    window=int(quality_window),
                )
                if stop:
                    log.info(
                        "native_tet_phase_c_stop",
                        iter=loop_idx, reason=reason,
                        min_q=q_hist[-1].min_q,
                    )
                    break

            if n_s == 0 and n_c == 0 and fr2.n_flip_23 == 0:
                break

        # 4) tangent-plane surface smoothing.
        if tangent_smooth_iterations > 0 and surface_new_ids2.size > 0:
            # new index 공간에서 surface V/F 재구성.
            vn_old = _vertex_normal_from_faces(V, F)
            # remap 으로 new-index 기반 법선 재매핑.
            vn_new = np.zeros((final_pts.shape[0], 3), dtype=np.float64)
            _remap_oids = np.arange(n_surface, dtype=np.int64)
            _remap_nids = remap[_remap_oids]
            _remap_valid = (_remap_nids >= 0) & (_remap_nids < vn_new.shape[0])
            vn_new[_remap_nids[_remap_valid]] = vn_old[_remap_oids[_remap_valid]]
            srt = smooth_tangent_surface(
                final_pts, final_tets,
                surface_vertex_ids=surface_new_ids2,
                vertex_normals=vn_new,
                # Round 7: corner vertex 는 tangent smoothing 에서도 완전 고정.
                feature_locked_ids=corner_new_ids_array if corner_new_ids_array.size else None,
                n_iter=int(tangent_smooth_iterations),
                relax=float(tangent_smooth_relax),
            )
            log.info(
                "native_tet_tangent_smooth",
                n_iter=srt.n_iter, moved=srt.n_interior_moved,
                max_disp=srt.max_displacement,
            )

        # beta1350 — AMIPS energy-based interior smoothing (P2).
        # KK2 (beta1860) — hard mesh (mean_q < 0.15) 자동 감지 시 multistage.
        if enable_amips_smooth and final_tets.shape[0] > 0:
            try:
                from core.generator.native_tet.amips import (
                    smooth_amips, smooth_amips_multistage,
                )
                from core.generator.native_tet.quality import snapshot as _qsnap

                use_multistage = False
                _pre_mq = 0.0
                try:
                    pre_q = _qsnap(final_pts, final_tets)
                    _pre_mq = float(pre_q.mean_q)
                    if _pre_mq < 0.15:
                        use_multistage = True
                except Exception:
                    pass

                if use_multistage:
                    # C-QUAL-7 / beta2399 — 매우 낮은 quality (mq < 0.05) 에 대해
                    # alpha 4단계로 확장 (validator: hard mesh tet grade D, mq~0.05-0.1).
                    # 추가 (4.0) alpha pass 가 sliver 더 적극 처리.
                    if _pre_mq < 0.05:
                        _alphas = (0.5, 1.0, 2.0, 4.0)
                    else:
                        _alphas = (0.5, 1.0, 2.0)
                    ar, new_pts_amips = smooth_amips_multistage(
                        final_pts, final_tets,
                        locked_vertex_ids=surface_new_ids2,
                        alphas=_alphas,
                        n_iter_per=1,
                    )
                    log.info(
                        "native_tet_amips_multistage",
                        e_before=round(ar.energy_before, 3),
                        e_after=round(ar.energy_after, 3),
                        n_alphas=len(_alphas),
                        pre_mq=round(_pre_mq, 4),
                    )
                else:
                    ar, new_pts_amips = smooth_amips(
                        final_pts, final_tets,
                        locked_vertex_ids=surface_new_ids2,
                        n_iter=int(amips_iterations),
                        alpha=float(amips_alpha),
                    )
                # C-QUAL-9 / beta2404 — accept 조건 확장: energy 5% 악화 시
                # mq (별도 지표) 가 향상됐으면 채택. validator 발견: hard mesh
                # 의 grade D 가 AMIPS energy reverts 로 stuck. 둘 중 하나라도
                # 향상이면 accept (단조성 이중-criterion).
                _energy_ok = ar.energy_after <= ar.energy_before * 1.05
                _mq_ok = False
                if not _energy_ok:
                    try:
                        _post_q = _qsnap(new_pts_amips, final_tets)
                        _mq_ok = float(_post_q.mean_q) >= _pre_mq + 0.005
                    except Exception:
                        pass
                if _energy_ok or _mq_ok:
                    final_pts = new_pts_amips
                    log.info(
                        "native_tet_amips",
                        moved=ar.n_moved,
                        e_before=round(ar.energy_before, 3),
                        e_after=round(ar.energy_after, 3),
                        max_disp=round(ar.max_disp, 6),
                        accept_via=("energy" if _energy_ok else "mq"),
                    )
                else:
                    log.warning(
                        "native_tet_amips_revert",
                        e_before=round(ar.energy_before, 3),
                        e_after=round(ar.energy_after, 3),
                    )
            except Exception as exc:
                log.debug("native_tet_amips_skipped", reason=str(exc))

    # 4d) Round 10 — inverted tet 안전판 (local op 반복 후 numerical edge).
    # V4 (beta1540) — surface-aware swap revert: fix_inverted 후 plane_area
    # coverage 가 5%+ 떨어지면 swap 결과를 버린다 (inverted tet 그대로 둔다).
    # P4-B-5j: _phase_bc_skip 시 P4-C 가 mesh 통째 재생성 — fix_inverted 무의미.
    if enable_phase_a and not _phase_bc_skip:
        from core.generator.native_tet.validate import fix_inverted_tets

        prev_tets = final_tets.copy()
        try:
            from core.generator.native_tet.plane_coverage import plane_coverage as _pc

            prev_area = float(_pc(V, F, final_pts, prev_tets).area_coverage)
        except Exception:
            prev_area = -1.0

        final_tets, vr = fix_inverted_tets(final_pts, final_tets)

        # surface plane area 가 깨졌는지 확인.
        try:
            new_area = float(_pc(V, F, final_pts, final_tets).area_coverage)
        except Exception:
            new_area = prev_area
        if (
            prev_area > 0 and new_area >= 0
            and new_area + 0.05 < prev_area
        ):
            log.warning(
                "native_tet_validate_revert",
                prev_area=round(prev_area, 3),
                new_area=round(new_area, 3),
                reason="fix_inverted swap broke surface plane coverage",
            )
            final_tets = prev_tets
        elif vr.n_inverted_before > 0 or vr.n_degenerate > 0:
            log.info(
                "native_tet_validate",
                n_inverted=vr.n_inverted_before,
                fixed_by_swap=vr.n_fixed_by_swap,
                degenerate=vr.n_degenerate,
            )
    if _phase_a_observer is not None:
        _report_phase_a_provenance_checkpoint(
            _phase_a_observer,
            stage="post_phase_a_fix_inverted",
            source_points=_input_source_vertices,
            source_faces=_input_source_faces,
            candidate_points=final_pts,
            candidate_tets=final_tets,
        )

    # JJ3 (beta1820) — drop_extreme_slivers 전에 smooth_then_drop_slivers 호출
    # (drop 대신 주변 vertex 이동으로 sliver 회복 시도). hard mesh quality ↑.
    # P4-B-5e (beta2245e): _phase_bc_skip 시 후속 sliver 처리도 무의미 (P4-C 가 통째 재생성).
    if enable_phase_a and final_tets.shape[0] > 0 and not _phase_bc_skip:
        try:
            from core.generator.native_tet.plane_coverage import (
                _tet_boundary_faces,
            )
            from core.generator.native_tet.plane_coverage import (
                plane_coverage as _pc_jj3,
            )
            from core.generator.native_tet.validate import (
                smooth_then_drop_slivers,
            )

            # JJ3-lock (beta2823) — V.shape[0] 는 *입력 STL* 정점 수(cube: 8)이지
            # 메쉬의 표면 정점 수가 아니다.  BSP 삽입이 표면 위에 만든 정점은
            # lock 밖이라 Laplacian 이 이웃 무게중심(대부분 내부)쪽으로 끌어당겨
            # 표면을 함몰시켰다 (실측: median off-plane 0.0 -> 0.0319, 한 호출).
            # carve 직후 boundary vertex 는 입력 표면 위에 정확히 있으므로
            # (median off-plane = 0.0) 경계 정점 전체를 lock 하는 것은 근사가
            # 아니라 정확하다.  fTetWild §3.5 — smoothing 은 surface vertex 를
            # 입력 표면 밖으로 내보내지 않는다.
            n_surface_in = int(V.shape[0])
            _B = _tet_boundary_faces(final_tets)
            _bnd = np.unique(_B.ravel())
            locked_smooth = np.union1d(
                np.arange(min(n_surface_in, final_pts.shape[0]),
                          dtype=np.int64),
                _bnd.astype(np.int64),
            )

            prev_pts_jj3 = final_pts.copy()
            prev_tets_jj3 = final_tets.copy()
            try:
                prev_area_jj3 = float(
                    _pc_jj3(V, F, prev_pts_jj3, prev_tets_jj3).area_coverage
                )
            except Exception:
                prev_area_jj3 = -1.0

            new_pts, new_tets, n_moved, n_drop_jj = smooth_then_drop_slivers(
                final_pts, final_tets,
                locked_vertex_ids=locked_smooth,
                min_dihedral_deg=float(sliver_drop_min_dihedral_deg) * 0.5,
                min_aspect_regular=float(sliver_drop_max_aspect) * 1.5,
                n_smooth_iter=2, relax=0.25,
            )
            if new_tets.shape[0] >= final_tets.shape[0] * 0.9:
                # 셀 손실 10% 이내일 때만 채택.
                (
                    _jj3_selected_pts,
                    _jj3_selected_tets,
                    _jj3_sidedness_transaction,
                ) = _commit_sidedness_nonincreasing_candidate(
                    prev_pts_jj3,
                    prev_tets_jj3,
                    new_pts,
                    new_tets,
                )
                _smooth_then_drop_sidedness_transaction = {
                    **_jj3_sidedness_transaction,
                    "n_moved": int(n_moved),
                    "n_dropped": int(n_drop_jj),
                }
                if not _jj3_sidedness_transaction["accepted"]:
                    log.warning(
                        "native_tet_smooth_then_drop_sidedness_revert",
                        **_smooth_then_drop_sidedness_transaction,
                    )
                final_pts = _jj3_selected_pts
                final_tets = _jj3_selected_tets

                # 이웃 블록(1764-1799 / 1832-1870)과 동일한 surface-aware
                # revert guard.  lock 이 옳다면 0 회 발화한다.
                try:
                    new_area_jj3 = float(
                        _pc_jj3(V, F, final_pts, final_tets).area_coverage
                    )
                except Exception:
                    new_area_jj3 = prev_area_jj3
                if (
                    prev_area_jj3 > 0
                    and new_area_jj3 + 0.05 < prev_area_jj3
                ):
                    log.warning(
                        "native_tet_smooth_then_drop_revert",
                        prev_area=round(prev_area_jj3, 3),
                        new_area=round(new_area_jj3, 3),
                        reason="smoothing broke surface plane coverage",
                    )
                    final_pts = prev_pts_jj3
                    final_tets = prev_tets_jj3
                elif (
                    _jj3_sidedness_transaction["accepted"]
                    and (n_moved > 0 or n_drop_jj > 0)
                ):
                    log.info(
                        "native_tet_smooth_then_drop",
                        moved=int(n_moved), dropped=int(n_drop_jj),
                    )
        except Exception as exc:
            log.debug("native_tet_smooth_then_drop_skipped", reason=str(exc))
    if _phase_a_observer is not None:
        _report_phase_a_provenance_checkpoint(
            _phase_a_observer,
            stage="post_smooth_then_drop_slivers",
            source_points=_input_source_vertices,
            source_faces=_input_source_faces,
            candidate_points=final_pts,
            candidate_tets=final_tets,
        )

    # Round 73-74: extreme sliver 제거 (파라미터 노출). V5 — surface-aware revert.
    if enable_phase_a and not _phase_bc_skip:
        try:
            from core.generator.native_tet.validate import drop_extreme_slivers
            from core.generator.native_tet.plane_coverage import (
                plane_coverage as _pc_pre,
            )

            prev_tets_drop = final_tets.copy()
            try:
                prev_area_drop = float(
                    _pc_pre(V, F, final_pts, prev_tets_drop).area_coverage
                )
            except Exception:
                prev_area_drop = -1.0

            final_tets, n_drop = drop_extreme_slivers(
                final_pts, final_tets,
                min_dihedral_deg=float(sliver_drop_min_dihedral_deg),
                min_aspect_regular=float(sliver_drop_max_aspect),
            )

            try:
                new_area_drop = float(
                    _pc_pre(V, F, final_pts, final_tets).area_coverage
                )
            except Exception:
                new_area_drop = prev_area_drop
            if (
                prev_area_drop > 0
                and new_area_drop + 0.05 < prev_area_drop
            ):
                log.warning(
                    "native_tet_drop_slivers_revert",
                    prev_area=round(prev_area_drop, 3),
                    new_area=round(new_area_drop, 3),
                )
                final_tets = prev_tets_drop
            elif n_drop > 0:
                log.info("native_tet_drop_slivers", dropped=n_drop)
        except Exception as exc:
            log.debug("native_tet_drop_slivers_skipped", reason=str(exc))
    if _phase_a_observer is not None:
        _report_phase_a_provenance_checkpoint(
            _phase_a_observer,
            stage="post_drop_extreme_slivers",
            source_points=_input_source_vertices,
            source_faces=_input_source_faces,
            candidate_points=final_pts,
            candidate_tets=final_tets,
        )

    # BETA2825 — 축퇴 tet 위상보존 제거 (signed 3-2 flip + 공면 flap 제거).
    # non-skip 경로의 disk 메쉬 = 아래 line 의 write(final_pts/final_tets).
    # cube/draft 에서 이 지점에 축퇴 tet 50개(|det|/6<1e-9) → max_skew 1.7e29.
    # fTetWild §3.4 처럼 삭제 없이 위상보존 국소연산으로 제거 (Phase 2 만 공면
    # flap 한정 삭제 + extra_area/area_coverage revert 가드).
    if not _phase_bc_skip:
        try:
            from core.utils.predicates import orient3d as _o3d
            from core.generator.native_tet.validate import (
                signed_volume6 as _sv6,
            )
            from core.generator.native_tet.plane_coverage import (
                plane_coverage as _pc_deg,
                _triangle_planes_and_areas as _tpa_deg,
                _group_by_plane as _grp_deg,
            )

            _DEGEN_V6 = 6e-9  # |det|/6 < 1e-9  ⇔  |vol6| < 6e-9.
            _EPAIRS = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))

            n_degen_pre = int((np.abs(_sv6(final_pts, final_tets)) < _DEGEN_V6).sum())
            if n_degen_pre > 0:
                pre_pts = final_pts
                pre_tets = final_tets.copy()
                _pcr_pre = _pc_deg(V, F, final_pts, final_tets)
                extra_area_pre = float(_pcr_pre.extra_area)
                area_cov_pre = float(_pcr_pre.area_coverage)
                abs_vol_pre = float(np.abs(_sv6(pre_pts, pre_tets)).sum())

                work_tets = final_tets.copy().astype(np.int64)
                n_flip32 = 0

                # --- Phase 1: 부호기반 3-2 flip (위상보존, ∑|vol| 불변) ---
                for _sweep in range(6):
                    degen_mask = np.abs(_sv6(final_pts, work_tets)) < _DEGEN_V6
                    if not degen_mask.any():
                        break
                    edge_owners: dict[tuple[int, int], list[int]] = {}
                    degen_edges: set[tuple[int, int]] = set()
                    for ti in range(work_tets.shape[0]):
                        t = work_tets[ti]
                        is_dg = bool(degen_mask[ti])
                        for a, b in _EPAIRS:
                            i, j = int(t[a]), int(t[b])
                            e = (i, j) if i < j else (j, i)
                            edge_owners.setdefault(e, []).append(ti)
                            if is_dg:
                                degen_edges.add(e)
                    consumed: set[int] = set()
                    del_tets: set[int] = set()
                    new_rows: list[list[int]] = []
                    for (u, v) in degen_edges:
                        owners = edge_owners.get((u, v), [])
                        if len(owners) != 3 or any(o in consumed for o in owners):
                            continue
                        ring: list[int] = []
                        for o in owners:
                            for w in work_tets[o].tolist():
                                if w != u and w != v and w not in ring:
                                    ring.append(int(w))
                        if len(ring) != 3:
                            continue
                        x, y, z = ring
                        su = _o3d(final_pts[x], final_pts[y], final_pts[z],
                                  final_pts[u], tol=_DEGEN_V6)
                        sv = _o3d(final_pts[x], final_pts[y], final_pts[z],
                                  final_pts[v], tol=_DEGEN_V6)
                        # 분리삼각형: xyz 평면이 u,v 를 반대편으로 분리 (둘 다 비공면).
                        if su == 0 or sv == 0 or su == sv:
                            continue
                        fixed: list[list[int]] = []
                        ok = True
                        for row in ([x, y, z, u], [x, y, z, v]):
                            vol6 = float(_sv6(
                                final_pts, np.asarray([row], dtype=np.int64))[0])
                            if vol6 < 0:
                                row = [row[0], row[1], row[3], row[2]]
                                vol6 = -vol6
                            if vol6 <= _DEGEN_V6:
                                ok = False
                                break
                            fixed.append(row)
                        if not ok:
                            continue
                        for o in owners:
                            consumed.add(o)
                            del_tets.add(o)
                        new_rows.extend(fixed)
                        n_flip32 += 1
                    if not del_tets:
                        break
                    keep = np.ones(work_tets.shape[0], dtype=bool)
                    keep[list(del_tets)] = False
                    if new_rows:
                        work_tets = np.vstack([
                            work_tets[keep],
                            np.asarray(new_rows, dtype=np.int64),
                        ])
                    else:
                        work_tets = work_tets[keep]

                # --- Phase 1b: interior-incident edge-collapse (THINSLIVER1)
                # flip 불가(owners!=3 또는 su==sv) 잔존 슬리버 제거. victim=
                # non-surface interior 정점만, keeper=상대 끝점(위치 불변). ---
                n_collapse1b = 0
                n_surf_1b = int(min(V.shape[0], final_pts.shape[0]))
                surf_set: set[int] = set(range(n_surf_1b))
                degen_1b = np.abs(_sv6(final_pts, work_tets)) < _DEGEN_V6
                if degen_1b.any():
                    v2t_1b: dict[int, list[int]] = {}
                    for ti in range(work_tets.shape[0]):
                        for w in work_tets[ti].tolist():
                            v2t_1b.setdefault(int(w), []).append(ti)
                    consumed_v: set[int] = set()
                    dead_1b: set[int] = set()
                    for ti in np.nonzero(degen_1b)[0].tolist():
                        if ti in dead_1b:
                            continue
                        # 최단 edge 우선(플랜 실측: 14/17 이 최단 edge 에
                        # interior 끝점 보유 → 국소적(짧은) collapse 만 안전).
                        t = work_tets[ti].tolist()
                        cand: list[tuple[float, int, int]] = []
                        for a, b in _EPAIRS:
                            i, j = int(t[a]), int(t[b])
                            elen = float(np.linalg.norm(
                                final_pts[i] - final_pts[j]))
                            if i not in surf_set and i not in consumed_v:
                                cand.append((elen, i, j))
                            if j not in surf_set and j not in consumed_v:
                                cand.append((elen, j, i))
                        victim = keeper = -1
                        if cand:
                            cand.sort(key=lambda e: e[0])
                            _, victim, keeper = cand[0]
                        if victim < 0:
                            continue
                        star = [o for o in set(v2t_1b.get(victim, []))
                                if o not in dead_1b]
                        if not star:
                            continue
                        # orientation guard: 각 생존 tet 이 collapse 전후로
                        # 부호를 바꾸지 않고(inversion 없음) |vol6| 문턱을
                        # 넘는지 확인 (star 내 tet 들은 write-time winding
                        # normalize 이전이라 서로 다른 부호가 정상이므로,
                        # star 공통부호가 아닌 tet-별 pre/post 부호를 비교).
                        rewritten: list[tuple[int, list[int]]] = []
                        ok = True
                        for o in star:
                            orig_row = work_tets[o].tolist()
                            row = [keeper if w == victim else w
                                   for w in orig_row]
                            if len(set(row)) < 4:
                                continue  # collapsed edge 를 품은 tet → 소멸
                            vol6_pre = float(_sv6(
                                final_pts,
                                np.asarray([orig_row], dtype=np.int64))[0])
                            vol6 = float(_sv6(
                                final_pts, np.asarray([row], dtype=np.int64))[0])
                            if abs(vol6) <= _DEGEN_V6 or (
                                (vol6 > 0) != (vol6_pre >= 0)
                            ):
                                ok = False
                                break
                            rewritten.append((o, row))
                        if not ok:
                            continue
                        kept_ids = {o for o, _ in rewritten}
                        for o, row in rewritten:
                            work_tets[o] = row
                        for o in star:
                            if o not in kept_ids:
                                dead_1b.add(o)
                        consumed_v.add(victim)
                        consumed_v.add(keeper)
                        n_collapse1b += 1
                    if dead_1b:
                        keep1b = np.ones(work_tets.shape[0], dtype=bool)
                        keep1b[list(dead_1b)] = False
                        work_tets = work_tets[keep1b]

                # --- Phase 2: 입력면 평면과 공면인 flap 제거 (부피변화 0, void 0) ---
                n_flap = 0
                degen_b = np.abs(_sv6(final_pts, work_tets)) < _DEGEN_V6
                if degen_b.any():
                    bbox_diag = float(np.linalg.norm(
                        V.max(axis=0) - V.min(axis=0))) + 1e-30
                    in_unit, in_off, _ = _tpa_deg(V, F)
                    groups = _grp_deg(
                        in_unit, in_off, bbox_diag=bbox_diag,
                        normal_tol=5e-2, offset_rel_tol=5e-3,
                    )
                    planes: list[tuple[np.ndarray, float]] = [
                        (in_unit[ix[0]], float(in_off[ix[0]]))
                        for ix in groups.values()
                    ]
                    tol_plane = 1e-6 * bbox_diag
                    keep2 = np.ones(work_tets.shape[0], dtype=bool)
                    for ti in np.nonzero(degen_b)[0].tolist():
                        P = final_pts[work_tets[ti]]
                        for (nrm, off) in planes:
                            if float(np.abs(P @ nrm - off).max()) <= tol_plane:
                                keep2[ti] = False
                                n_flap += 1
                                break
                    if not keep2.all():
                        work_tets = work_tets[keep2]

                # --- 단조 가드: extra_area 비증가 AND area_coverage 비감소 ---
                n_degen_post = int((np.abs(_sv6(final_pts, work_tets))
                                    < _DEGEN_V6).sum())
                _pcr_post = _pc_deg(V, F, final_pts, work_tets)
                extra_area_post = float(_pcr_post.extra_area)
                area_cov_post = float(_pcr_post.area_coverage)
                abs_vol_post = float(np.abs(_sv6(final_pts, work_tets)).sum())
                if (
                    extra_area_post > extra_area_pre + 1e-6
                    or area_cov_post < area_cov_pre - 1e-3
                    or abs_vol_post < abs_vol_pre * 0.999
                ):
                    final_pts, final_tets = pre_pts, pre_tets
                    log.warning(
                        "native_tet_degenerate_removal_revert",
                        extra_area_pre=round(extra_area_pre, 6),
                        extra_area_post=round(extra_area_post, 6),
                        area_cov_pre=round(area_cov_pre, 4),
                        area_cov_post=round(area_cov_post, 4),
                        abs_vol_pre=round(abs_vol_pre, 9),
                        abs_vol_post=round(abs_vol_post, 9),
                    )
                else:
                    (
                        final_pts,
                        final_tets,
                        _degenerate_removal_source_transaction,
                    ) = _commit_degenerate_removal_source_candidate(
                        _input_source_vertices,
                        _input_source_faces,
                        pre_pts,
                        pre_tets,
                        final_pts,
                        work_tets,
                    )
                    if not _degenerate_removal_source_transaction["accepted"]:
                        log.warning(
                            "native_tet_degenerate_removal_source_revert",
                            **_degenerate_removal_source_transaction,
                        )
                    else:
                        log.info(
                            "native_tet_degenerate_removal",
                            n_flip32=int(n_flip32), n_flap=int(n_flap),
                            n_collapse1b=int(n_collapse1b),
                            n_degen_pre=int(n_degen_pre),
                            n_degen_post=int(n_degen_post),
                        )
        except Exception as exc:
            log.debug("native_tet_degenerate_removal_skipped", reason=str(exc))
    if _phase_a_observer is not None:
        _report_phase_a_provenance_checkpoint(
            _phase_a_observer,
            stage="post_degenerate_removal",
            source_points=_input_source_vertices,
            source_faces=_input_source_faces,
            candidate_points=final_pts,
            candidate_tets=final_tets,
        )

    # BETA2826 — surface-locked AMIPS smooth, disk-write 직전 (pre-write Stage-4).
    # P4C=0 경로에서 sweep/post-write AMIPS 는 아래 write *이후* 실행되어
    # in-memory 만 바꾸고 버려진다. 4-op 중 smooth 만 inversion-safe
    # (amips.py:336 per-vertex det>0 가드) 이므로, 모든 경계(표면) 정점을
    # lock 한 채 write 직전에 단독 적용해 disk 에 반영한다. split/flip 은
    # abs(vol6) 검사 잠복버그로 inversion 을 주입하므로 여기선 쓰지 않는다.
    # (계측 cube/draft/N2000/P4C0: skew 10.02→2.03, surf 이동 0.0, inv 0.)
    if not _phase_bc_skip and final_tets.shape[0] > 100:
        try:
            from core.generator.native_tet.amips import smooth_amips as _sm_bc
            from core.generator.native_tet.validate import (
                signed_volume6 as _sv6_bc,
            )
            from core.generator.native_tet.plane_coverage import (
                _tet_boundary_faces as _bf_bc,
            )

            _surf_ids = np.unique(_bf_bc(final_tets).ravel()).astype(np.int64)
            _pre_pts = final_pts.copy()
            _sv6_pre = _sv6_bc(final_pts, final_tets)
            _pre_abs = float(np.abs(_sv6_pre).sum())
            _, _new_pts = _sm_bc(
                final_pts, final_tets,
                locked_vertex_ids=_surf_ids, n_iter=5,
            )
            _sv6_new = _sv6_bc(_new_pts, final_tets)
            _vol_ratio = float(np.abs(_sv6_new).sum()) / max(_pre_abs, 1e-30)
            _surf_moved = float(
                np.abs(_new_pts[_surf_ids] - _pre_pts[_surf_ids]).max()
            ) if _surf_ids.size else 0.0
            # inversion 판정은 **전후 부호 비교** — 이 메쉬의 in-memory 정점
            # 순서는 균일 양수 방향이 아니다 (writer 가 write 시 winding 정규화;
            # validate 로그상 전 tet 이 "flipped" 인 경우도 정상). 절대 부호
            # (min>0) 를 요구하면 기존 음수-순서 tet 때문에 항상 revert 된다
            # — 실측: 14/14 호출 전부 revert, min_sv6=-0.0012 는 smooth 가
            # 만든 게 아니라 원래 있던 저장-순서 음수였다. 기하를 재라,
            # 장부를 재지 말고.
            _no_inv = bool(
                np.all(np.sign(_sv6_new) == np.sign(_sv6_pre))
                and np.all(np.abs(_sv6_new) > 1e-12)
            )
            # BETA2828 — evaluator-공식 skew 비악화 가드. smooth 는 이 블록 뒤
            # 곧바로 disk write → 여기 accept = 최종 판정 (하류 없음). interior
            # AMIPS 이동이 곡면 boundary 에서 skew 를 폭발시키면(cylinder) revert,
            # cube 처럼 개선하면 유지 → 방향-일치 monotone accept. topology
            # 불변이므로 _pre/_new 각각 동일 face-map 으로 평가한다.
            _sk_pre = _skew_proxy(_pre_pts, final_tets)
            _sk_post = _skew_proxy(_new_pts, final_tets)
            _accept = bool(
                _no_inv
                and 0.97 <= _vol_ratio <= 1.03
                and _surf_moved <= 1e-9
                and _sk_post <= _sk_pre * (1.0 + 1e-6)
            )
            if _accept:
                final_pts = _new_pts
            else:
                final_pts = _pre_pts
                log.warning(
                    "native_tet_prewrite_locked_smooth_revert",
                    n_surf=int(_surf_ids.shape[0]),
                    min_sv6=float(_sv6_new.min()),
                    vol_ratio=round(_vol_ratio, 6),
                    surf_moved=round(_surf_moved, 9),
                    sk_pre=round(_sk_pre, 4),
                    sk_post=round(_sk_post, 4),
                )
            log.info(
                "native_tet_prewrite_locked_smooth",
                n_surf=int(_surf_ids.shape[0]),
                vol_ratio=round(_vol_ratio, 6),
                surf_moved=round(_surf_moved, 9),
                sk_pre=round(_sk_pre, 4),
                sk_post=round(_sk_post, 4),
                accepted=_accept,
            )
        except Exception as exc:
            log.debug(
                "native_tet_prewrite_locked_smooth_skipped", reason=str(exc)
            )
    if _phase_a_observer is not None:
        _report_phase_a_provenance_checkpoint(
            _phase_a_observer,
            stage="post_prewrite_locked_smooth",
            source_points=_input_source_vertices,
            source_faces=_input_source_faces,
            candidate_points=final_pts,
            candidate_tets=final_tets,
        )

    # FSL3 — guarded 2-3 flip: flip-eligible all-surface flat sliver 제거,
    # write 직전 (BETA2826 locked-smooth 직후). 이중 가드(최종 mesh 기준):
    # skew proxy 비증가 + boundary-face count 불변이면 accept, 아니면 전량
    # revert(final_tets 유지).
    if not _phase_bc_skip and final_tets.shape[0] > 100:
        try:
            from core.generator.native_tet.validate import (
                apply_flat_sliver_23_flips as _fsl3_flip,
                count_boundary_faces as _fsl3_nbf,
            )

            _fsl3_pre_nbf = _fsl3_nbf(final_tets)
            _fsl3_sk_pre = _skew_proxy(final_pts, final_tets)
            _fsl3_cand, _fsl3_stats = _fsl3_flip(final_pts, final_tets, n_surface)
            _fsl3_accept = False
            if _fsl3_stats["n_flipped"] > 0:
                _fsl3_sk_post = _skew_proxy(final_pts, _fsl3_cand)
                _fsl3_accept = bool(
                    _fsl3_sk_post <= _fsl3_sk_pre * (1.0 + 1e-6)
                    and _fsl3_nbf(_fsl3_cand) == _fsl3_pre_nbf
                )
                if _fsl3_accept:
                    final_tets = _fsl3_cand
            log.info(
                "native_tet_fsl3_flip",
                n_eligible=int(_fsl3_stats["n_eligible"]),
                n_flipped=int(_fsl3_stats["n_flipped"]),
                n_reverted=int(_fsl3_stats["n_reverted"]),
                accepted=_fsl3_accept,
            )
        except Exception as exc:
            log.debug("native_tet_fsl3_flip_skipped", reason=str(exc))
    if _phase_a_observer is not None:
        _report_phase_a_provenance_checkpoint(
            _phase_a_observer,
            stage="post_fsl3_flip",
            source_points=_input_source_vertices,
            source_faces=_input_source_faces,
            candidate_points=final_pts,
            candidate_tets=final_tets,
        )

    # FSL Wave 1 (TET-LAZY-1 + TET-SHAPE-3(a)) -- Dassi 2018 lazy compound
    # flips (depth 1/2) then Ni 2017 / Shewchuk exhaustive multi-face
    # removal on FSL1's remaining core-unflippable coplanar wedges.
    # Default OFF (diagnostic-first card); fully transactional, so enabling
    # it never partially applies a fix -- see fsl_wave1.py docstring.
    if os.environ.get("AUTO_TESSELL_FSL_WAVE1", "0") == "1" and final_tets.shape[0] > 100:
        try:
            from core.generator.native_tet.fsl_wave1 import run_wave1_diagnostic

            final_tets, _fw1_report = run_wave1_diagnostic(final_pts, final_tets, n_surface)
            log.info(
                "native_tet_fsl_wave1",
                n_wedges=_fw1_report["n_wedges"],
                n_combinatorially_unlocked=_fw1_report["n_combinatorially_unlocked"],
                n_structurally_blocked=_fw1_report["n_structurally_blocked"],
                n_collateral_resolved=_fw1_report["n_collateral_resolved"],
                by_method=_fw1_report["by_method"],
            )
        except Exception as exc:
            log.debug("native_tet_fsl_wave1_skipped", reason=str(exc))

    # TET-FLOW-2 (Leng et al. 2013, Eqs. 3.13-3.16) -- penalized active-set
    # interior smoothing, the Phase 2 opening card. Interior vertices only:
    # boundary vertices stay bitwise identical, every vertex move is line-
    # searched (0.618 backtracking) under the exact Shewchuk orient3d
    # inversion guard, and the pass reverts whole on any guard failure, so
    # enabling it can never partially apply an edit -- see flow2.py docstring.
    # Default OFF pending broader shape coverage (FSL Wave 1 precedent).
    if os.environ.get("AUTO_TESSELL_TET_FLOW2", "0") == "1" and final_tets.shape[0] > 100:
        try:
            from core.generator.native_tet.flow2 import run_flow2_pass

            _f2_sweeps = int(os.environ.get("AUTO_TESSELL_TET_FLOW2_SWEEPS", "3"))
            _f2_pts, _f2_rep = run_flow2_pass(
                final_pts, final_tets, n_surface, n_sweeps=_f2_sweeps,
            )
            if _f2_rep["accepted"]:
                final_pts = _f2_pts
            log.info(
                "native_tet_flow2",
                accepted=_f2_rep["accepted"],
                reason=_f2_rep["reject_reason"],
                n_moved=_f2_rep["n_moved"],
                min_q_before=round(_f2_rep["min_q_canon_before"], 9),
                min_q_after=round(_f2_rep["min_q_canon_after"], 9),
                mean_q_before=round(_f2_rep["mean_q_canon_before"], 6),
                mean_q_after=round(_f2_rep["mean_q_canon_after"], 6),
                n_sliver_before=_f2_rep["n_sliver_before"],
                n_sliver_after=_f2_rep["n_sliver_after"],
                boundary_preserved=_f2_rep["boundary_preserved"],
            )
        except Exception as exc:
            log.debug("native_tet_flow2_skipped", reason=str(exc))

    # TET-SHAPE-2 (Ni et al. 2017) -- boundary-pinned interior GSM/AMIPS
    # smoothing.  The flag is deliberately default OFF until a caller opts
    # into the measured Phase-2 pass; the helper itself keeps all boundary,
    # exact-orientation, and strict quality-axis transactions.
    if (
        os.environ.get("AUTO_TESSELL_TET_SHAPE2", "0") == "1"
        and final_tets.shape[0] > 100
    ):
        try:
            from core.generator.native_tet.shape2 import run_shape2_pass

            _s2_weight = float(
                os.environ.get("AUTO_TESSELL_TET_SHAPE2_WEIGHT", "0.35")
            )
            _s2_sweeps = int(
                os.environ.get("AUTO_TESSELL_TET_SHAPE2_SWEEPS", "3")
            )
            _s2_pts, _s2_rep = run_shape2_pass(
                final_pts,
                final_tets,
                n_surface_vertices=n_surface,
                n_sweeps=_s2_sweeps,
                gsm_weight=_s2_weight,
            )
            if _s2_rep.accepted:
                final_pts = _s2_pts
            log.info(
                "native_tet_shape2",
                accepted=_s2_rep.accepted,
                reason=_s2_rep.reject_reason,
                n_moved=_s2_rep.n_moved,
                sigma_before=round(_s2_rep.sigma_dihedral_before, 8),
                sigma_after=round(_s2_rep.sigma_dihedral_after, 8),
                p10_before=round(_s2_rep.p10_q_before, 9),
                p10_after=round(_s2_rep.p10_q_after, 9),
                mean_before=round(_s2_rep.mean_q_before, 8),
                mean_after=round(_s2_rep.mean_q_after, 8),
                boundary_preserved=_s2_rep.boundary_preserved,
            )
        except Exception as exc:
            log.debug("native_tet_shape2_skipped", reason=str(exc))

    # Diagnostic-only dump for offline Wave-1 measurement scripts (never
    # runs in production; opt-in path + no default value so a stray/typo'd
    # env var can't silently write files).
    _fsl_dump_path = os.environ.get("AUTO_TESSELL_FSL_WAVE1_DUMP")
    if _fsl_dump_path:
        try:
            np.savez(_fsl_dump_path, pts=final_pts, tets=final_tets, n_surface=n_surface)
            log.debug("native_tet_fsl_wave1_dump_written", path=_fsl_dump_path)
        except Exception as exc:
            log.debug("native_tet_fsl_wave1_dump_failed", reason=str(exc))

    _prog("write", 0.9, n_tets=int(final_tets.shape[0]))

    # 5) polyMesh 쓰기.
    # W3 및 후단 품질 pass가 final_pts/final_tets를 바꿀 수 있으므로 중간
    # writer는 생략하고 FINAL-SYNC에서 정확히 한 번만 쓴다.  이로써 disk
    # mesh와 반환 배열의 source-of-truth가 갈라지는 구간도 제거된다.
    stats = {
        "num_cells": int(final_tets.shape[0]),
        "num_points": int(final_pts.shape[0]),
    }
    log.info(
        "native_tet_polymesh_write_deferred",
        reason="final_sync",
        n_tets=int(final_tets.shape[0]),
    )

    elapsed = time.perf_counter() - t0
    n_cells = int(stats.get("num_cells", final_tets.shape[0]))
    n_points = int(stats.get("num_points", final_pts.shape[0]))

    # Diagnostic-only anchor for the final-result contract audit.  The first
    # writer is the historical pre-W3 baseline; later local passes are checked
    # against it without changing acceptance or mesh state.
    _boundary_audit_anchor = (final_pts.copy(), final_tets.copy())

    def _boundary_audit_probe(stage_name: str) -> None:
        if _phase_a_observer is not None and stage_name in (
            "post_best_of",
            "post_nn1_collapse",
            "pre_rr1_flip",
            "post_rr1_flip",
            "pre_ddd1_bsp",
            "post_eee_quality",
        ):
            _report_phase_a_provenance_checkpoint(
                _phase_a_observer,
                stage=stage_name,
                source_points=_input_source_vertices,
                source_faces=_input_source_faces,
                candidate_points=final_pts,
                candidate_tets=final_tets,
            )
        try:
            from core.generator.native_tet.boundary_invariant import (
                check_boundary_invariant as _check_boundary_audit,
            )
            _boundary_audit_report = _check_boundary_audit(
                _boundary_audit_anchor[0], _boundary_audit_anchor[1],
                final_pts, final_tets, stage_name, log_only=True,
            )
            log.info(
                "native_tet_boundary_audit_probe",
                stage=stage_name,
                preserved=_boundary_audit_report.preserved,
                before_boundary_faces=_boundary_audit_report.before_face_count,
                after_boundary_faces=_boundary_audit_report.after_face_count,
            )
        except Exception as _boundary_audit_exc:
            log.debug(
                "native_tet_boundary_audit_probe_skipped",
                stage=stage_name,
                reason=str(_boundary_audit_exc)[:120],
            )

    # beta830: final quality snapshot.
    final_quality = None
    try:
        from core.generator.native_tet.quality import snapshot as _qsnap

        final_quality = _qsnap(final_pts, final_tets)
    except Exception:
        pass

    # W3 (beta1600) — Best-of-two: final vs base+inside 후보 중 점수 최대 채택.
    # 점수 = area*0.5 + cdt_chain*0.3 + mq*0.2 (단순 가중).
    try:
        if _phase_bc_skip:
            raise RuntimeError("_phase_bc_skip")
        if ordered_boolean_paths and boolean_operation != "union":
            raise RuntimeError(
                "non-union boolean keeps the operation-filtered primary candidate"
            )
        from core.generator.native_tet.cdt_check import (
            check_edge_recovery_chained, cdt_ratio as _cdt_ratio_w3,
        )
        from core.generator.native_tet.quality import snapshot as _qsnap_w3

        def _score(p_arr, t_arr):
            try:
                pc_v = float(_pc_base(V, F, p_arr, t_arr).area_coverage)
            except Exception:
                pc_v = 0.0
            try:
                cdt_v = float(_cdt_ratio_w3(check_edge_recovery_chained(V, F, p_arr, t_arr)))
            except Exception:
                cdt_v = 0.0
            try:
                snap = _qsnap_w3(p_arr, t_arr)
                mq_v = float(getattr(snap, "mean_q", 0.0))
            except Exception:
                mq_v = 0.0
            return (
                float(score_weight_area) * pc_v
                + float(score_weight_cdt) * cdt_v
                + float(score_weight_mq) * mq_v
            ), (pc_v, cdt_v, mq_v)

        final_score, final_metrics = _score(final_pts, final_tets)

        # 후보 1: base + inside winding filter (+ surface-vertex tet 강제 keep).
        base_centroids = base_pts_for_fallback[base_tets_for_fallback].mean(axis=1)
        base_inside = _classify_output_points(base_centroids)
        try:
            if not ordered_boolean_paths or boolean_operation == "union":
                n_surface_in = int(V.shape[0])
                on_surface = (base_tets_for_fallback < n_surface_in).all(axis=1)
                base_inside = base_inside | on_surface
        except Exception:
            pass
        base_filt_tets = base_tets_for_fallback[base_inside]
        base_score, base_metrics = _score(base_pts_for_fallback, base_filt_tets)

        # W2 (beta1620) — 후보 2: V-only Delaunay (입력 vertex 만 사용).
        v_only_score = -1.0
        v_only_pts = None
        v_only_tets = None
        try:
            from scipy.spatial import Delaunay as _D_v
            if V.shape[0] >= 4:
                Dv = _D_v(V)
                v_only_tets_raw = np.asarray(Dv.simplices, dtype=np.int64)
                v_cen = V[v_only_tets_raw].mean(axis=1)
                v_keep = _classify_output_points(v_cen)
                if not ordered_boolean_paths or boolean_operation == "union":
                    v_on_surf = (v_only_tets_raw < V.shape[0]).all(axis=1)
                    v_keep = v_keep | v_on_surf
                v_only_tets = v_only_tets_raw[v_keep]
                v_only_pts = V.copy()
                v_only_score, v_only_metrics = _score(v_only_pts, v_only_tets)
        except Exception:
            pass

        # W5 (beta1630) — V-only 후보 + interior point 추가 + quality smoothing.
        # cube/cyl 의 mean_q 0.22 → 0.30+ 향상으로 grade B → A 도달.
        v_only_smoothed_score = -1.0
        v_only_smoothed_pts = None
        v_only_smoothed_tets = None
        try:
            if v_only_pts is not None and v_only_tets is not None:
                # bbox 중심에 interior point 1개 추가 → re-Delaunay → smooth.
                bbox_min_v = V.min(axis=0)
                bbox_max_v = V.max(axis=0)
                center = 0.5 * (bbox_min_v + bbox_max_v)
                # 8 corner 중간 정점들 추가 (총 9 추가).
                ext_pts = [center.tolist()]
                for off in [
                    [0.4, 0, 0], [-0.4, 0, 0],
                    [0, 0.4, 0], [0, -0.4, 0],
                    [0, 0, 0.4], [0, 0, -0.4],
                ]:
                    p = center + np.asarray(off) * (bbox_max_v - bbox_min_v)
                    ext_pts.append(p.tolist())

                # OO1 (beta1920) — hard mesh (V > 500) 에 internal seed grid
                # 추가. surface vertex 비율 ↓ → 4-vertex sliver tet 격감.
                # n_internal ≈ V × 0.15 (예: V=11k → 1650 internal).
                try:
                    nv_in = int(V.shape[0])
                    if nv_in > 500:
                        # bbox 내부 균일 grid: edge-cube 분할.
                        n_internal_target = max(50, int(nv_in * 0.15))
                        # n^3 ≥ n_internal_target → n = ceil(cbrt).
                        n_axis = int(np.ceil(n_internal_target ** (1.0 / 3.0)))
                        # 0.05 ~ 0.95 range (boundary 회피).
                        ts = np.linspace(0.08, 0.92, n_axis)
                        gx, gy, gz = np.meshgrid(ts, ts, ts, indexing="ij")
                        grid_uvw = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
                        grid_pts = bbox_min_v + grid_uvw * (bbox_max_v - bbox_min_v)
                        # 작은 jitter 추가 (Delaunay degeneracy 회피).
                        rng = np.random.default_rng(42)
                        jitter = (rng.random(grid_pts.shape) - 0.5) * 1e-6 * float(np.linalg.norm(bbox_max_v - bbox_min_v))
                        grid_pts = grid_pts + jitter
                        ext_pts.extend(grid_pts.tolist())
                except Exception:
                    pass
                aug_pts = np.vstack([V, np.asarray(ext_pts)])
                # winding inside 한 점만 keep.
                inside_aug = _classify_output_points(aug_pts[V.shape[0]:])
                aug_pts = np.vstack([V, aug_pts[V.shape[0]:][inside_aug]])
                from scipy.spatial import Delaunay as _D_aug
                Daug = _D_aug(aug_pts)
                aug_tets_raw = np.asarray(Daug.simplices, dtype=np.int64)
                aug_cen = aug_pts[aug_tets_raw].mean(axis=1)
                aug_keep = _classify_output_points(aug_cen)
                if not ordered_boolean_paths or boolean_operation == "union":
                    aug_on_surf = (aug_tets_raw < V.shape[0]).all(axis=1)
                    aug_keep = aug_keep | aug_on_surf
                aug_tets = aug_tets_raw[aug_keep]

                # AMIPS analytic 으로 quality smoothing (interior 만).
                try:
                    from core.generator.native_tet.amips import (
                        smooth_amips_analytic,
                    )
                    locked_v = np.arange(V.shape[0], dtype=np.int64)
                    _, aug_pts_sm = smooth_amips_analytic(
                        aug_pts, aug_tets,
                        locked_vertex_ids=locked_v,
                        n_iter=3, alpha=1.0,
                    )
                    aug_pts = aug_pts_sm
                except Exception:
                    pass

                v_only_smoothed_pts = aug_pts
                v_only_smoothed_tets = aug_tets
                v_only_smoothed_score, _ = _score(aug_pts, aug_tets)
        except Exception:
            pass

        log.info(
            "native_tet_best_of_candidates",
            final_score=round(final_score, 3),
            final_metrics=tuple(round(x, 3) for x in final_metrics),
            base_score=round(base_score, 3),
            base_metrics=tuple(round(x, 3) for x in base_metrics),
            v_only_score=round(v_only_score, 3) if v_only_score >= 0 else -1,
        )

        # 3 후보 중 최고 score.
        def _candidate_meets_target_floor(t_arr: np.ndarray | None) -> bool:
            """Do not let a tiny V-only mesh mask a requested cell budget."""
            if t_arr is None:
                return False
            return _best_of_candidate_meets_target_floor(
                int(np.asarray(t_arr).shape[0]), target_cells
            )

        best_label = "final"
        best_score = final_score
        best_pts = final_pts
        best_tets = final_tets
        if (
            _candidate_meets_target_floor(base_filt_tets)
            and base_score > best_score + float(prefer_base_threshold)
        ):
            best_label = "base"
            best_score = base_score
            best_pts = base_pts_for_fallback
            best_tets = base_filt_tets
        if (
            _candidate_meets_target_floor(v_only_tets)
            and v_only_score > best_score + float(prefer_base_threshold)
        ):
            best_label = "v_only"
            best_score = v_only_score
            best_pts = v_only_pts
            best_tets = v_only_tets
        if (
            _candidate_meets_target_floor(v_only_smoothed_tets)
            and v_only_smoothed_score > best_score + float(prefer_base_threshold)
        ):
            best_label = "v_only_smoothed"
            best_score = v_only_smoothed_score
            best_pts = v_only_smoothed_pts
            best_tets = v_only_smoothed_tets

        if target_cells is not None:
            _target_floor = int(np.ceil(0.30 * max(0, int(target_cells))))
            for _label, _candidate in (
                ("final", final_tets),
                ("base", base_filt_tets),
                ("v_only", v_only_tets),
                ("v_only_smoothed", v_only_smoothed_tets),
            ):
                if _candidate is not None and int(np.asarray(_candidate).shape[0]) < _target_floor:
                    log.info(
                        "native_tet_best_of_candidate_rejected",
                        candidate=_label,
                        candidate_cells=int(np.asarray(_candidate).shape[0]),
                        target_cells=int(target_cells),
                        floor_cells=_target_floor,
                        reason="below_target_cell_floor",
                    )
            log.info(
                "native_tet_best_of_target_floor",
                target_cells=int(target_cells),
                floor_cells=_target_floor,
                final_cells=int(final_tets.shape[0]),
                base_cells=int(base_filt_tets.shape[0]),
                v_only_cells=(int(v_only_tets.shape[0])
                              if v_only_tets is not None else 0),
                v_only_smoothed_cells=(
                    int(v_only_smoothed_tets.shape[0])
                    if v_only_smoothed_tets is not None else 0
                ),
                picked=best_label,
            )

        if best_label != "final":
            log.warning(
                "native_tet_best_of_picks_alt",
                pick=best_label,
                score=round(best_score, 3),
                final_score=round(final_score, 3),
            )
            final_pts = best_pts
            final_tets = best_tets
    except Exception as exc:
        log.debug("native_tet_best_of_skipped", reason=str(exc))

    _boundary_audit_probe("post_best_of")

    # NN1 (beta1910) — sliver post-removal pass: 짧은 edge collapse 로
    # sliver tet 직접 제거. fTetWild §3.4 의 sliver removal 핵심 단계.
    # mean_q < 0.20 이면 1 회 적용. surface vertex lock.
    try:
        if _phase_bc_skip:
            raise RuntimeError("_phase_bc_skip")
        from core.generator.native_tet.quality import snapshot as _qsnap_pre
        pre_q = _qsnap_pre(final_pts, final_tets)
        # GAP1 / beta2767 — trigger 확장: mean_q < 0.30 또는 p10_q < 0.05.
        # 이전: mean_q < 0.20 만 → mean 정상이지만 worst tet 잔존하는 grade A
        # 실패 케이스 (sliver < 5%) 에서 collapse 미작동.
        # 신규: p10 (worst 10%) < 0.05 도 트리거 → sliver 적극 제거.
        # 단조 가드 (mean_q*0.99) 는 그대로 → 회귀 안전.
        _gap1_trigger = (
            float(pre_q.mean_q) < 0.30
            or float(pre_q.p10_q) < 0.05
        )
        if _gap1_trigger and final_tets.shape[0] > 100:
            from core.generator.native_tet.local_ops import collapse_short_edges
            n_v_pre = int(final_pts.shape[0])
            n_t_pre = int(final_tets.shape[0])
            # surface vertex lock — surface_new_ids2 가 일부 경로에서 미정의.
            try:
                lock_ids = surface_new_ids2  # type: ignore[name-defined]
            except NameError:
                # fallback: 입력 표면 vertex (V) 의 첫 n_surface_in 개 ID lock.
                lock_ids = np.arange(int(n_surface_in), dtype=np.int64)
            # YY1 (beta2000) — hard input (mq < 0.15) 일 땐 ratio 0.85 로
            # 더 적극적 collapse → sliver 더 격감.
            collapse_ratio = 0.85 if float(pre_q.mean_q) < 0.15 else 0.7
            # BETA2825 — wildmesh density alignment 모드에선 native 의 grid
            # over-density (셀 수 1.18× 초과) 를 줄이기 위해 ratio 0.95 로 escalate.
            # env AUTO_TESSELL_NATIVE_WILDMESH_DENSITY=1 인 경우만 발동.
            if os.environ.get("AUTO_TESSELL_NATIVE_WILDMESH_DENSITY", "0") == "1":
                collapse_ratio = float(
                    os.environ.get("AUTO_TESSELL_NATIVE_DENSITY_COLLAPSE_RATIO", "0.95")
                )
            new_pts, new_tets, n_c = collapse_short_edges(
                final_pts, final_tets,
                target_edge=float(target_edge_length),
                ratio=collapse_ratio,
                locked_vertices=lock_ids,
                max_collapses=4000,
                # P2.1 / beta2311 — hard input cleanup pass (mq < 0.15) 에서
                # surface→interior collapse 도 활성 (fTetWild §3.4 sliver 격감).
                allow_surface_keeper=bool(enable_phase_c),
            )
            if n_c > 0 and new_tets.shape[0] > 50:
                post_q = _qsnap_pre(new_pts, new_tets)
                # mean_q 가 단조 향상한 경우만 수용.
                if float(post_q.mean_q) > float(pre_q.mean_q) * 0.99:
                    final_pts = new_pts
                    final_tets = new_tets
                    log.info(
                        "native_tet_sliver_post_collapse",
                        n_collapsed=int(n_c),
                        v_before=n_v_pre, v_after=int(new_pts.shape[0]),
                        t_before=n_t_pre, t_after=int(new_tets.shape[0]),
                        mq_before=round(float(pre_q.mean_q), 3),
                        mq_after=round(float(post_q.mean_q), 3),
                    )
    except Exception as exc:
        log.debug("native_tet_sliver_post_skipped", reason=str(exc))

    _boundary_audit_probe("post_nn1_collapse")

    # P2.1 / beta2770 — Stellar Klingner edge-contract pass (sliver removal).
    # _klingner_edge_contract_candidates → _apply_klingner_edge_contract_topK
    # 이미 모듈 존재 (stellar.py:1514, 1615) but caller 없었음 (R196 dryrun gate).
    # 활성화: env AUTO_TESSELL_STELLAR_KLINGNER=1 (default ON in this card).
    # tet self-impl grade A 0/20 → +5/20 목표.
    # 단조 가드: _apply_klingner_edge_contract_topK 가 자체 revert 로직 보유.
    try:
        if _phase_bc_skip:
            raise RuntimeError("_phase_bc_skip")
        if os.environ.get("AUTO_TESSELL_STELLAR_KLINGNER", "1") != "0":
            from core.generator.native_tet.quality import snapshot as _qsnap_st
            pre_q_st = _qsnap_st(final_pts, final_tets)
            # 트리거: mean_q < 0.30 또는 min_q < 1e-4 (sliver 잔존).
            if (
                (float(pre_q_st.mean_q) < 0.30
                 or float(pre_q_st.min_q) < 1e-4)
                and final_tets.shape[0] > 100
            ):
                from core.generator.native_tet.stellar import (
                    _klingner_edge_contract_candidates,
                    _apply_klingner_edge_contract_topK,
                )
                cands = _klingner_edge_contract_candidates(
                    final_pts, final_tets,
                    q_max=0.10,
                    max_candidates=200,
                )
                if cands:
                    pts_st, tets_st, st_stats = _apply_klingner_edge_contract_topK(
                        final_pts, final_tets, cands, k=50,
                    )
                    if tets_st.shape[0] > 50:
                        post_q_st = _qsnap_st(pts_st, tets_st)
                        # global monotone: mean_q × 0.99 가드 (collapse 와 동일).
                        if (
                            float(post_q_st.mean_q)
                            >= float(pre_q_st.mean_q) * 0.99
                        ):
                            final_pts = pts_st
                            final_tets = tets_st
                            log.info(
                                "native_tet_p21_stellar_klingner",
                                n_applied=int(st_stats.get("n_applied", 0)),
                                n_reverted=int(st_stats.get("n_reverted", 0)),
                                mq_before=round(float(pre_q_st.mean_q), 4),
                                mq_after=round(float(post_q_st.mean_q), 4),
                                min_q_before=round(float(pre_q_st.min_q), 6),
                                min_q_after=round(float(post_q_st.min_q), 6),
                            )
    except Exception as exc:
        log.debug("native_tet_p21_stellar_skipped", reason=str(exc)[:200])

    _boundary_audit_probe("pre_rr1_flip")

    # RR1 (beta1950) — 2-3 face flip pass: connectivity-only sliver 깨기.
    # vertex 위치 변경 X (surface 보존), tet 재구성으로 min Q 향상.
    try:
        if _phase_bc_skip:
            raise RuntimeError("_phase_bc_skip")
        from core.generator.native_tet.quality import snapshot as _qsnap_flip
        pre_q_f = _qsnap_flip(final_pts, final_tets)
        if float(pre_q_f.mean_q) < 0.25 and final_tets.shape[0] > 100:
            from core.generator.native_tet.flip import (
                flip_faces_23, flip_edges_32, flip_edges_44,
            )
            t_before = int(final_tets.shape[0])
            # 2-3 face flip.
            new_tets_f, n_flips = flip_faces_23(
                final_pts, final_tets,
                min_quality_improvement=1e-3,
                max_flips=3000,
            )
            if n_flips > 0 and new_tets_f.shape[0] > 50:
                post_q_f = _qsnap_flip(final_pts, new_tets_f)
                if float(post_q_f.mean_q) >= float(pre_q_f.mean_q) * 0.99:
                    final_tets = new_tets_f
                    log.info(
                        "native_tet_flip_23",
                        n_flips=int(n_flips),
                        t_before=t_before, t_after=int(new_tets_f.shape[0]),
                        mq_before=round(float(pre_q_f.mean_q), 3),
                        mq_after=round(float(post_q_f.mean_q), 3),
                    )
            # SS1 (beta1960) — 3-2 edge flip pass: 추가 sliver 타입 깨기.
            try:
                pre_q_e = _qsnap_flip(final_pts, final_tets)
                t_pre_e = int(final_tets.shape[0])
                new_tets_e, n_e = flip_edges_32(
                    final_pts, final_tets,
                    min_quality_improvement=1e-3,
                    max_flips=2000,
                )
                if n_e > 0 and new_tets_e.shape[0] > 50:
                    post_q_e = _qsnap_flip(final_pts, new_tets_e)
                    if float(post_q_e.mean_q) >= float(pre_q_e.mean_q) * 0.99:
                        final_tets = new_tets_e
                        log.info(
                            "native_tet_flip_32",
                            n_flips=int(n_e),
                            t_before=t_pre_e, t_after=int(new_tets_e.shape[0]),
                            mq_before=round(float(pre_q_e.mean_q), 3),
                            mq_after=round(float(post_q_e.mean_q), 3),
                        )
            except Exception as exc:
                log.debug("native_tet_flip_32_skipped", reason=str(exc))
            # TT1 (beta1970) — 4-4 edge flip: 내부 edge ring 재배치.
            # P3.4 / beta2782 — adaptive threshold + multi-pass for self-impl A.
            # Klingner 2008 §4 4-4 swap 완전 적용: threshold 적응적 lowering
            # (1e-3 → 1e-5), 최대 5 pass. 각 pass 가 독립 flip 후보 발견.
            try:
                pre_q_44 = _qsnap_flip(final_pts, final_tets)
                t_pre_44 = int(final_tets.shape[0])
                _adaptive_thrs = (1e-3, 5e-4, 1e-4, 5e-5, 1e-5)
                _total_44 = 0
                cur_pts_44 = final_pts
                cur_tets_44 = final_tets
                cur_mq_44 = float(pre_q_44.mean_q)
                for _thr_44 in _adaptive_thrs:
                    new_tets_44, n_44 = flip_edges_44(
                        cur_pts_44, cur_tets_44,
                        min_quality_improvement=float(_thr_44),
                        max_flips=2000,
                    )
                    if n_44 == 0 or new_tets_44.shape[0] <= 50:
                        continue
                    post_q_44 = _qsnap_flip(cur_pts_44, new_tets_44)
                    if float(post_q_44.mean_q) >= cur_mq_44 * 0.99:
                        cur_tets_44 = new_tets_44
                        cur_mq_44 = float(post_q_44.mean_q)
                        _total_44 += int(n_44)
                if _total_44 > 0:
                    final_tets = cur_tets_44
                    log.info(
                        "native_tet_flip_44_adaptive",
                        n_flips=_total_44,
                        t_before=t_pre_44, t_after=int(final_tets.shape[0]),
                        mq_before=round(float(pre_q_44.mean_q), 4),
                        mq_after=round(cur_mq_44, 4),
                        adaptive_thr_min=_adaptive_thrs[-1],
                    )
            except Exception as exc:
                log.debug("native_tet_flip_44_skipped", reason=str(exc))

            # UU1 (beta1980) — 2nd flip cycle: 첫 cycle 의 잔여 sliver 를
            # 다시 노출시켜 추가 mq 향상. flip_23 → flip_32 1회 더.
            try:
                pre_q_c2 = _qsnap_flip(final_pts, final_tets)
                if float(pre_q_c2.mean_q) < 0.30:
                    new_tets_c2, n_c2 = flip_faces_23(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=2000,
                    )
                    if n_c2 > 0 and new_tets_c2.shape[0] > 50:
                        post_q_c2 = _qsnap_flip(final_pts, new_tets_c2)
                        if float(post_q_c2.mean_q) >= float(pre_q_c2.mean_q) * 0.99:
                            final_tets = new_tets_c2
                            log.info("native_tet_flip_23_c2", n_flips=int(n_c2),
                                     mq_before=round(float(pre_q_c2.mean_q), 3),
                                     mq_after=round(float(post_q_c2.mean_q), 3))
                    pre_q_c2b = _qsnap_flip(final_pts, final_tets)
                    new_tets_c2b, n_c2b = flip_edges_32(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1500,
                    )
                    if n_c2b > 0 and new_tets_c2b.shape[0] > 50:
                        post_q_c2b = _qsnap_flip(final_pts, new_tets_c2b)
                        if float(post_q_c2b.mean_q) >= float(pre_q_c2b.mean_q) * 0.99:
                            final_tets = new_tets_c2b
                            log.info("native_tet_flip_32_c2", n_flips=int(n_c2b),
                                     mq_before=round(float(pre_q_c2b.mean_q), 3),
                                     mq_after=round(float(post_q_c2b.mean_q), 3))
            except Exception as exc:
                log.debug("native_tet_flip_cycle2_skipped", reason=str(exc))

            # AAA1 (beta2020) — flip cycle 3: 추가 잔여 sliver 노출.
            try:
                pre_q_c3 = _qsnap_flip(final_pts, final_tets)
                if float(pre_q_c3.mean_q) < 0.30:
                    new_tets_c3, n_c3 = flip_faces_23(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1500,
                    )
                    if n_c3 > 0 and new_tets_c3.shape[0] > 50:
                        post_q_c3 = _qsnap_flip(final_pts, new_tets_c3)
                        if float(post_q_c3.mean_q) >= float(pre_q_c3.mean_q) * 0.99:
                            final_tets = new_tets_c3
                            log.info("native_tet_flip_23_c3", n_flips=int(n_c3),
                                     mq_before=round(float(pre_q_c3.mean_q), 3),
                                     mq_after=round(float(post_q_c3.mean_q), 3))
                    # BBB1 (beta2030) — cycle 3 의 flip_32 + cycle 2 의 flip_44.
                    pre_q_c3b = _qsnap_flip(final_pts, final_tets)
                    new_tets_c3b, n_c3b = flip_edges_32(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1000,
                    )
                    if n_c3b > 0 and new_tets_c3b.shape[0] > 50:
                        post_q_c3b = _qsnap_flip(final_pts, new_tets_c3b)
                        if float(post_q_c3b.mean_q) >= float(pre_q_c3b.mean_q) * 0.99:
                            final_tets = new_tets_c3b
                            log.info("native_tet_flip_32_c3", n_flips=int(n_c3b),
                                     mq_before=round(float(pre_q_c3b.mean_q), 3),
                                     mq_after=round(float(post_q_c3b.mean_q), 3))
                    pre_q_44b = _qsnap_flip(final_pts, final_tets)
                    new_tets_44b, n_44b = flip_edges_44(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1000,
                    )
                    if n_44b > 0 and new_tets_44b.shape[0] > 50:
                        post_q_44b = _qsnap_flip(final_pts, new_tets_44b)
                        if float(post_q_44b.mean_q) >= float(pre_q_44b.mean_q) * 0.99:
                            final_tets = new_tets_44b
                            log.info("native_tet_flip_44_c2", n_flips=int(n_44b),
                                     mq_before=round(float(pre_q_44b.mean_q), 3),
                                     mq_after=round(float(post_q_44b.mean_q), 3))
            except Exception as exc:
                log.debug("native_tet_flip_cycle3_skipped", reason=str(exc))

            # VV1 (beta1990) — flip 2-cycle 후 AMIPS interior smoothing 1 회
            # 더. sliver 깬 새 connectivity 에서 vertex 위치 미세 조정으로
            # mq 추가 향상.
            try:
                pre_q_v = _qsnap_flip(final_pts, final_tets)
                if float(pre_q_v.mean_q) < 0.30:
                    from core.generator.native_tet.amips import smooth_amips_analytic
                    try:
                        from core.generator.native_tet.plane_coverage import (
                            _tet_boundary_faces,
                        )
                        # surface_new_ids2 is based on the pre-pass remap.  At
                        # this point local flips/collapse may have changed the
                        # active boundary incidence, so lock the exact current
                        # boundary vertex set before AMIPS relocation.
                        lock_ids_v = np.unique(
                            _tet_boundary_faces(final_tets),
                        ).astype(np.int64)
                    except Exception:
                        lock_ids_v = np.arange(int(n_surface_in), dtype=np.int64)
                    ar_v, new_pts_v = smooth_amips_analytic(
                        final_pts, final_tets,
                        locked_vertex_ids=lock_ids_v,
                        n_iter=1, alpha=1.0,
                    )
                    if ar_v.energy_after <= ar_v.energy_before * 1.05:
                        post_q_v = _qsnap_flip(new_pts_v, final_tets)
                        if float(post_q_v.mean_q) >= float(pre_q_v.mean_q) * 0.99:
                            final_pts = new_pts_v
                            log.info("native_tet_amips_post_flip",
                                     mq_before=round(float(pre_q_v.mean_q), 3),
                                     mq_after=round(float(post_q_v.mean_q), 3))
            except Exception as exc:
                log.debug("native_tet_amips_post_flip_skipped", reason=str(exc))
    except Exception as exc:
        log.debug("native_tet_flip_23_skipped", reason=str(exc))

    _boundary_audit_probe("post_rr1_flip")

    _boundary_audit_probe("pre_ddd1_bsp")

    # DDD1 (beta2040) — BSP triangle insertion pass: missing surface triangle
    # 강제 회복. fTetWild §3.3 의 핵심 envelope 정합 단계.
    # missing_face_indices 직접 계산 (input F 중 final_tets 안에 없는 face).
    try:
        if _phase_bc_skip:
            raise RuntimeError("_phase_bc_skip")
        from core.generator.native_tet.bsp_insert import bsp_insert_triangles_batch as _bsp_batch
        from core.generator.native_tet.boundary_invariant import (
            check_boundary_invariant as _check_bsp_boundary,
        )
        from core.generator.native_tet.insertion import (
            find_missing_triangles as _find_missing_triangles,
        )
        # final_tets 의 모든 canonical face set.
        if final_tets.size > 0 and F.size > 0:
            tf = np.stack(
                [final_tets[:, [0, 1, 2]], final_tets[:, [0, 1, 3]],
                 final_tets[:, [0, 2, 3]], final_tets[:, [1, 2, 3]]], axis=1,
            ).reshape(-1, 3)
            tf = np.sort(tf, axis=1)
            tf_set = {(int(a), int(b), int(c)) for a, b, c in tf}
            # input F 의 triangle (input vertex indexing — final_pts 의 처음 n_surface_in 와 매칭).
            n_surf_v = min(int(n_surface_in), int(final_pts.shape[0]))
            Fs = np.sort(F, axis=1)
            _in_range = (Fs[:, 0] < n_surf_v) & (Fs[:, 1] < n_surf_v) & (Fs[:, 2] < n_surf_v)
            _cand_idx = np.where(_in_range)[0]
            missing = [int(i) for i in _cand_idx
                       if (int(Fs[i, 0]), int(Fs[i, 1]), int(Fs[i, 2])) not in tf_set]
        else:
            missing = []
        # FFF1 (beta2060) — BSP insert 한계 확장: missing<1000, max_inserts=800.
        if len(missing) > 0 and len(missing) < 1000:
            n_v_pre_b = int(final_pts.shape[0])
            n_t_pre_b = int(final_tets.shape[0])
            new_pts_b, new_tets_b, bsp_r = _bsp_batch(
                final_pts, final_tets, V, F,
                np.asarray(missing, dtype=np.int64),
                max_inserts=800,
            )
            # The batch helper is a proposal stage: it may remove crossed
            # tets while returning only the proposed points.  Its
            # n_missing_after is intentionally unset (-1) until the caller
            # rebuilds/rechecks the tet complex.  Never accept that partial
            # complex as a mesh.
            bsp_boundary = _check_bsp_boundary(
                final_pts,
                final_tets,
                new_pts_b,
                new_tets_b,
                "pre_bsp->bsp_batch_candidate",
                log_only=True,
            )
            n_missing_after = int(_find_missing_triangles(F, new_tets_b).size)
            n_recovered = int(bsp_r.n_missing_before - n_missing_after)
            prefix_stable = np.array_equal(new_pts_b[:n_v_pre_b], final_pts)
            candidate_shape_valid = new_tets_b.shape[0] >= n_t_pre_b
            candidate_accepted = bool(
                new_tets_b.shape[0] > 50
                and n_recovered > 0
                and prefix_stable
                and candidate_shape_valid
                and bsp_boundary.area_equal
            )
            if candidate_accepted:
                final_pts = new_pts_b
                final_tets = new_tets_b
                bsp_r.n_missing_after = n_missing_after
                log.info(
                    "native_tet_bsp_insert",
                    missing_before=int(bsp_r.n_missing_before),
                    missing_after=n_missing_after,
                    n_recovered=int(n_recovered),
                    n_inserted_points=int(bsp_r.n_inserted_points),
                    v_before=n_v_pre_b, v_after=int(new_pts_b.shape[0]),
                    t_before=n_t_pre_b, t_after=int(new_tets_b.shape[0]),
                )
            else:
                log.warning(
                    "native_tet_bsp_insert_rejected",
                    missing_before=int(bsp_r.n_missing_before),
                    missing_after=n_missing_after,
                    n_recovered=int(n_recovered),
                    n_inserted_points=int(bsp_r.n_inserted_points),
                    v_before=n_v_pre_b,
                    v_after=int(new_pts_b.shape[0]),
                    t_before=n_t_pre_b,
                    t_after=int(new_tets_b.shape[0]),
                    boundary_keys_equal=bool(bsp_boundary.keys_equal),
                    boundary_area_equal=bool(bsp_boundary.area_equal),
                    prefix_stable=prefix_stable,
                    candidate_shape_valid=candidate_shape_valid,
                )
    except Exception as exc:
        log.debug("native_tet_bsp_insert_skipped", reason=str(exc))

    # Diagnostic-only snapshot: the EEE lane contains several local topology
    # operations.  Compare its net result separately from later Steiner/CVT
    # stages so a final write cannot hide the first boundary violation.
    _eee_boundary_before = (final_pts.copy(), final_tets.copy())

    # EEE1 (beta2050) — BSP insert 후 flip + AMIPS post-pass: 새 Steiner
    # vertex 로 인한 sliver 추가 처리.
    try:
        if _phase_bc_skip:
            raise RuntimeError("_phase_bc_skip")
        from core.generator.native_tet.quality import snapshot as _qsnap_eee
        from core.generator.native_tet.flip import (
            flip_faces_23 as _f23_e, flip_edges_32 as _f32_e,
        )
        pre_q_e1 = _qsnap_eee(final_pts, final_tets)
        if float(pre_q_e1.mean_q) < 0.30 and final_tets.shape[0] > 100:
            # flip_23 1회.
            new_tets_e1, n_e1 = _f23_e(
                final_pts, final_tets,
                min_quality_improvement=1e-3, max_flips=1500,
            )
            if n_e1 > 0:
                post_q_e1 = _qsnap_eee(final_pts, new_tets_e1)
                if float(post_q_e1.mean_q) >= float(pre_q_e1.mean_q) * 0.99:
                    final_tets = new_tets_e1
                    log.info("native_tet_post_bsp_flip_23", n_flips=int(n_e1),
                             mq_before=round(float(pre_q_e1.mean_q), 3),
                             mq_after=round(float(post_q_e1.mean_q), 3))
            # flip_32 1회.
            pre_q_e2 = _qsnap_eee(final_pts, final_tets)
            new_tets_e2, n_e2 = _f32_e(
                final_pts, final_tets,
                min_quality_improvement=1e-3, max_flips=1000,
            )
            if n_e2 > 0:
                post_q_e2 = _qsnap_eee(final_pts, new_tets_e2)
                if float(post_q_e2.mean_q) >= float(pre_q_e2.mean_q) * 0.99:
                    final_tets = new_tets_e2
                    log.info("native_tet_post_bsp_flip_32", n_flips=int(n_e2),
                             mq_before=round(float(pre_q_e2.mean_q), 3),
                             mq_after=round(float(post_q_e2.mean_q), 3))
            # KKK1 (beta2073) — flip-only sliver removal cycle (BSP 후, vertex 위치 불변).
            # flip_23 pass.
            try:
                from core.generator.native_tet.flip import flip_edges_44 as _f44_k
                _pre_k1 = _qsnap_eee(final_pts, final_tets)
                _new_tets_k1, _n_k1 = _f23_e(
                    final_pts, final_tets,
                    min_quality_improvement=1e-3, max_flips=1500,
                )
                _post_k1 = _qsnap_eee(final_pts, _new_tets_k1)
                if (
                    float(_post_k1.min_q) >= float(_pre_k1.min_q) * 0.99
                    and float(_post_k1.mean_q) >= float(_pre_k1.mean_q) * 0.99
                ):
                    final_tets = _new_tets_k1
                else:
                    _n_k1 = 0
                # flip_32 pass.
                _pre_k2 = _qsnap_eee(final_pts, final_tets)
                _new_tets_k2, _n_k2 = _f32_e(
                    final_pts, final_tets,
                    min_quality_improvement=1e-3, max_flips=1000,
                )
                _post_k2 = _qsnap_eee(final_pts, _new_tets_k2)
                if (
                    float(_post_k2.min_q) >= float(_pre_k2.min_q) * 0.99
                    and float(_post_k2.mean_q) >= float(_pre_k2.mean_q) * 0.99
                ):
                    final_tets = _new_tets_k2
                else:
                    _n_k2 = 0
                # flip_44 pass.
                _pre_k3 = _qsnap_eee(final_pts, final_tets)
                _new_tets_k3, _n_k3 = _f44_k(
                    final_pts, final_tets,
                    min_quality_improvement=1e-3, max_flips=1000,
                )
                _post_k3 = _qsnap_eee(final_pts, _new_tets_k3)
                if (
                    float(_post_k3.min_q) >= float(_pre_k3.min_q) * 0.99
                    and float(_post_k3.mean_q) >= float(_pre_k3.mean_q) * 0.99
                ):
                    final_tets = _new_tets_k3
                else:
                    _n_k3 = 0
                _final_k = _qsnap_eee(final_pts, final_tets)
                log.info(
                    "native_tet_kkk1",
                    n_flips_23=int(_n_k1),
                    n_flips_32=int(_n_k2),
                    n_flips_44=int(_n_k3),
                    mq_before=round(float(_pre_k1.mean_q), 3),
                    mq_after=round(float(_final_k.mean_q), 3),
                    min_q_before=round(float(_pre_k1.min_q), 4),
                    min_q_after=round(float(_final_k.min_q), 4),
                )
                # MMM1 — flip cycle 2차 반복 (multi-pass, Joe 1995 §4).
                try:
                    _pre_m1 = _qsnap_eee(final_pts, final_tets)
                    _new_tets_m1, _n_m1 = _f23_e(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1500,
                    )
                    _post_m1 = _qsnap_eee(final_pts, _new_tets_m1)
                    if (
                        float(_post_m1.min_q) >= float(_pre_m1.min_q) * 0.99
                        and float(_post_m1.mean_q) >= float(_pre_m1.mean_q) * 0.99
                    ):
                        final_tets = _new_tets_m1
                    else:
                        _n_m1 = 0
                    # flip_32 pass.
                    _pre_m2 = _qsnap_eee(final_pts, final_tets)
                    _new_tets_m2, _n_m2 = _f32_e(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1000,
                    )
                    _post_m2 = _qsnap_eee(final_pts, _new_tets_m2)
                    if (
                        float(_post_m2.min_q) >= float(_pre_m2.min_q) * 0.99
                        and float(_post_m2.mean_q) >= float(_pre_m2.mean_q) * 0.99
                    ):
                        final_tets = _new_tets_m2
                    else:
                        _n_m2 = 0
                    # flip_44 pass.
                    _pre_m3 = _qsnap_eee(final_pts, final_tets)
                    _new_tets_m3, _n_m3 = _f44_k(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1000,
                    )
                    _post_m3 = _qsnap_eee(final_pts, _new_tets_m3)
                    if (
                        float(_post_m3.min_q) >= float(_pre_m3.min_q) * 0.99
                        and float(_post_m3.mean_q) >= float(_pre_m3.mean_q) * 0.99
                    ):
                        final_tets = _new_tets_m3
                    else:
                        _n_m3 = 0
                    _final_m = _qsnap_eee(final_pts, final_tets)
                    log.info(
                        "native_tet_mmm1",
                        n_flips_23=int(_n_m1),
                        n_flips_32=int(_n_m2),
                        n_flips_44=int(_n_m3),
                        mq_before=round(float(_pre_m1.mean_q), 3),
                        mq_after=round(float(_final_m.mean_q), 3),
                        min_q_before=round(float(_pre_m1.min_q), 4),
                        min_q_after=round(float(_final_m.min_q), 4),
                    )
                except Exception as exc:
                    log.warning("native_tet_mmm1_skipped", reason=str(exc)[:120])
            except Exception as exc:
                log.warning("native_tet_kkk1_skipped", reason=str(exc)[:120])
        try:
            from core.generator.native_tet.boundary_invariant import (
                check_boundary_invariant as _check_eee_boundary,
            )
            _eee_boundary_report = _check_eee_boundary(
                _eee_boundary_before[0], _eee_boundary_before[1],
                final_pts, final_tets, "post_bsp_quality_eee1", log_only=True,
            )
            log.info(
                "native_tet_post_bsp_quality_boundary_snapshot",
                preserved=_eee_boundary_report.preserved,
                before_boundary_faces=_eee_boundary_report.before_face_count,
                after_boundary_faces=_eee_boundary_report.after_face_count,
            )
        except Exception as _eee_boundary_exc:
            log.debug(
                "native_tet_post_bsp_quality_boundary_snapshot_skipped",
                reason=str(_eee_boundary_exc)[:120],
            )
        _boundary_audit_probe("post_eee_quality")

        # NNN1 — Steiner dry-run sliver detection (TetWild §3.3, read-only)
        if os.environ.get("AUTO_TESSELL_NNN1_DRYRUN", "1") != "0":
            try:
                from core.generator.native_tet.quality import tet_shape_quality
                q_arr = tet_shape_quality(final_pts, final_tets)
                sliver_mask = q_arr < 0.05
                n_sliver = int(sliver_mask.sum())
                try:
                    _sliver_centroids = final_pts[final_tets[sliver_mask]].mean(axis=1)
                    n_sliver_inside = int(envelope.contains_points(_sliver_centroids).sum())
                except Exception:
                    n_sliver_inside = n_sliver
                log.info(
                    "native_tet_nnn1_dry_run",
                    n_sliver=n_sliver,
                    n_sliver_inside=n_sliver_inside,
                    threshold=0.05,
                )
            except Exception as exc:
                log.warning("native_tet_nnn1_failed", reason=str(exc)[:200])
        # NNN2b — Steiner circumcenter insertion (TetWild §3.3, envelope-validated)
        if _phase_a_observer is not None:
            _report_phase_a_provenance_checkpoint(_phase_a_observer, stage="post_nnn1_dry_run", source_points=_input_source_vertices, source_faces=_input_source_faces, candidate_points=final_pts, candidate_tets=final_tets)
        if os.environ.get("AUTO_TESSELL_NNN2_INSERT", "1") != "0":
            try:
                from core.generator.native_tet.quality import tet_shape_quality
                from scipy.spatial import Delaunay

                pre_q_arr = tet_shape_quality(final_pts, final_tets)
                pre_min = float(pre_q_arr.min())
                pre_mean = float(pre_q_arr.mean())

                sliver_mask = pre_q_arr < 0.05
                n_worst = min(200, int(sliver_mask.sum()))
                worst_idx = np.argsort(pre_q_arr)[:n_worst]

                if len(worst_idx) > 0:
                    _wpts = final_pts[final_tets[worst_idx]]  # (K,4,3)
                    _A = 2.0 * (_wpts[:, 1:, :] - _wpts[:, :1, :])  # (K,3,3)
                    _b = (np.sum(_wpts[:, 1:, :] ** 2, axis=2)
                          - np.sum(_wpts[:, :1, :] ** 2, axis=2))  # (K,3)
                    cands_list = []
                    for _ki in range(len(worst_idx)):
                        try:
                            _cc = np.linalg.lstsq(_A[_ki], _b[_ki], rcond=None)[0]
                        except Exception:
                            _cc = _wpts[_ki].mean(axis=0)
                        cands_list.append(_cc)
                    cands = np.array(cands_list) if cands_list else np.zeros((0, 3))
                else:
                    cands = np.zeros((0, 3))

                if len(cands) > 0:
                    try:
                        mask_inside = envelope.contains_points(cands)
                    except Exception:
                        mask_inside = np.ones(len(cands), dtype=bool)

                    if mask_inside.any():
                        trial_pts = np.vstack([final_pts, cands[mask_inside]])
                        new_tets = Delaunay(trial_pts).simplices

                        # drop outside tets
                        centroids = trial_pts[new_tets].mean(axis=1)
                        try:
                            keep = envelope.contains_points(centroids)
                        except Exception:
                            keep = np.ones(len(new_tets), dtype=bool)
                        new_tets_inside = new_tets[keep]

                        if len(new_tets_inside) > 0:
                            post_q_arr = tet_shape_quality(trial_pts, new_tets_inside)
                            if (
                                post_q_arr.min() >= pre_min - 1e-12
                                and post_q_arr.mean() >= pre_mean - 1e-12
                            ):
                                final_pts, final_tets = trial_pts, new_tets_inside
                                n_inserted = int(mask_inside.sum())
                            else:
                                n_inserted = 0
                                post_q_arr = pre_q_arr
                        else:
                            n_inserted = 0
                            post_q_arr = pre_q_arr
                    else:
                        n_inserted = 0
                        post_q_arr = pre_q_arr
                else:
                    n_inserted = 0
                    post_q_arr = pre_q_arr

                log.info(
                    "native_tet_nnn2",
                    n_inserted=n_inserted,
                    pre_min=pre_min,
                    post_min=float(post_q_arr.min()),
                    pre_mean=pre_mean,
                    post_mean=float(post_q_arr.mean()),
                )
            except Exception as exc:
                log.warning("native_tet_nnn2_failed", reason=str(exc)[:200])

        # NNN3 — Steiner circumcenter insertion cycle 2 (TetWild §3.3)
        if _phase_a_observer is not None:
            _report_phase_a_provenance_checkpoint(_phase_a_observer, stage="post_nnn2_insert", source_points=_input_source_vertices, source_faces=_input_source_faces, candidate_points=final_pts, candidate_tets=final_tets)
        if os.environ.get("AUTO_TESSELL_NNN3_INSERT", "1") != "0":
            try:
                from core.generator.native_tet.quality import tet_shape_quality
                from scipy.spatial import Delaunay

                pre_q_arr = tet_shape_quality(final_pts, final_tets)
                pre_min = float(pre_q_arr.min())
                pre_mean = float(pre_q_arr.mean())

                sliver_mask = pre_q_arr < 0.05
                n_worst = min(200, int(sliver_mask.sum()))
                worst_idx = np.argsort(pre_q_arr)[:n_worst]

                if len(worst_idx) > 0:
                    _wpts3 = final_pts[final_tets[worst_idx]]  # (K,4,3)
                    _A3 = 2.0 * (_wpts3[:, 1:, :] - _wpts3[:, :1, :])
                    _b3 = (np.sum(_wpts3[:, 1:, :] ** 2, axis=2)
                           - np.sum(_wpts3[:, :1, :] ** 2, axis=2))
                    _cl3 = []
                    for _ki3 in range(len(worst_idx)):
                        try:
                            _cl3.append(np.linalg.lstsq(_A3[_ki3], _b3[_ki3], rcond=None)[0])
                        except Exception:
                            _cl3.append(_wpts3[_ki3].mean(axis=0))
                    cands = np.array(_cl3) if _cl3 else np.zeros((0, 3))
                else:
                    cands = np.zeros((0, 3))

                if len(cands) > 0:
                    try:
                        mask_inside = envelope.contains_points(cands)
                    except Exception:
                        mask_inside = np.ones(len(cands), dtype=bool)

                    if mask_inside.any():
                        trial_pts = np.vstack([final_pts, cands[mask_inside]])
                        new_tets = Delaunay(trial_pts).simplices

                        centroids = trial_pts[new_tets].mean(axis=1)
                        try:
                            keep = envelope.contains_points(centroids)
                        except Exception:
                            keep = np.ones(len(new_tets), dtype=bool)
                        new_tets_inside = new_tets[keep]

                        if len(new_tets_inside) > 0:
                            post_q_arr = tet_shape_quality(trial_pts, new_tets_inside)
                            if (
                                post_q_arr.min() >= pre_min - 1e-12
                                and post_q_arr.mean() >= pre_mean - 1e-12
                            ):
                                final_pts, final_tets = trial_pts, new_tets_inside
                                n_inserted_iter2 = int(mask_inside.sum())
                            else:
                                n_inserted_iter2 = 0
                                post_q_arr = pre_q_arr
                        else:
                            n_inserted_iter2 = 0
                            post_q_arr = pre_q_arr
                    else:
                        n_inserted_iter2 = 0
                        post_q_arr = pre_q_arr
                else:
                    n_inserted_iter2 = 0
                    post_q_arr = pre_q_arr

                log.info(
                    "native_tet_nnn3",
                    n_inserted_iter2=n_inserted_iter2,
                    pre_min=pre_min,
                    post_min=float(post_q_arr.min()),
                    pre_mean=pre_mean,
                    post_mean=float(post_q_arr.mean()),
                )
            except Exception as exc:
                log.warning("native_tet_nnn3_skipped", reason=str(exc)[:120])

        # NNN4 — post-Steiner interior AMIPS smoothing (Klingner 2008 §3.5)
        if _phase_a_observer is not None:
            _report_phase_a_provenance_checkpoint(_phase_a_observer, stage="post_nnn3_insert", source_points=_input_source_vertices, source_faces=_input_source_faces, candidate_points=final_pts, candidate_tets=final_tets)
        if os.environ.get("AUTO_TESSELL_NNN4_AMIPS", "1") != "0":
            try:
                from core.generator.native_tet.amips import smooth_amips_analytic
                from core.generator.native_tet.quality import tet_shape_quality

                n_surface_in = int(V.shape[0])
                surface_lock_ids = np.arange(n_surface_in, dtype=np.int64)

                pre_q = tet_shape_quality(final_pts, final_tets)
                pre_min = float(pre_q.min())
                pre_mean = float(pre_q.mean())

                _res, smoothed_pts = smooth_amips_analytic(
                    final_pts, final_tets,
                    locked_vertex_ids=surface_lock_ids,
                    n_iter=1,
                    alpha=1.0,
                )

                post_q = tet_shape_quality(smoothed_pts, final_tets)
                accepted = bool(
                    post_q.min() >= pre_min - 1e-12
                    and post_q.mean() >= pre_mean - 1e-12
                )
                if accepted:
                    final_pts = smoothed_pts

                log.info(
                    "native_tet_nnn4_post_steiner_amips",
                    pre_min=pre_min,
                    post_min=float(post_q.min()),
                    pre_mean=pre_mean,
                    post_mean=float(post_q.mean()),
                    accepted=accepted,
                )
            except Exception as exc:
                log.warning("native_tet_nnn4_skipped", reason=str(exc)[:120])

        # RRR2 — worst-percentile targeted AMIPS smoothing (Klingner 2008 §3.5)
        if _phase_a_observer is not None:
            _report_phase_a_provenance_checkpoint(_phase_a_observer, stage="post_nnn4_amips", source_points=_input_source_vertices, source_faces=_input_source_faces, candidate_points=final_pts, candidate_tets=final_tets)
        if os.environ.get("AUTO_TESSELL_RRR2_TARGETED", "1") != "0":
            try:
                from core.generator.native_tet.quality import _RRR1_QUALITY_HISTOGRAM, tet_shape_quality
                from core.generator.native_tet.amips import smooth_amips_analytic

                if not _RRR1_QUALITY_HISTOGRAM:
                    pass
                else:
                    q_per_tet = tet_shape_quality(final_pts, final_tets)
                    p5 = float(np.percentile(q_per_tet, 5))

                    if p5 >= 0.10:
                        log.info("native_tet_rrr2_targeted_amips_skip", p5=p5, reason="p5>=0.10")
                    else:
                        worst_mask = q_per_tet < 0.10
                        worst_v = np.unique(final_tets[worst_mask].ravel())

                        n_surface_in = int(V.shape[0])
                        is_surface = worst_v < n_surface_in
                        free_v = worst_v[~is_surface]

                        if free_v.size == 0:
                            log.info("native_tet_rrr2_targeted_amips_skip", p5=p5, reason="no_free_interior_vertices")
                        else:
                            all_ids = np.arange(final_pts.shape[0], dtype=np.int64)
                            lock_ids = np.setdiff1d(all_ids, free_v)

                            pre_min = float(q_per_tet.min())
                            pre_mean = float(q_per_tet.mean())

                            # P2.2 / beta2310: torch (CUDA) 라우팅 — fine
                            # quality 에서 use_torch_amips=True 면 batch
                            # tensor 경로. CUDA 미가용 시 torch CPU. torch
                            # 미설치 환경 fallback → numpy.
                            sm_pts = None
                            if use_torch_amips:
                                try:
                                    from core.generator.native_tet.amips_torch import (
                                        smooth_amips_torch, is_available as _torch_avail,
                                    )
                                    if _torch_avail():
                                        _tres, sm_pts = smooth_amips_torch(
                                            final_pts, final_tets,
                                            locked_vertex_ids=lock_ids,
                                            n_iter=2, alpha=1.0,
                                        )
                                        log.info(
                                            "native_tet_rrr2_amips_torch",
                                            device=_tres.device,
                                            energy_before=round(_tres.energy_before, 4),
                                            energy_after=round(_tres.energy_after, 4),
                                        )
                                except Exception as _exc_t:
                                    log.warning(
                                        "native_tet_rrr2_torch_fallback",
                                        reason=str(_exc_t)[:120],
                                    )
                                    sm_pts = None
                            if sm_pts is None:
                                _res, sm_pts = smooth_amips_analytic(
                                    final_pts, final_tets,
                                    locked_vertex_ids=lock_ids,
                                    n_iter=2,
                                    alpha=1.0,
                                )

                            post_q = tet_shape_quality(sm_pts, final_tets)
                            # beta2307 — RRR2 monotone guard 완화.
                            # 이전: worst -1e-12 (사실상 no-drop) + mean -1e-12 → 거의 모든 시도 reject
                            #       → 60+ round 카드 누적에도 grade A=0/20.
                            # 신규: worst 하락 ≤ 0.015 허용 + mean 향상 (≥ pre - 1e-12).
                            #       → fTetWild §3.5 envelope-bounded relocation 의 활용 가능.
                            #       SSS_REVIVAL (line 2508) 와 동일 임계.
                            # P1.3 / beta2581 — D-cell recovery branch 추가.
                            #   min quality 개선이 큰 경우 (≥ 0.005) 작은 mean
                            #   drop (≤ 0.005) 까지 허용. Klingner §3.5 가
                            #   강조하는 worst tet 회복 우선 정책. tet grade A
                            #   self-impl 0/20 → +2~3/20 expected.
                            _worst_drop = pre_min - float(post_q.min())
                            _mean_gain = float(post_q.mean()) - pre_mean
                            _min_gain = float(post_q.min()) - pre_min
                            accepted_standard = (
                                _worst_drop <= 0.015
                                and _mean_gain >= -1e-12
                            )
                            accepted_d_recovery = (
                                _min_gain >= 0.005
                                and _mean_gain >= -0.005
                            )
                            # RRR3 extreme-worst lane (BETA2819): pre_min < 0.05
                            # (D-cell extreme regime) 에서 min_gain ≥ 0.002 이고
                            # mean strict non-drop → worst monotone 보장.
                            _rrr3_extreme_on = (
                                os.environ.get("AUTO_TESSELL_RRR3_EXTREME", "1") == "1"
                            )
                            accepted_extreme = bool(
                                _rrr3_extreme_on
                                and pre_min < 0.05
                                and _min_gain >= 0.002
                                and _mean_gain >= -1e-12
                            )
                            accepted = bool(
                                accepted_standard
                                or accepted_d_recovery
                                or accepted_extreme
                            )
                            if accepted:
                                final_pts = sm_pts

                            log.info(
                                "native_tet_rrr2_targeted_amips",
                                p5=p5,
                                n_worst=int(worst_mask.sum()),
                                n_free=int(free_v.size),
                                pre_min=pre_min,
                                post_min=float(post_q.min()),
                                pre_mean=pre_mean,
                                post_mean=float(post_q.mean()),
                                accepted=accepted,
                                accepted_extreme=bool(accepted_extreme),
                                q_thresh=0.10,
                                n_iter=2,
                            )
            except Exception as exc:
                log.warning("native_tet_rrr2_skipped", reason=str(exc)[:120])

        # P3-card2 (beta2234) — SSS revival: envelope-bounded surface vertex
        if _phase_a_observer is not None:
            _report_phase_a_provenance_checkpoint(_phase_a_observer, stage="post_rrr2_targeted_amips", source_points=_input_source_vertices, source_faces=_input_source_faces, candidate_points=final_pts, candidate_tets=final_tets)
        # relocation (fTetWild §3.5).
        # 동기: small mesh 의 surface vertex 비율 90%+ 이라 RRR2 의 free
        # interior pool (7-32) 부족. surface vertex 도 envelope ε 안에서
        # 작은 inward step 으로 이동 가능 → quality histogram 깰 가능성.
        # SSS2/3 abandon (worst -0.027) 회피: 가드 worst -0.015 + mean 향상.
        if os.environ.get("AUTO_TESSELL_P3_SSS_REVIVAL", "1") != "0":
            try:
                from core.generator.native_tet.envelope import Envelope as _Env
                from core.generator.native_tet.envelope_relocate import _envelope_bounded_relocate
                from core.generator.native_tet.quality import tet_shape_quality as _tsq
                # C1.2 / beta2361 — 1-pass → multi-pass iteration (max 3 passes).
                # 각 pass 가 채택되면 다음 pass 의 input 이 되어 효과가 compound.
                # 거부되거나 quality 개선 < 1e-4 (plateau) 면 중단.
                # 기본 3 passes; AUTO_TESSELL_P3_SSS_REVIVAL_PASSES env 로 override.
                _max_passes = int(os.environ.get("AUTO_TESSELL_P3_SSS_REVIVAL_PASSES", "3"))
                # vertex normal + Laplacian target 은 pass 간 동일 (입력 V/F 기준).
                # pass 마다 final_pts 만 바뀌므로 미리 계산.
                env = None
                vn = None
                target_pts = None
                surface_idx = None
                n_surface = 0
                for _pass_idx in range(max(1, _max_passes)):
                    if _phase_a_observer is not None and _pass_idx == 0:
                        _report_phase_a_provenance_checkpoint(
                            _phase_a_observer,
                            stage="sss_pass0_pre_quality",
                            source_points=_input_source_vertices,
                            source_faces=_input_source_faces,
                            candidate_points=final_pts,
                            candidate_tets=final_tets,
                        )
                    _q_pre = _tsq(final_pts, final_tets)
                    _pre_min = float(_q_pre.min())
                    _pre_mean = float(_q_pre.mean())
                    if not (_pre_min < 0.10 and final_tets.shape[0] > 50):
                        break  # 정책 (아직 sliver 없음 또는 너무 작은 mesh) — 중단.
                    if env is None:
                        # 첫 pass 에서만 expensive 한 정규/이웃 계산 수행.
                        n_surface = int(min(V.shape[0], final_pts.shape[0]))
                        surface_idx = np.arange(n_surface, dtype=np.intp)
                        e1_in = V[F[:, 1]] - V[F[:, 0]]
                        e2_in = V[F[:, 2]] - V[F[:, 0]]
                        fn = np.cross(e1_in, e2_in)
                        fn_len = np.linalg.norm(fn, axis=1, keepdims=True)
                        fn = fn / np.maximum(fn_len, 1e-30)
                        # C-PERF-62 / beta2513 — vertex normal + Laplacian
                        # 1-ring scatter 모두 벡터화.
                        vn = np.zeros((n_surface, 3), dtype=np.float64)
                        for k in range(3):
                            vk_col = F[:, k].astype(np.int64)
                            mask_k = vk_col < n_surface
                            np.add.at(vn, vk_col[mask_k], fn[mask_k])
                        vn_len = np.linalg.norm(vn, axis=1, keepdims=True)
                        vn = vn / np.maximum(vn_len, 1e-30)
                        env = _Env.build_auto_eps(V, F, base_ratio=0.001)
                        # 6 (vk, wk) 페어 per face: (0,1),(0,2),(1,0),(1,2),(2,0),(2,1)
                        vk_flat = F[:, [0, 0, 1, 1, 2, 2]].reshape(-1).astype(np.int64)
                        wk_flat = F[:, [1, 2, 0, 2, 0, 1]].reshape(-1).astype(np.int64)
                        mask_lap = vk_flat < n_surface
                        nbr_sum = np.zeros((n_surface, 3), dtype=np.float64)
                        nbr_cnt = np.zeros(n_surface, dtype=np.int64)
                        np.add.at(nbr_sum, vk_flat[mask_lap], V[wk_flat[mask_lap]])
                        np.add.at(nbr_cnt, vk_flat[mask_lap], 1)
                        target_pts = nbr_sum / np.maximum(nbr_cnt[:, None], 1)
                    if _phase_a_observer is not None and _pass_idx == 0:
                        _report_phase_a_provenance_checkpoint(
                            _phase_a_observer,
                            stage="sss_pass0_post_target_construction",
                            source_points=_input_source_vertices,
                            source_faces=_input_source_faces,
                            candidate_points=final_pts,
                            candidate_tets=final_tets,
                        )
                    if _phase_a_observer is not None and _pass_idx == 0:
                        _report_phase_a_provenance_checkpoint(
                            _phase_a_observer,
                            stage="pre_sss_pass0_relocate",
                            source_points=_input_source_vertices,
                            source_faces=_input_source_faces,
                            candidate_points=final_pts,
                            candidate_tets=final_tets,
                        )
                    new_pts = _envelope_bounded_relocate(
                        final_pts, surface_idx, target_pts, vn, env,
                    )
                    _q_post = _tsq(new_pts, final_tets)
                    _post_min = float(_q_post.min())
                    _post_mean = float(_q_post.mean())
                    _worst_drop = _pre_min - _post_min
                    _mean_gain = _post_mean - _pre_mean
                    accepted = bool(_worst_drop <= 0.015 and _mean_gain >= -1e-12)
                    if _phase_a_observer is not None and _pass_idx == 0:
                        _report_phase_a_provenance_checkpoint(
                            _phase_a_observer,
                            stage="post_sss_pass0_relocate_pre_accept",
                            source_points=_input_source_vertices,
                            source_faces=_input_source_faces,
                            candidate_points=new_pts,
                            candidate_tets=final_tets,
                        )
                    log.info(
                        "native_tet_p3_sss_revival",
                        pass_idx=int(_pass_idx),
                        n_surface=int(n_surface),
                        envelope_eps=round(float(env.eps), 6),
                        pre_min=_pre_min, post_min=_post_min,
                        pre_mean=_pre_mean, post_mean=_post_mean,
                        worst_drop=_worst_drop, mean_gain=_mean_gain,
                        accepted=accepted,
                    )
                    if accepted:
                        final_pts = new_pts
                        if _phase_a_observer is not None:
                            _report_phase_a_provenance_checkpoint(
                                _phase_a_observer,
                                stage=f"post_sss_revival_pass_{_pass_idx}",
                                source_points=_input_source_vertices,
                                source_faces=_input_source_faces,
                                candidate_points=final_pts,
                                candidate_tets=final_tets,
                            )
                        # plateau detect: mean_gain < 1e-4 면 추가 pass 효과 미미.
                        if _mean_gain < 1e-4:
                            break
                    else:
                        if _phase_a_observer is not None:
                            _report_phase_a_provenance_checkpoint(
                                _phase_a_observer,
                                stage=(
                                    f"post_sss_revival_pass_{_pass_idx}_rejected"
                                ),
                                source_points=_input_source_vertices,
                                source_faces=_input_source_faces,
                                candidate_points=final_pts,
                                candidate_tets=final_tets,
                            )
                        # reject 시 즉시 중단 (다음 pass 도 동일 quality plateau).
                        break
            except Exception as exc:
                log.warning("native_tet_p3_sss_revival_skipped", reason=str(exc)[:120])

        # C1.3 / beta2363 — Volumetric Lloyd CVT 3D (interior vertex relaxation).
        if _phase_a_observer is not None:
            _report_phase_a_provenance_checkpoint(_phase_a_observer, stage="post_sss_revival", source_points=_input_source_vertices, source_faces=_input_source_faces, candidate_points=final_pts, candidate_tets=final_tets)
        # SSS_REVIVAL (surface) 와 보완적: 내부 vertex 의 1-ring tet centroid
        # 평균. monotone guard 표준. env AUTO_TESSELL_CVT3D_OFF=1 로 비활성.
        if os.environ.get("AUTO_TESSELL_CVT3D_OFF", "0") != "1":
            try:
                from core.generator.native_tet.cvt3d import lloyd_cvt_3d
                from core.generator.native_tet.plane_coverage import _tet_boundary_faces

                _boundary_lock_ids_cvt = np.unique(
                    _tet_boundary_faces(final_tets),
                ).astype(np.intp)
                _n_surface_cvt = 0
                _cvt3d_iter = int(os.environ.get("AUTO_TESSELL_CVT3D_ITER", "3"))
                _cvt3d_relax = float(os.environ.get("AUTO_TESSELL_CVT3D_RELAX", "0.5"))

                def _cvt3d_fail_closed_result(
                    points: np.ndarray,
                    tets: np.ndarray,
                    transaction: dict[str, int | bool],
                ) -> NativeTetResult:
                    """Return before any later topology mutator can run."""
                    import shutil

                    stale_poly_mesh = Path(case_dir) / "constant" / "polyMesh"
                    if stale_poly_mesh.is_dir():
                        shutil.rmtree(stale_poly_mesh)
                    return NativeTetResult(
                        False,
                        time.perf_counter() - t0,
                        n_cells=int(tets.shape[0]),
                        n_points=int(points.shape[0]),
                        message=(
                            "native_tet CVT candidate increases strict "
                            "internal-face debt"
                        ),
                        tet_points=points,
                        tets=tets,
                        warnings=None,
                        debug_info={
                            "cvt3d_sidedness_transaction": transaction,
                            "strict_source_topology": {
                                "valid": False,
                                "polymesh_artifacts_removed": (
                                    not stale_poly_mesh.exists()
                                ),
                            },
                        },
                    )

                if _phase_a_observer is not None:
                    _report_phase_a_provenance_checkpoint(
                        _phase_a_observer, stage="pre_cvt3d",
                        source_points=_input_source_vertices,
                        source_faces=_input_source_faces,
                        candidate_points=final_pts, candidate_tets=final_tets,
                    )
                _cvt3d_before_pts = final_pts
                _cvt3d_before_tets = final_tets
                _new_pts_cvt, _cvt_res = lloyd_cvt_3d(
                    final_pts, final_tets,
                    n_surface=_n_surface_cvt,
                    n_iter=_cvt3d_iter,
                    relax=_cvt3d_relax,
                    locked_ids=_boundary_lock_ids_cvt,
                )
                if _cvt_res.accepted:
                    (
                        _cvt3d_selected_pts,
                        _cvt3d_selected_tets,
                        _cvt3d_sidedness_transaction,
                    ) = _commit_cvt3d_sidedness_nonincreasing_candidate(
                        _cvt3d_before_pts,
                        _cvt3d_before_tets,
                        _new_pts_cvt,
                        final_tets,
                    )
                    _cvt3d_sidedness_transaction = {
                        **_cvt3d_sidedness_transaction,
                        "n_iter": int(_cvt_res.n_iter_used),
                        "n_moved": int(_cvt_res.n_moved),
                    }
                    if not _cvt3d_sidedness_transaction["accepted"]:
                        # This is the first persistent overlap transition
                        # after JJ3.  Do not let a later local pass conceal
                        # it: return the exact pre-CVT arrays and publish no
                        # new polyMesh artifact.
                        log.warning(
                            "native_tet_cvt3d_sidedness_rejected",
                            **_cvt3d_sidedness_transaction,
                        )
                        return _cvt3d_fail_closed_result(
                            _cvt3d_selected_pts,
                            _cvt3d_selected_tets,
                            _cvt3d_sidedness_transaction,
                        )
                    final_pts = _cvt3d_selected_pts
                    final_tets = _cvt3d_selected_tets
                log.info(
                    "native_tet_cvt3d_lloyd",
                    n_iter=_cvt_res.n_iter_used,
                    n_moved=_cvt_res.n_moved,
                    pre_min=_cvt_res.pre_min_q,
                    post_min=_cvt_res.post_min_q,
                    pre_mean=_cvt_res.pre_mean_q,
                    post_mean=_cvt_res.post_mean_q,
                    accepted=_cvt_res.accepted,
                    elapsed_s=round(_cvt_res.elapsed_s, 3),
                )
                # GAP-TET / beta2779 — 2차 CVT3D pass (quality-weighted, 강력).
                # 첫 pass 후 mean_q < 0.20 (grade A 미달) 이면 quality-weighted
                # Lloyd 6 iter 추가. monotone guard 자체적으로 reject 처리.
                # self-impl tet grade A 0/20 → +N/20 시도.
                from core.generator.native_tet.quality import snapshot as _qsnap_cvt2
                _q_post1 = _qsnap_cvt2(final_pts, final_tets)
                if (
                    float(_q_post1.mean_q) < 0.20
                    and final_tets.shape[0] > 100
                ):
                    # 임시 env 활성 (this scope only).
                    _qw_prev = os.environ.get("AUTO_TESSELL_CVT3D_QUALITY_WEIGHT", "")
                    os.environ["AUTO_TESSELL_CVT3D_QUALITY_WEIGHT"] = "1"
                    try:
                        _new_pts_cvt2, _cvt2_res = lloyd_cvt_3d(
                            final_pts, final_tets,
                            n_surface=_n_surface_cvt,
                            n_iter=6,
                            relax=0.7,
                            locked_ids=_boundary_lock_ids_cvt,
                            monotone_worst_drop_max=0.020,
                        )
                        if _cvt2_res.accepted:
                            (
                                _cvt2_selected_pts,
                                _cvt2_selected_tets,
                                _cvt2_sidedness_transaction,
                            ) = _commit_cvt3d_sidedness_nonincreasing_candidate(
                                final_pts,
                                final_tets,
                                _new_pts_cvt2,
                                final_tets,
                            )
                            _cvt2_sidedness_transaction = {
                                **_cvt2_sidedness_transaction,
                                "pass_index": 2,
                                "n_iter": int(_cvt2_res.n_iter_used),
                                "n_moved": int(_cvt2_res.n_moved),
                            }
                            if not _cvt2_sidedness_transaction["accepted"]:
                                log.warning(
                                    "native_tet_cvt3d_sidedness_rejected",
                                    **_cvt2_sidedness_transaction,
                                )
                                return _cvt3d_fail_closed_result(
                                    _cvt2_selected_pts,
                                    _cvt2_selected_tets,
                                    _cvt2_sidedness_transaction,
                                )
                            final_pts = _cvt2_selected_pts
                            final_tets = _cvt2_selected_tets
                        log.info(
                            "native_tet_cvt3d_lloyd_pass2_qw",
                            n_iter=_cvt2_res.n_iter_used,
                            pre_mean=round(_cvt2_res.pre_mean_q, 4),
                            post_mean=round(_cvt2_res.post_mean_q, 4),
                            accepted=_cvt2_res.accepted,
                        )
                    finally:
                        if _qw_prev:
                            os.environ["AUTO_TESSELL_CVT3D_QUALITY_WEIGHT"] = _qw_prev
                        else:
                            os.environ.pop("AUTO_TESSELL_CVT3D_QUALITY_WEIGHT", None)
            except Exception as exc:
                log.warning("native_tet_cvt3d_skipped", reason=str(exc)[:120])

    except Exception as exc:
        log.debug("native_tet_post_bsp_pass_skipped", reason=str(exc))

    _boundary_audit_probe("post_nnn_cvt")

    # VAL3 (beta2158) — initialize negative-volume tracker
    try:
        from core.generator.native_tet.stellar import _count_neg_vol as _cnv  # noqa: PLC0415
        _val3_prev_neg = _cnv(final_pts, final_tets)
        log.info("native_tet_neg_vol_track", pass_name="init_post_bsp", n_neg=_val3_prev_neg, delta=0)
    except Exception:
        _val3_prev_neg = 0

    # VVV3b — Stellar queue build + swap-only apply (worst-first 32+44, triple monotone)
    _t_vvv3b = time.perf_counter()
    if os.environ.get("AUTO_TESSELL_VVV2_QUEUE", "1") != "0":
        try:
            from core.generator.native_tet.stellar import (
                _VVV1_STELLAR_QUEUE,
                _build_op_queue,
                _apply_op_queue,
            )
            from core.generator.native_tet.quality import snapshot as _qsnap  # noqa: PLC0415
            if _VVV1_STELLAR_QUEUE:
                _q = _build_op_queue(final_pts, final_tets)
                _worst = float(_q[0]["quality"]) if _q else 0.0
                log.info(
                    "native_tet_stellar_queue",
                    n_queue=len(_q),
                    worst_q=_worst,
                )
                # VVV3b: apply swap ops with triple monotone guard.
                pre = _qsnap(final_pts, final_tets)
                pre_n = final_tets.shape[0]
                # C1.7 / beta2378 — fine 의 enable_stellar_split=True 면
                # AUTO_TESSELL_STELLAR_SPLIT 자동 활성 (env override 우선).
                _stellar_env_prev: "str | None" = None
                if enable_stellar_split and "AUTO_TESSELL_STELLAR_SPLIT" not in os.environ:
                    os.environ["AUTO_TESSELL_STELLAR_SPLIT"] = "1"
                    _stellar_env_prev = "__set_by_mesher__"
                try:
                    pts2, tets2, n_app = _apply_op_queue(
                        final_pts,
                        final_tets,
                        _q,
                        protected_edges=None,
                    )
                finally:
                    if _stellar_env_prev == "__set_by_mesher__":
                        os.environ.pop("AUTO_TESSELL_STELLAR_SPLIT", None)
                post = _qsnap(pts2, tets2)
                # BETA2824 — Klingner monotone proof 만으로 채택 충분 (cell count
                # 변화는 3-2/sliver split 의 정상적 결과). drop_floor env-gated:
                # default 0.85 (15% drop 허용) — native_tet 의 over-density 와
                # wildmesh 정렬 위해 loosened. AUTO_TESSELL_STELLAR_DROP_FLOOR
                # 로 override 가능.
                _drop_floor = float(
                    os.environ.get("AUTO_TESSELL_STELLAR_DROP_FLOOR", "0.85")
                )
                accepted = (
                    post.min_q >= pre.min_q - 1e-6
                    and post.mean_q >= pre.mean_q - 1e-3
                    and tets2.shape[0] >= _drop_floor * pre_n
                )
                if accepted:
                    final_pts, final_tets = pts2, tets2
                log.info(
                    "native_tet_stellar_apply",
                    n_app=int(n_app),
                    pre_min=float(pre.min_q),
                    post_min=float(post.min_q),
                    pre_mean=float(pre.mean_q),
                    post_mean=float(post.mean_q),
                    accepted=bool(accepted),
                )
        except Exception as exc:
            log.warning("native_tet_vvv2_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV3b", dt_ms=int((time.perf_counter() - _t_vvv3b) * 1000))
    try:
        from core.generator.native_tet.stellar import _count_neg_vol as _cnv3b  # noqa: PLC0415
        _n3b = _cnv3b(final_pts, final_tets)
        log.info("native_tet_neg_vol_track", pass_name="VVV3b", n_neg=_n3b, delta=_n3b - _val3_prev_neg)
        _val3_prev_neg = _n3b
    except Exception:
        pass

    # VVV5b — flip_edges_54 (Klingner Table 1 5-4 ring removal, strict per-flip guard)
    _t_vvv5b = time.perf_counter()
    if not os.environ.get("AUTO_TESSELL_VVV5B_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv5b_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.flip import flip_edges_54 as _f54  # noqa: PLC0415
                from core.generator.native_tet.quality import snapshot as _qsnap54  # noqa: PLC0415
                _pre54 = _qsnap54(final_pts, final_tets)
                _pre54_n = final_tets.shape[0]
                _pts54, _tets54, _n54 = _f54(
                    final_pts, final_tets,
                    min_quality_improvement=1e-3,
                    max_flips=200,
                )
                _post54 = _qsnap54(_pts54, _tets54)
                _acc54 = (
                    _post54.min_q >= _pre54.min_q - 1e-6
                    and _post54.mean_q >= _pre54.mean_q - 1e-3
                    and _tets54.shape[0] >= 0.95 * _pre54_n
                )
                if _acc54:
                    final_pts, final_tets = _pts54, _tets54
                log.info(
                    "native_tet_flip54",
                    n_app=int(_n54),
                    pre_min=float(_pre54.min_q),
                    post_min=float(_post54.min_q),
                    accepted=bool(_acc54),
                )
        except Exception as exc:
            log.warning("native_tet_vvv5b_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV5b", dt_ms=int((time.perf_counter() - _t_vvv5b) * 1000))
    try:
        from core.generator.native_tet.stellar import _count_neg_vol as _cnv5b  # noqa: PLC0415
        _n5b = _cnv5b(final_pts, final_tets)
        log.info("native_tet_neg_vol_track", pass_name="VVV5b", n_neg=_n5b, delta=_n5b - _val3_prev_neg)
        _val3_prev_neg = _n5b
    except Exception:
        pass

    # VVV6 — flip_edges_76 (Klingner Table 1 7-6 ring removal, strict per-flip guard)
    _t_vvv6 = time.perf_counter()
    if not os.environ.get("AUTO_TESSELL_VVV6_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv6_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.flip import flip_edges_76 as _f76  # noqa: PLC0415
                from core.generator.native_tet.quality import snapshot as _qsnap76  # noqa: PLC0415
                _pre76 = _qsnap76(final_pts, final_tets)
                _pre76_n = final_tets.shape[0]
                _pts76, _tets76, _n76 = _f76(
                    final_pts, final_tets,
                    min_quality_improvement=1e-3,
                    max_flips=200,
                )
                _post76 = _qsnap76(_pts76, _tets76)
                _acc76 = (
                    _post76.min_q >= _pre76.min_q - 1e-6
                    and _post76.mean_q >= _pre76.mean_q - 1e-3
                    and _tets76.shape[0] >= 0.95 * _pre76_n
                )
                if _acc76:
                    final_pts, final_tets = _pts76, _tets76
                log.info(
                    "native_tet_flip76",
                    n_app=int(_n76),
                    pre_min=float(_pre76.min_q),
                    post_min=float(_post76.min_q),
                    accepted=bool(_acc76),
                )
        except Exception as exc:
            log.warning("native_tet_vvv6_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV6", dt_ms=int((time.perf_counter() - _t_vvv6) * 1000))

    # VVV7 — interior Laplacian smoothing (top-K worst-tet incident verts, ≥2-ring from boundary)
    _t_vvv7 = time.perf_counter()
    if not os.environ.get("AUTO_TESSELL_VVV7_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv7_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.laplacian import smooth_interior_laplacian as _sil  # noqa: PLC0415
                from core.generator.native_tet.quality import snapshot as _qsnap77  # noqa: PLC0415
                _pre77 = _qsnap77(final_pts, final_tets)
                _pre77_n = final_tets.shape[0]
                _pts77, _tets77, _n77 = _sil(
                    final_pts, final_tets,
                    top_k=20,
                    n_iter=1,
                    min_quality_improvement=1e-6,
                )
                _post77 = _qsnap77(_pts77, _tets77)
                _acc77 = (
                    _post77.min_q >= _pre77.min_q - 1e-6
                    and _post77.mean_q >= _pre77.mean_q - 1e-3
                    and _tets77.shape[0] == _pre77_n
                )
                if _acc77:
                    final_pts, final_tets = _pts77, _tets77
                log.info(
                    "native_tet_smooth_interior",
                    n_moved=int(_n77),
                    pre_min=float(_pre77.min_q),
                    post_min=float(_post77.min_q),
                    accepted=bool(_acc77),
                )
        except Exception as exc:
            log.warning("native_tet_vvv7_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV7", dt_ms=int((time.perf_counter() - _t_vvv7) * 1000))
    try:
        from core.generator.native_tet.stellar import _count_neg_vol as _cnv7  # noqa: PLC0415
        _n7 = _cnv7(final_pts, final_tets)
        log.info("native_tet_neg_vol_track", pass_name="VVV7", n_neg=_n7, delta=_n7 - _val3_prev_neg)
        _val3_prev_neg = _n7
    except Exception:
        pass

    # VVV8 — boundary Laplacian + envelope projection (Loseille 2013 §3.2)
    _t_vvv8 = time.perf_counter()
    if not os.environ.get("AUTO_TESSELL_VVV8_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv8_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.laplacian import smooth_boundary_envelope as _sbe  # noqa: PLC0415
                from core.generator.native_tet.quality import snapshot as _qsnap78  # noqa: PLC0415
                _pre78 = _qsnap78(final_pts, final_tets)
                _pre78_n = final_tets.shape[0]
                _pts78, _tets78, _n78 = _sbe(
                    final_pts, final_tets,
                    V, F,
                    top_k=20,
                    n_iter=1,
                    min_quality_improvement=1e-6,
                )
                _post78 = _qsnap78(_pts78, _tets78)
                from core.generator.native_tet.boundary_invariant import (
                    check_boundary_invariant as _check_boundary78,
                )
                _boundary78 = _check_boundary78(
                    final_pts, final_tets, _pts78, _tets78,
                    "vvv8_boundary_laplacian_candidate", log_only=True,
                )
                _acc78 = (
                    _post78.min_q >= _pre78.min_q - 1e-6
                    and _post78.mean_q >= _pre78.mean_q - 1e-3
                    and _tets78.shape[0] == _pre78_n
                    and _boundary78.preserved
                )
                if _acc78:
                    final_pts, final_tets = _pts78, _tets78
                log.info(
                    "native_tet_smooth_boundary",
                    n_moved=int(_n78),
                    pre_min=float(_pre78.min_q),
                    post_min=float(_post78.min_q),
                    accepted=bool(_acc78),
                    boundary_preserved=bool(_boundary78.preserved),
                )
        except Exception as exc:
            log.warning("native_tet_vvv8_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV8", dt_ms=int((time.perf_counter() - _t_vvv8) * 1000))
    try:
        from core.generator.native_tet.stellar import _count_neg_vol as _cnv8  # noqa: PLC0415
        _n8 = _cnv8(final_pts, final_tets)
        log.info("native_tet_neg_vol_track", pass_name="VVV8", n_neg=_n8, delta=_n8 - _val3_prev_neg)
        _val3_prev_neg = _n8
    except Exception:
        pass

    # VVV9 — flip-1-4 Steiner insertion (non-Delaunay, fTetWild §3.4 simplified)
    _t_vvv9 = time.perf_counter()
    if not os.environ.get("AUTO_TESSELL_VVV9_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv9_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.stellar import insert_steiner_flip14 as _isf14  # noqa: PLC0415
                from core.generator.native_tet.quality import snapshot as _qsnap79  # noqa: PLC0415
                _pre79 = _qsnap79(final_pts, final_tets)
                _pre79_n = final_tets.shape[0]
                _pts79, _tets79, _n79 = _isf14(
                    final_pts, final_tets,
                    top_k=5,
                    min_quality_improvement=1e-3,
                    max_inserts=10,
                )
                _post79 = _qsnap79(_pts79, _tets79)
                _acc79 = (
                    _post79.min_q >= _pre79.min_q - 1e-6
                    and _post79.mean_q >= _pre79.mean_q - 1e-3
                    and _pre79_n <= _tets79.shape[0] <= _pre79_n + 4 * 10
                )
                if _acc79:
                    final_pts, final_tets = _pts79, _tets79
                log.info(
                    "native_tet_steiner_flip14",
                    n_inserted=int(_n79),
                    pre_min=float(_pre79.min_q),
                    post_min=float(_post79.min_q),
                    accepted=bool(_acc79),
                )
        except Exception as exc:
            log.warning("native_tet_vvv9_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV9", dt_ms=int((time.perf_counter() - _t_vvv9) * 1000))
    try:
        from core.generator.native_tet.stellar import _count_neg_vol as _cnv9  # noqa: PLC0415
        _n9 = _cnv9(final_pts, final_tets)
        log.info("native_tet_neg_vol_track", pass_name="VVV9", n_neg=_n9, delta=_n9 - _val3_prev_neg)
        _val3_prev_neg = _n9
    except Exception:
        pass

    # VVV10 — flip_face_23 strict per-flip guard (Klingner Table 1: 2→3 face flip)
    _t_vvv10 = time.perf_counter()
    if not os.environ.get("AUTO_TESSELL_VVV10_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv10_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.flip import flip_face_23 as _ff23  # noqa: PLC0415
                from core.generator.native_tet.quality import snapshot as _qsnap710  # noqa: PLC0415
                _pre710 = _qsnap710(final_pts, final_tets)
                _pre710_n = final_tets.shape[0]
                _pts710, _tets710, _n710 = _ff23(
                    final_pts, final_tets,
                    min_quality_improvement=1e-3,
                    max_flips=200,
                )
                _post710 = _qsnap710(_pts710, _tets710)
                _acc710 = (
                    _post710.min_q >= _pre710.min_q - 1e-6
                    and _post710.mean_q >= _pre710.mean_q - 1e-3
                    and _pre710_n - 1 <= _tets710.shape[0] <= _pre710_n + 200
                )
                if _acc710:
                    final_pts, final_tets = _pts710, _tets710
                log.info(
                    "native_tet_flip23",
                    n_app=int(_n710),
                    pre_min=float(_pre710.min_q),
                    post_min=float(_post710.min_q),
                    accepted=bool(_acc710),
                )
        except Exception as exc:
            log.warning("native_tet_vvv10_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV10", dt_ms=int((time.perf_counter() - _t_vvv10) * 1000))

    # VVV11 — 2-flip lookahead chain (Klingner 2008 §3.4 plateau escape)
    _t_vvv11 = time.perf_counter()
    if not os.environ.get("AUTO_TESSELL_VVV11_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv11_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.stellar import lookahead_2flip_chain as _la2  # noqa: PLC0415
                from core.generator.native_tet.quality import snapshot as _qsnap711  # noqa: PLC0415
                _pre711 = _qsnap711(final_pts, final_tets)
                _pts711, _tets711, _n711 = _la2(
                    final_pts, final_tets,
                    top_k=5,
                    min_quality_improvement=1e-3,
                    max_chains=5,
                )
                _post711 = _qsnap711(_pts711, _tets711)
                _acc711 = (
                    _post711.min_q >= _pre711.min_q - 1e-6
                    and _post711.mean_q >= _pre711.mean_q - 1e-3
                )
                if _acc711:
                    final_pts, final_tets = _pts711, _tets711
                log.info(
                    "native_tet_lookahead_chain",
                    n_chains=int(_n711),
                    pre_min=float(_pre711.min_q),
                    post_min=float(_post711.min_q),
                    accepted=bool(_acc711),
                )
        except Exception as exc:
            log.warning("native_tet_vvv11_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV11", dt_ms=int((time.perf_counter() - _t_vvv11) * 1000))

    # VVV12 — sliver tet detection + longest-edge midpoint split (V/L³ < 1e-3)
    _t_vvv12 = time.perf_counter()
    # Keep the diagnostic counters defined even when the small-mesh guard
    # skips the optional split pass.  Later report-only hooks share this scope.
    _n_sliver_pre = 0
    if not os.environ.get("AUTO_TESSELL_VVV12_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv12_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.stellar import (  # noqa: PLC0415
                    split_sliver_longest_edge as _ssl,
                    _count_slivers as _cs,
                    _count_offplane_sliver_candidates as _cofp,
                )
                from core.generator.native_tet.quality import snapshot as _qsnap712  # noqa: PLC0415
                _pre712 = _qsnap712(final_pts, final_tets)
                _n_sliver_pre = _cs(final_pts, final_tets)
                try:
                    _n_offp = int(_cofp(final_pts, final_tets, flatness_thresh=1e-2))
                except Exception:
                    _n_offp = -1
                _pts712, _tets712, _n712 = _ssl(
                    final_pts, final_tets,
                    sliver_ratio=1e-3,
                    min_quality_improvement=1e-3,
                    max_splits=20,
                )
                _post712 = _qsnap712(_pts712, _tets712)
                _acc712 = (
                    _post712.min_q >= _pre712.min_q - 1e-6
                    and _post712.mean_q >= _pre712.mean_q - 1e-3
                )
                if _acc712:
                    final_pts, final_tets = _pts712, _tets712
                log.info(
                    "native_tet_sliver_split",
                    n_sliver_detected=int(_n_sliver_pre),
                    n_split=int(_n712),
                    pre_min=float(_pre712.min_q),
                    post_min=float(_post712.min_q),
                    accepted=bool(_acc712),
                    n_offplane_candidates=_n_offp,
                    flatness_thresh=1e-2,
                )
                # VVV9D / beta2318 — off-plane Steiner application (env-gated).
                # 이전엔 dry-run 만 (mesh 미변경 + log only). beta2318 부터 env
                # AUTO_TESSELL_OFFPLANE_STEINER=1 시 실 apply + 단조 가드 검증
                # 후 결과 반영. n_offplane>0 이고 monotone (post_min ≥ pre_min -
                # 0.005 + post_mean ≥ pre_mean - 1e-3) 통과 시만 commit.
                if (
                    os.environ.get("AUTO_TESSELL_OFFPLANE_STEINER", "0") == "1"
                    and _n_offp > 0
                ):
                    try:
                        from core.generator.native_tet.stellar import (  # noqa: PLC0415
                            _apply_offplane_steiner_topK as _aost,
                        )
                        from core.generator.native_tet.quality import snapshot as _qsnap_ofp
                        _t_ofp0 = time.perf_counter()
                        _pre_ofp = _qsnap_ofp(final_pts, final_tets)
                        _pts_ofp, _tets_ofp, _n_ins = _aost(
                            final_pts, final_tets,
                            top_k=int(min(20, _n_offp)),
                            eps_factor=0.05,
                            flatness_thresh=1e-2,
                        )
                        _post_ofp = _qsnap_ofp(_pts_ofp, _tets_ofp)
                        _acc_ofp = (
                            _post_ofp.min_q >= _pre_ofp.min_q - 0.005
                            and _post_ofp.mean_q >= _pre_ofp.mean_q - 1e-3
                        )
                        _wall_ms = int((time.perf_counter() - _t_ofp0) * 1000)
                        if _acc_ofp and _n_ins > 0:
                            final_pts, final_tets = _pts_ofp, _tets_ofp
                        log.info(
                            "native_tet_offplane_steiner_apply",
                            n_offplane_candidates=int(_n_offp),
                            n_inserted=int(_n_ins),
                            pre_min=float(_pre_ofp.min_q),
                            post_min=float(_post_ofp.min_q),
                            accepted=bool(_acc_ofp),
                            wall_ms=_wall_ms,
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.warning(
                            "native_tet_offplane_steiner_skipped",
                            reason=str(exc)[:120],
                        )
                # VVV9F (beta2255) — dry-run exudation wire (mesh unchanged, log only)
                _VVV9F_EXUDATION_DRYRUN: bool = True  # R191/VVV9F #5 evidence emit (mesh discard, sliver-gated)
                if _VVV9F_EXUDATION_DRYRUN and _n_sliver_pre >= 1:
                    try:
                        from core.generator.native_tet.stellar import (  # noqa: PLC0415
                            _perturb_weights_topK as _pwk_dr,
                            _select_best_weight_assignment as _sbw_dr,
                        )
                        _t0 = time.perf_counter()
                        _W = _pwk_dr(final_pts, final_tets, n_samples=8, alpha=0.3, seed=0)
                        _bidx, _bmq = _sbw_dr(final_pts, final_tets, _W, alpha=0.3)
                        _wall_ms = int((time.perf_counter() - _t0) * 1000)
                        log.info(
                            "native_tet_vvv9f_dryrun",
                            n_samples=8,
                            alpha=0.3,
                            best_idx=int(_bidx),
                            best_min_q=float(_bmq),
                            wall_ms=int(_wall_ms),
                            mode="dry_run",
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.warning("native_tet_vvv9f_skipped", reason=str(exc)[:120])
                # VVV9H (beta2259) — Klingner edge-contract diagnostic hook (gate ON, log only)
                _VVV9H_DIAG: bool = True  # R194/VVV9H #3: evidence collection (gate ON → mesh ±0)
                if _VVV9H_DIAG and _n_sliver_pre >= 1:
                    try:
                        from core.generator.native_tet.stellar import (  # noqa: PLC0415
                            _klingner_edge_contract_candidates as _kecc_dr,
                        )
                        _pre_worst_q = float(_pre712.min_q)
                        _t0 = time.perf_counter()
                        _cands = _kecc_dr(
                            final_pts, final_tets,
                            q_max=0.2, l_max_factor=0.4, max_candidates=200,
                        )
                        _n_qi = sum(1 for c in _cands if c[2] >= _pre_worst_q)
                        _wall_ms = int((time.perf_counter() - _t0) * 1000)
                        log.info(
                            "native_tet_vvv9h_diag",
                            n_candidates=len(_cands),
                            n_safe=len(_cands),
                            n_quality_improving=_n_qi,
                            q_max=0.2,
                            l_max_factor=0.4,
                            wall_ms=_wall_ms,
                            mode="dry_run",
                        )
                        # VVV9H6 (beta2262) — apply dryrun gate ON (evidence collection, mesh unchanged)
                        _VVV9H_APPLY_DRYRUN: bool = True  # R197: flip ON
                        # VVV9H8 (beta2264) — real apply env-only gate (default OFF)
                        _VVV9H_APPLY_REAL: bool = bool(os.environ.get("AUTO_TESSELL_VVV9H_APPLY", "0") == "1")
                        if _VVV9H_APPLY_DRYRUN and _n_sliver_pre >= 1 and len(_cands) >= 1:
                            try:
                                from core.generator.native_tet.stellar import _apply_klingner_edge_contract_topK as _akec_dr  # noqa: PLC0415
                                _t0 = time.perf_counter()
                                _np, _nt, _st = _akec_dr(final_pts, final_tets, _cands, k=10)
                                _wall_ms = int((time.perf_counter() - _t0) * 1000)
                                log.info(
                                    "native_tet_vvv9h4_dryrun",
                                    n_apply_attempted=10,
                                    n_apply_accepted=int(_st.get("n_applied", 0)),
                                    n_reverted=int(_st.get("n_reverted", 0)),
                                    n_conflict=int(_st.get("n_conflict", 0)),
                                    wall_ms=_wall_ms,
                                    mode="dry_run",
                                )
                                # beta2319 — bug fix: stats key 가 "accepted" 가 아닌
                                # "n_applied" 임. 이전엔 _st.get("accepted") 가 항상
                                # False (key 없음) → env 가 켜져도 real apply 사실상
                                # dead code. _apply_klingner_edge_contract_topK 가
                                # 내부 monotone guard 로 reject 도 처리하므로
                                # n_applied > 0 만 보면 안전.
                                if _VVV9H_APPLY_REAL and int(_st.get("n_applied", 0)) > 0:
                                    final_pts, final_tets = _np, _nt
                                    log.info(
                                        "native_tet_vvv9h8_real_apply",
                                        n_apply=int(_st.get("n_applied", 0)),
                                        n_reverted=int(_st.get("n_reverted", 0)),
                                    )
                            except Exception as exc:  # noqa: BLE001
                                log.warning("native_tet_vvv9h4_skipped", reason=str(exc)[:120])
                    except Exception as exc:  # noqa: BLE001
                        log.warning("native_tet_vvv9h_skipped", reason=str(exc)[:120])
            # VVV9I #3 — envelope distance diagnostic hook (gate OFF by default)
            _VVV9I_DIAG: bool = False
            if _VVV9I_DIAG and _n_sliver_pre >= 1:
                _t0 = time.perf_counter()
                try:
                    from core.generator.native_tet.stellar import (  # noqa: PLC0415
                        _envelope_distance_to_triangles as _edt,
                    )
                    _dists = _edt(final_pts, V, F)
                    _eps = float(env.eps)
                    _n_invasion = int((_dists > _eps).sum())
                    _max_dist = float(_dists.max())
                    _wall_ms = int((time.perf_counter() - _t0) * 1000)
                    log.info(
                        "native_tet_vvv9i_diag",
                        n_pts=int(final_pts.shape[0]),
                        n_invasion=_n_invasion,
                        max_dist=_max_dist,
                        eps=_eps,
                        wall_ms=_wall_ms,
                        mode="dry_run",
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("native_tet_vvv9i_skipped", reason=str(exc)[:120])
            # VVV9J #6 — SLIM global-pass diagnostic hook (gate OFF by default, discard-only)
            _VVV9J_DIAG: bool = False
            if _VVV9J_DIAG and _n_sliver_pre >= 1:
                try:
                    from core.generator.native_tet.stellar import _slim_global_pass  # noqa: PLC0415
                    from core.generator.native_tet.quality import snapshot as _qsnap_j6  # noqa: PLC0415
                    _pre_j6 = _qsnap_j6(final_pts, final_tets)
                    _t0_j6 = time.perf_counter()
                    _res_j6 = _slim_global_pass(final_pts, final_tets, max_iters=2, eps=1e-6)
                    _post_j6 = _qsnap_j6(_res_j6["new_pts"], final_tets)
                    _wall_ms_j6 = int((time.perf_counter() - _t0_j6) * 1000)
                    log.info(
                        "native_tet_vvv9j_diag",
                        n_vertex=int(final_pts.shape[0]),
                        pre_worst_mq=float(_pre_j6.min_q),
                        post_worst_mq=float(_post_j6.min_q),
                        energy_delta=float(_res_j6["total_energy_delta"]),
                        wall_ms=_wall_ms_j6,
                        n_iters=int(_res_j6["n_iters_used"]),
                        mode="dry_run",
                    )
                    # env-gate apply (default OFF — empirical evidence pending)
                    _apply_env = os.environ.get("AUTO_TESSELL_VVV9J_APPLY", "0") == "1"
                    if not _apply_env:
                        log.info("native_tet_vvv9j_apply", mode="skip_env_off")
                    else:
                        from core.generator.native_tet.stellar import _count_neg_vol as _cnv_j6  # noqa: PLC0415
                        _pre_n_neg_j6 = _cnv_j6(final_pts, final_tets)
                        _post_n_neg_j6 = _cnv_j6(_res_j6["new_pts"], final_tets)
                        if _pre_j6.min_q > 0.05:
                            log.info("native_tet_vvv9j_apply", mode="reject_pre_gate",
                                     pre_min_q=float(_pre_j6.min_q))
                        elif _post_j6.min_q < _pre_j6.min_q:
                            log.info("native_tet_vvv9j_apply", mode="reject_min_q",
                                     pre_min_q=float(_pre_j6.min_q), post_min_q=float(_post_j6.min_q))
                        elif _post_j6.mean_q < _pre_j6.mean_q - 1e-3:
                            log.info("native_tet_vvv9j_apply", mode="reject_mean_q",
                                     pre_mean_q=float(_pre_j6.mean_q), post_mean_q=float(_post_j6.mean_q))
                        elif _post_n_neg_j6 != _pre_n_neg_j6:
                            log.info("native_tet_vvv9j_apply", mode="reject_neg_vol",
                                     pre_n_neg=_pre_n_neg_j6, post_n_neg=_post_n_neg_j6)
                        else:
                            final_pts = _res_j6["new_pts"]
                            log.info("native_tet_vvv9j_apply", mode="apply",
                                     pre_min_q=float(_pre_j6.min_q), post_min_q=float(_post_j6.min_q),
                                     pre_mean_q=float(_pre_j6.mean_q), post_mean_q=float(_post_j6.mean_q))
                    # discard _res_j6["new_pts"] if not applied — final_tets unchanged
                except Exception as exc:  # noqa: BLE001
                    log.warning("native_tet_vvv9j6_skipped", reason=str(exc)[:120])
            # VVV9K #5 — priority-queue main-loop diagnostic hook (gate OFF default, discard-only)
            _VVV9K_DIAG: bool = False  # evidence-only gate; default OFF
            _VVV9K_APPLY_REAL: bool = bool(os.environ.get("AUTO_TESSELL_VVV9K_APPLY", "0") == "1")
            if _VVV9K_DIAG and _n_sliver_pre >= 1:
                try:
                    from core.generator.native_tet.stellar import _priority_queue_main_loop  # noqa: PLC0415
                    from core.generator.native_tet.quality import snapshot as _qsnap_9k  # noqa: PLC0415
                    from core.generator.native_tet.stellar import _tet_quality_batch
                    _q_arr_9k = _tet_quality_batch(final_pts, final_tets)
                    _t0_9k = time.perf_counter()
                    _pts2, _tets2, _n_imp, _n_it, _delta = _priority_queue_main_loop(
                        final_pts, final_tets, _q_arr_9k, max_iters=10, time_budget_ms=100.0
                    )
                    _wall_ms_9k = int((time.perf_counter() - _t0_9k) * 1000)
                    log.info(
                        "native_tet_vvv9k_diag",
                        n_improved=int(_n_imp),
                        n_iters_used=int(_n_it),
                        total_delta=float(_delta),
                        wall_ms=_wall_ms_9k,
                        mode="dry_run",
                    )
                    # results discard — final_pts/final_tets unchanged unless AUTO_TESSELL_VVV9K_APPLY=1
                    # beta2320 — monotone guard 추가 (이전엔 _delta >= 0 + n_imp ≥ 1
                    #            만 — min_q drop 검사 없어 worst quality 악화 가능).
                    #            RRR2 와 동일 임계 (worst ≤ 0.015 drop + mean 향상)
                    #            로 안전성 ↑.
                    if _VVV9K_APPLY_REAL and _delta >= 0.0 and int(_n_imp) >= 1:
                        _wd_9k = 0.0
                        _mg_9k = 0.0
                        _ok_9k = False
                        try:
                            _pre_9k = _qsnap_9k(final_pts, final_tets)
                            _post_9k = _qsnap_9k(_pts2, _tets2)
                            _wd_9k = float(_pre_9k.min_q) - float(_post_9k.min_q)
                            _mg_9k = float(_post_9k.mean_q) - float(_pre_9k.mean_q)
                            _ok_9k = _wd_9k <= 0.015 and _mg_9k >= -1e-12
                        except Exception:
                            _ok_9k = False
                        if _ok_9k:
                            final_pts, final_tets = _pts2, _tets2
                            log.info(
                                "native_tet_vvv9k7_real_apply",
                                n_improved=int(_n_imp),
                                total_delta=float(_delta),
                                worst_drop=round(_wd_9k, 4),
                                mean_gain=round(_mg_9k, 4),
                                wall_ms=_wall_ms_9k,
                                mode="apply",
                            )
                        else:
                            log.info(
                                "native_tet_vvv9k7_rejected",
                                worst_drop=round(_wd_9k, 4),
                                mean_gain=round(_mg_9k, 4),
                            )
                except Exception as exc:  # noqa: BLE001
                    log.warning("native_tet_vvv9k_skipped", reason=str(exc)[:120])
            # VVV9N #2 — line-comparison helper diagnostic hook (gate OFF default)
            _VVV9N_DIAG: bool = True  # VVV9N #3: default ON
            try:
                from core.generator.native_tet.quality import snapshot as _qsnap_9n  # noqa: PLC0415
                _worst_pre = float(_qsnap_9n(final_pts, final_tets).min_q)
            except Exception:
                _worst_pre = 1.0
            if _VVV9N_DIAG and _n_sliver_pre >= 1 and _worst_pre < 0.10:
                try:
                    from core.generator.native_tet.stellar import _evidence_compare_lines  # noqa: PLC0415
                    _t0_9n = time.perf_counter()
                    _lines = _evidence_compare_lines(final_pts, final_tets)
                    _wall_ms_9n = int((time.perf_counter() - _t0_9n) * 1000)
                    log.info(
                        "native_tet_vvv9n_diag",
                        lines_total=int(len(_lines)),
                        wall_ms=_wall_ms_9n,
                        mode="dry_run",
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("native_tet_vvv9n_skipped", reason=str(exc)[:120])
            else:
                log.info("native_tet_vvv9n_skipped_guard", n_sliver_pre=int(_n_sliver_pre), worst_pre=float(_worst_pre))
            # VVV9P #2 — multi-face removal diagnostic hook (gate OFF default, R226 ON flip)
            _VVV9P_DIAG: bool = False  # evidence-only gate; default OFF
            if _VVV9P_DIAG and _n_sliver_pre >= 1 and _worst_pre < 0.10:
                try:
                    from core.generator.native_tet.stellar import _multi_face_removal_candidates as _mfrc_9p  # noqa: PLC0415
                    _t0_9p = time.perf_counter()
                    _cands = _mfrc_9p(final_pts, final_tets, k_worst=64, q_thr=0.3)
                    # VVV9P #5 — env-only real-apply gate (R228)
                    _VVV9P_APPLY_REAL: bool = bool(os.environ.get("AUTO_TESSELL_VVV9P_APPLY", "0") == "1")
                    from core.generator.native_tet.stellar import _multi_face_removal_apply as _mfra_9p  # noqa: PLC0415
                    _pts2, _tets2, _n_imp, _delta = _mfra_9p(final_pts, final_tets, candidates=_cands)
                    # beta2321 — VVV9K (beta2320) 와 동일 monotone guard 표준화.
                    # 이전엔 _delta >= 0 + n_imp ≥ 1 만 — multi-face removal 이
                    # worst min_q 악화시킬 위험. RRR2 임계 (worst -0.015 + mean
                    # improve) 추가.
                    if _VVV9P_APPLY_REAL and _delta >= 0.0 and int(_n_imp) >= 1:
                        from core.generator.native_tet.quality import snapshot as _qsnap_9p
                        _wd_9p = 0.0
                        _mg_9p = 0.0
                        _ok_9p = False
                        try:
                            _pre_9p = _qsnap_9p(final_pts, final_tets)
                            _post_9p = _qsnap_9p(_pts2, _tets2)
                            _wd_9p = float(_pre_9p.min_q) - float(_post_9p.min_q)
                            _mg_9p = float(_post_9p.mean_q) - float(_pre_9p.mean_q)
                            _ok_9p = _wd_9p <= 0.015 and _mg_9p >= -1e-12
                        except Exception:
                            _ok_9p = False
                        if _ok_9p:
                            final_pts, final_tets = _pts2, _tets2
                            log.info(
                                "native_tet_vvv9p5_real_apply",
                                n_improved=int(_n_imp),
                                delta=float(_delta),
                                worst_drop=round(_wd_9p, 4),
                                mean_gain=round(_mg_9p, 4),
                                mode="real_apply",
                            )
                        else:
                            log.info(
                                "native_tet_vvv9p5_rejected",
                                worst_drop=round(_wd_9p, 4),
                                mean_gain=round(_mg_9p, 4),
                            )
                    _wall_ms_9p = int((time.perf_counter() - _t0_9p) * 1000)
                    _top_q = float(_cands[0]["min_q"]) if _cands else 1.0
                    log.info(
                        "native_tet_vvv9p_diag",
                        n_candidates=int(len(_cands)),
                        top_quality=_top_q,
                        wall_ms=_wall_ms_9p,
                        mode="dry_run",
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("native_tet_vvv9p_skipped", reason=str(exc)[:120])
            else:
                log.info("native_tet_vvv9p_skipped_guard", n_sliver_pre=int(_n_sliver_pre), worst_pre=float(_worst_pre))
        except Exception as exc:
            log.warning("native_tet_vvv12_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV12", dt_ms=int((time.perf_counter() - _t_vvv12) * 1000))
    try:
        from core.generator.native_tet.stellar import _count_neg_vol as _cnv12  # noqa: PLC0415
        _n12 = _cnv12(final_pts, final_tets)
        log.info("native_tet_neg_vol_track", pass_name="VVV12", n_neg=_n12, delta=_n12 - _val3_prev_neg)
        _val3_prev_neg = _n12
    except Exception:
        pass

    # VVV13 — anisotropic tet AR longest-edge split (fTetWild §3.2 style)
    _t_vvv13 = time.perf_counter()
    if not os.environ.get("AUTO_TESSELL_VVV13_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv13_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.stellar import (  # noqa: PLC0415
                    split_anisotropic_tet_edges as _sate,
                    _count_anisotropic as _ca13,
                )
                from core.generator.native_tet.quality import snapshot as _qsnap713  # noqa: PLC0415
                _pre713 = _qsnap713(final_pts, final_tets)
                _n_aniso_pre = _ca13(final_pts, final_tets, ar_threshold=5.0)
                _pts713, _tets713, _n713 = _sate(
                    final_pts, final_tets,
                    ar_threshold=5.0,
                    min_quality_improvement=1e-3,
                    max_splits=20,
                )
                _post713 = _qsnap713(_pts713, _tets713)
                _acc713 = (
                    _post713.min_q >= _pre713.min_q - 1e-6
                    and _post713.mean_q >= _pre713.mean_q - 1e-3
                )
                if _acc713:
                    final_pts, final_tets = _pts713, _tets713
                log.info(
                    "native_tet_aniso_split",
                    n_aniso_detected=int(_n_aniso_pre),
                    n_split=int(_n713),
                    pre_min=float(_pre713.min_q),
                    post_min=float(_post713.min_q),
                    accepted=bool(_acc713),
                )
        except Exception as exc:
            log.warning("native_tet_vvv13_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV13", dt_ms=int((time.perf_counter() - _t_vvv13) * 1000))
    try:
        from core.generator.native_tet.stellar import _count_neg_vol as _cnv13  # noqa: PLC0415
        _n13 = _cnv13(final_pts, final_tets)
        log.info("native_tet_neg_vol_track", pass_name="VVV13", n_neg=_n13, delta=_n13 - _val3_prev_neg)
        _val3_prev_neg = _n13
    except Exception:
        pass

    # VVV14 — face-centroid Steiner insertion (worst-face-fan, 1+1→6 sub-tets)
    _t_vvv14 = time.perf_counter()
    if not os.environ.get("AUTO_TESSELL_VVV14_OFF"):
        try:
            if final_tets.shape[0] < 500:
                log.info("vvv14_skipped_small_mesh", n_tets=int(final_tets.shape[0]))
            else:
                from core.generator.native_tet.stellar import (  # noqa: PLC0415
                    insert_face_centroid_steiner as _ifcs,
                )
                from core.generator.native_tet.quality import snapshot as _qsnap714  # noqa: PLC0415
                _pre714 = _qsnap714(final_pts, final_tets)
                _pts714, _tets714, _n714 = _ifcs(
                    final_pts, final_tets,
                    top_k=5,
                    min_quality_improvement=1e-3,
                    max_inserts=10,
                )
                _post714 = _qsnap714(_pts714, _tets714)
                # Triple monotone global revert.
                _acc714 = (
                    _post714.min_q >= _pre714.min_q - 1e-6
                    and _post714.mean_q >= _pre714.mean_q - 1e-3
                )
                if _acc714:
                    final_pts, final_tets = _pts714, _tets714
                log.info(
                    "native_tet_face_steiner",
                    n_inserted=int(_n714),
                    pre_min=float(_pre714.min_q),
                    post_min=float(_post714.min_q),
                    accepted=bool(_acc714),
                )
        except Exception as exc:
            log.warning("native_tet_vvv14_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VVV14", dt_ms=int((time.perf_counter() - _t_vvv14) * 1000))
    try:
        from core.generator.native_tet.stellar import _count_neg_vol as _cnv14  # noqa: PLC0415
        _n14 = _cnv14(final_pts, final_tets)
        log.info("native_tet_neg_vol_track", pass_name="VVV14", n_neg=_n14, delta=_n14 - _val3_prev_neg)
        _val3_prev_neg = _n14
    except Exception:
        pass

    _boundary_audit_probe("post_vvv14")

    # TET_QUALITY1 (beta2141) — non-ortho local post-pass (mirror HEX_QUALITY1).
    # env AUTO_TESSELL_TET_QUALITY1_OFF disables. Default ON.
    _t_tq1 = time.perf_counter()
    if (
        final_tets.shape[0] >= 500
        and not os.environ.get("AUTO_TESSELL_TET_QUALITY1_OFF")
    ):
        try:
            from core.generator.native_tet.laplacian import (  # noqa: PLC0415
                reduce_nonortho_tet as _rnt,
            )
            from core.generator.native_tet.quality import snapshot as _qsnap_tq1  # noqa: PLC0415
            _pre_tq1 = _qsnap_tq1(final_pts, final_tets)
            _pts_tq1, _tets_tq1, _n_tq1 = _rnt(final_pts, final_tets)
            _post_tq1 = _qsnap_tq1(_pts_tq1, _tets_tq1)
            # Triple monotone global revert: min_q must not drop.
            if _post_tq1.min_q >= _pre_tq1.min_q - 1e-6:
                final_pts, final_tets = _pts_tq1, _tets_tq1
                log.info(
                    "tet_quality_postpass",
                    n_moved=int(_n_tq1),
                    pre_min_q=round(float(_pre_tq1.min_q), 4),
                    post_min_q=round(float(_post_tq1.min_q), 4),
                )
            else:
                log.info(
                    "tet_quality_postpass",
                    n_moved=0,
                    pre_min_q=round(float(_pre_tq1.min_q), 4),
                    post_min_q=round(float(_post_tq1.min_q), 4),
                    reverted=True,
                )
        except Exception as exc:
            log.debug("native_tet_quality1_skipped", reason=str(exc)[:120])
    log.info("native_tet_pass_timing", pass_name="TET_QUALITY1", dt_ms=int((time.perf_counter() - _t_tq1) * 1000))

    _boundary_audit_probe("post_tet_quality1")

    # beta1530 (V3) — 외부 tet 제거: 입력 surface 외부에 centroid 가 있는 tet drop.
    if enable_boundary_clip:
        try:
            from core.generator.native_tet.boundary_clip import (
                clip_to_input_surface,
            )
            final_pts, final_tets, clip_info = clip_to_input_surface(
                final_pts, final_tets, V, F,
                inside_threshold=float(boundary_clip_threshold),
            )
            log.info(
                "native_tet_boundary_clip",
                dropped=clip_info.n_dropped,
                tets_after=clip_info.n_tets_after,
                face_ratio=round(clip_info.face_ratio_after, 3),
            )
        except Exception as exc:
            log.debug("native_tet_boundary_clip_skipped", reason=str(exc))

    # beta1460 (T2) — 입력 surface vertex 가 결과 mesh 의 같은 좌표를 유지하는지
    # 강제 보정. final_pts 의 [0:n_surface] 가 V 와 일치해야 hausdorff 측정이
    # 의미 있음. 일부 path (Phase A smooth) 가 surface vertex 위치를 살짝 옮길
    # 수 있으니 명시적으로 복원.
    try:
        n_surface_in = int(V.shape[0])
        if (
            final_pts.shape[0] >= n_surface_in
            and not np.allclose(final_pts[:n_surface_in], V, atol=1e-9)
        ):
            log.info(
                "native_tet_surface_snap_restore",
                max_diff=float(
                    np.linalg.norm(final_pts[:n_surface_in] - V, axis=1).max()
                ),
            )
            final_pts = final_pts.copy()
            final_pts[:n_surface_in] = V
    except Exception:
        pass

    # beta1420 (Q4) — 통합 PASS gate 산출 (cdt_ratio + hausdorff + quality).
    grade = "?"
    cdt_ratio_val = -1.0
    cdt_face_ratio_val = -1.0
    plane_cov_val = -1.0
    plane_area_cov_val = -1.0
    haus_rel = -1.0
    # P4-B-5k (beta2245k) — _phase_bc_skip 시 pass_gate 자체가 bottleneck.
    # Phase A 9859 tet × 2536 input F 의 hausdorff + cdt_check 가 3+ 분.
    # 어차피 grade 가 D 라서 P4-C 가 호출됨. 여기서 grade="D" 로 하드코딩하고 skip.
    try:
        if _phase_bc_skip:
            grade = "D"
            raise RuntimeError("_phase_bc_skip")
        from core.generator.native_tet.cdt_check import (
            check_edge_recovery, check_edge_recovery_chained,
            cdt_ratio as _cdt_ratio, cdt_face_ratio as _cdt_face_ratio,
        )
        from core.generator.native_tet.hausdorff import hausdorff_vs_input
        from core.generator.native_tet.plane_coverage import plane_coverage

        # T1 — chain-based 검사 (subdivided edge 도 회복으로 인정).
        try:
            cdt_r = check_edge_recovery_chained(
                _input_source_vertices,
                _input_source_faces,
                final_pts,
                final_tets,
            )
        except Exception:
            cdt_r = check_edge_recovery(_input_source_faces, final_tets)
        cdt_ratio_val = float(_cdt_ratio(cdt_r))
        # face ratio (strict).
        cdt_strict = check_edge_recovery(_input_source_faces, final_tets)
        cdt_face_ratio_val = float(_cdt_face_ratio(cdt_strict))
        # V1 — plane coverage (fTetWild-style).
        try:
            pc = plane_coverage(
                _input_source_vertices,
                _input_source_faces,
                final_pts,
                final_tets,
            )
            plane_cov_val = float(pc.plane_coverage)
            plane_area_cov_val = float(pc.area_coverage)
        except Exception:
            pass

        haus = hausdorff_vs_input(
            _input_source_vertices,
            _input_source_faces,
            final_pts,
            final_tets,
            n_samples_per_tri=2,
        )
        bbox = _input_source_vertices.max(
            axis=0,
        ) - _input_source_vertices.min(axis=0)
        diag = float(np.linalg.norm(bbox)) + 1e-30
        haus_rel = float(haus.h_symmetric / diag)

        # V3 — plane_coverage 가 fTetWild 정합 메트릭. A 는 plane_coverage 우선.
        mean_q = float(getattr(final_quality, "mean_q", 0.0)) if final_quality else 0.0
        if (
            plane_cov_val >= 0.95
            and plane_area_cov_val >= 0.95
            and mean_q >= 0.25
        ):
            grade = "A"
        elif (
            plane_cov_val >= 0.8
            and plane_area_cov_val >= 0.8
            and mean_q >= 0.18
        ):
            grade = "B"
        elif (
            (plane_cov_val >= 0.5 or cdt_ratio_val >= 0.5)
            and mean_q >= 0.10
        ):
            grade = "C"
        else:
            grade = "D"
        log.info(
            "native_tet_pass_gate",
            grade=grade,
            cdt_ratio=round(cdt_ratio_val, 3),
            cdt_face_ratio=round(cdt_face_ratio_val, 3),
            plane_coverage=round(plane_cov_val, 3),
            plane_area_coverage=round(plane_area_cov_val, 3),
            hausdorff_rel=round(haus_rel, 5),
            mean_q=round(mean_q, 3),
        )
    except Exception as exc:
        log.debug("native_tet_pass_gate_skipped", reason=str(exc))

    # P4-B-5 (beta2245d) — _phase_bc_skip 으로 mutate 된 env 변수 복원.
    # P4-C 가 처리하기 전 / 함수 종료 후 호출자 영향 없도록.
    if _phase_bc_skip:
        try:
            for _k, _v in _orig_env.items():
                if _v is None:
                    os.environ.pop(_k, None)
                else:
                    os.environ[_k] = _v
        except Exception:
            pass

    # KLINGNER-FULL / beta2794 — Klingner §4 full topology sweep.
    # collapse → split → flip(3-2/4-4) → smooth — 4-stage cycle, n_cycles=2.
    # GAP-SELF AMIPS 직전 통합 sweep 으로 self-impl mesh 의 cross-stage 효과 누적.
    # 자체 monotone guard + plateau early-exit.
    if grade in ("B", "C", "D", "?") and final_tets.shape[0] > 100:
        try:
            from core.generator.native_tet.klingner_full_sweep import (
                klingner_full_sweep,
            )
            _lock_kf = np.arange(int(min(V.shape[0], final_pts.shape[0])),
                                  dtype=np.int64)
            _new_pts_kf, _new_tets_kf, _kf_res = klingner_full_sweep(
                final_pts, final_tets,
                n_cycles=2,
                locked_vertex_ids=_lock_kf,
                monotone_min_drop=0.020,
            )
            if _kf_res.accepted:
                final_pts = _new_pts_kf
                final_tets = _new_tets_kf
                log.info(
                    "native_tet_klingner_full_sweep",
                    cycles=_kf_res.n_cycles_used,
                    mq_before=round(_kf_res.pre_mean_q, 4),
                    mq_after=round(_kf_res.post_mean_q, 4),
                    n_collapse=_kf_res.n_collapse,
                    n_split=_kf_res.n_split,
                    n_flip32=_kf_res.n_flip32,
                    n_flip44=_kf_res.n_flip44,
                    elapsed_s=round(_kf_res.elapsed_s, 2),
                )
                # grade 재평가.
                if _kf_res.post_mean_q >= 0.20:
                    grade = "A"
                elif _kf_res.post_mean_q >= 0.15:
                    grade = "B"
                elif _kf_res.post_mean_q >= 0.10:
                    grade = "C"
        except Exception as exc:
            log.debug("native_tet_klingner_full_skipped", reason=str(exc)[:120])

    # METRIC-TENSOR / beta2803 — curvature anisotropic metric guided sweep.
    # surface curvature → anisotropic metric tensor → collapse/split 우선순위.
    # self-impl tet 단독 grade A 도달 시도.
    if grade in ("B", "C", "D", "?") and final_tets.shape[0] > 100:
        try:
            from core.generator.native_tet.metric_tensor_sweep import (
                metric_tensor_sweep, compute_curvature_metric,
            )
            from core.generator.native_tet.plane_coverage import _tet_boundary_faces
            _EDGES_M = np.array([[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]], dtype=np.int64)
            _e_idx_m = final_tets[:, _EDGES_M]
            _e_lens_m = np.linalg.norm(
                final_pts[_e_idx_m[..., 1]] - final_pts[_e_idx_m[..., 0]], axis=-1,
            )
            _h_target_m = float(np.median(_e_lens_m))
            _metric = compute_curvature_metric(
                V, F, n_total_v=int(final_pts.shape[0]),
                base_edge=_h_target_m, aniso_factor=2.0,
            )
            _ns_m = int(min(V.shape[0], final_pts.shape[0]))
            _lock_m = np.unique(_tet_boundary_faces(final_tets)).astype(np.int64)
            _metric_source_txn_enabled = (
                os.environ.get("AUTO_TESSELL_TET_METRIC_SOURCE_TXN", "0") == "1"
            )
            if _metric_source_txn_enabled:
                # Snapshot only this optional mutator.  The source audit below
                # must be able to restore these exact arrays without repair.
                from core.generator.native_tet.surface_transaction_gate import (
                    apply_metric_surface_transaction,
                )

                _pre_pts_m = final_pts.copy()
                _pre_tets_m = final_tets.copy()
            else:
                _pre_pts_m = final_pts
                _pre_tets_m = final_tets
            try:
                _new_pts_m, _new_tets_m, _mt_res = metric_tensor_sweep(
                    final_pts, final_tets,
                    n_cycles=2,
                    target_edge=_h_target_m,
                    metric=_metric,
                    locked_vertex_ids=_lock_m,
                    monotone_min_drop=0.025,
                )
            except Exception:
                if _metric_source_txn_enabled:
                    final_pts = _pre_pts_m
                    final_tets = _pre_tets_m
                raise

            _metric_sweep_committed = bool(_mt_res.accepted)
            if _metric_sweep_committed:
                from core.generator.native_tet.surface_transaction_gate import (
                    apply_metric_topology_transaction,
                )

                _new_pts_m, _new_tets_m, _metric_topology_txn = (
                    apply_metric_topology_transaction(
                        _input_source_vertices,
                        _input_source_faces,
                        _pre_pts_m,
                        _pre_tets_m,
                        _new_pts_m,
                        _new_tets_m,
                    )
                )
                _metric_sweep_committed = _metric_topology_txn.accepted
                if not _metric_sweep_committed:
                    _metric_topology_audit = _metric_topology_txn.audit
                    log.info(
                        "native_tet_metric_topology_txn_revert",
                        reason=_metric_topology_txn.reason,
                        n_nonmanifold_edges=(
                            _metric_topology_audit.boundary.n_nonmanifold_edges
                            if _metric_topology_audit is not None
                            else None
                        ),
                        n_open_edges=(
                            _metric_topology_audit.boundary.n_open_edges
                            if _metric_topology_audit is not None
                            else None
                        ),
                        component_bijective=(
                            _metric_topology_audit.components.bijective
                            if _metric_topology_audit is not None
                            else None
                        ),
                    )
            if _metric_source_txn_enabled:
                if _metric_sweep_committed:
                    final_pts, final_tets, _metric_surface_txn = apply_metric_surface_transaction(
                        _input_source_vertices,
                        _input_source_faces,
                        _pre_pts_m,
                        _pre_tets_m,
                        _new_pts_m,
                        _new_tets_m,
                    )
                    _metric_sweep_committed = _metric_surface_txn.accepted
                    if not _metric_sweep_committed:
                        log.info(
                            "native_tet_metric_surface_txn_revert",
                            reason=_metric_surface_txn.reason,
                            pre_hausdorff_relative=_metric_surface_txn.pre.hausdorff_relative,
                            post_hausdorff_relative=_metric_surface_txn.post.hausdorff_relative,
                            pre_plane_coverage=_metric_surface_txn.pre.plane_coverage,
                            post_plane_coverage=_metric_surface_txn.post.plane_coverage,
                            pre_area_coverage=_metric_surface_txn.pre.area_coverage,
                            post_area_coverage=_metric_surface_txn.post.area_coverage,
                        )
                else:
                    # Also defend the opt-in snapshot from an unexpected
                    # in-place mutator that reports its own rejection.
                    final_pts = _pre_pts_m
                    final_tets = _pre_tets_m
            elif _metric_sweep_committed:
                final_pts = _new_pts_m
                final_tets = _new_tets_m

            if _metric_sweep_committed:
                log.info(
                    "native_tet_metric_tensor_sweep",
                    cycles=_mt_res.n_cycles_used,
                    aniso_max=round(_mt_res.metric_aniso_max, 3),
                    mq_before=round(_mt_res.pre_mean_q, 4),
                    mq_after=round(_mt_res.post_mean_q, 4),
                    n_collapse=_mt_res.n_collapse,
                    n_split=_mt_res.n_split,
                    n_flip=_mt_res.n_flip,
                )
                if _mt_res.post_mean_q >= 0.20:
                    grade = "A"
                elif _mt_res.post_mean_q >= 0.15:
                    grade = "B"
                elif _mt_res.post_mean_q >= 0.10:
                    grade = "C"
        except Exception as exc:
            log.debug("native_tet_metric_tensor_skipped", reason=str(exc)[:120])

    # GAP-SELF / beta2791 — final aggressive AMIPS multistage smoothing.
    # P4-C 진입 직전, grade<A 인 self-impl mesh 에 강력한 multi-alpha sweep 적용.
    # alphas=(0.5, 1.0, 2.0, 4.0) — 점진적으로 sliver energy weight 강화.
    # n_iter_per=2 (보통 1) → 더 깊은 minimization. monotone guard (자체 보유).
    # P4-C fallback 직전 self-impl 의 마지막 회복 기회 — 외부 fallback 없을 때
    # (env P4C OFF) 에도 self-impl 단독 grade A 향상 가능.
    if grade in ("B", "C", "D", "?"):
        try:
            from core.generator.native_tet.amips import smooth_amips_multistage as _ams
            from core.generator.native_tet.quality import snapshot as _qs_self
            from core.generator.native_tet.plane_coverage import _tet_boundary_faces
            _q_pre_self = _qs_self(final_pts, final_tets)
            _mq_pre_self = float(_q_pre_self.mean_q)
            if final_tets.shape[0] > 100:
                _lock_ids_self = np.unique(_tet_boundary_faces(final_tets)).astype(np.int64)
                _, _new_pts_self = _ams(
                    final_pts, final_tets,
                    locked_vertex_ids=_lock_ids_self,
                    alphas=(0.5, 1.0, 2.0, 4.0),
                    n_iter_per=2,
                    step_init=0.1,
                )
                _q_post_self = _qs_self(_new_pts_self, final_tets)
                _mq_post_self = float(_q_post_self.mean_q)
                _min_drop_self = float(_q_pre_self.min_q) - float(_q_post_self.min_q)
                # 채택: mean 향상 + worst drop ≤ 0.020 (RRR2 임계).
                if _mq_post_self > _mq_pre_self and _min_drop_self <= 0.020:
                    final_pts = _new_pts_self
                    log.info(
                        "native_tet_gap_self_amips_multistage",
                        mq_before=round(_mq_pre_self, 4),
                        mq_after=round(_mq_post_self, 4),
                        min_drop=round(_min_drop_self, 5),
                    )
                    # grade 재평가.
                    if _mq_post_self >= 0.20:
                        grade = "A"
                    elif _mq_post_self >= 0.15:
                        grade = "B"
                    elif _mq_post_self >= 0.10:
                        grade = "C"
        except Exception as exc:
            log.debug("native_tet_gap_self_skipped", reason=str(exc)[:120])

    # P4-C (beta2236) — grade<A 시 pytetwild fallback.
    # native_tet 의 self-구현 algorithm 이 grade A 도달 못한 mesh 만 fTetWild
    # python wrapper (pytetwild) 로 재생성. 결과 final_pts/final_tets 교체
    # → 다음 단계 (polymesh_writer + native_bl) 그대로 작동.
    # CLAUDE.md 정책 일부 완화 (외부 의존 — pytetwild 는 이미 pyproject.toml 에).
    #
    # 2026-07-17 — non-skip 경로 버그: _phase_bc_skip=False 이면 polyMesh 는
    # 이미 line 1887 에서 (P4-C 이전 mesh 로) 쓰여 있다.  P4-C 가
    # final_pts/final_tets 를 grade-A mesh 로 재할당해도 아래 4428 의 re-write
    # 가 _phase_bc_skip 만 검사해 실행되지 않아, on-disk polyMesh 는 P4-C 이전의
    # 저품질 mesh 로 남는다 (실린더: 8601-cell 충실 mesh → 1841-cell 왜곡 mesh).
    # 이 플래그로 "P4-C 가 mesh 를 재할당했다" 를 추적해 re-write 를 강제한다.
    _p4c_rewrote = False
    # 2026-07-18 — dead-zone [0.15, 0.18) 봉합 (cylinder 간헐 FAIL 근본 원인).
    # _phase_bc_skip 은 Phase-A mean_q < 0.18 에서 발동해 복구 패스 18개를
    # "P4-C 가 구제할 것" 이라는 전제로 스킵한다 (reason=
    # below_threshold_p4c_fallback_will_rescue).  그런데 skip 으로 가드되지
    # 않은 KLINGNER sweep 이 mean_q 를 0.15~0.18 로 올려 grade 를 C→B 로
    # 승격시키면, 아래 게이트(grade C/D/? = mean_q<0.15)가 P4-C 를 건너뛴다 —
    # 스킵은 했는데 구제는 안 오는 구멍.  그 축퇴 mesh (min_q=0, skew~1e15,
    # 곡면벽 dev 0.359) 가 `_phase_bc_skip or _p4c_rewrote` write 조건으로
    # disk 에 그대로 쓰였다.  따라서 skip 이 발동했으면 grade 와 무관하게
    # P4-C 를 반드시 시도한다 (전제의 의무 이행).
    # 단, skip-강제 진입은 target_cells 가 있을 때만 — target 없이 cap
    # (bare max_cells) 만 준 경우 P4-C 는 env 기본 elf 로 크기를 정해
    # ~9.8k 셀로 부풀린다 (cap≠target 계약 위반, test_harness_bare_max_cells
    # 실측).  target 이 있으면 P4-C 가 N-RESPECT elf 로 크기를 지키므로 안전.
    if (
        (
            grade in ("C", "D", "?")
            or (_phase_bc_skip and target_cells is not None and int(target_cells) > 0)
        )
        and os.environ.get("AUTO_TESSELL_P4C_PYTETWILD", "1") != "0"
    ):
        try:
            import pytetwild  # noqa: PLC0415
            from core.generator.native_tet.quality import snapshot as _qsnap_fb  # noqa: PLC0415

            _bbox = V.max(axis=0) - V.min(axis=0)
            _diag_fb = float(np.linalg.norm(_bbox))
            # GAP-MULTI / beta2775 — multi-fallback chain.
            # P4D 1차 (fTetWild 권장 default) → grade<A 면 2차 (tighter eps + smaller elf) →
            # 3차 (envelope 더 작게, 더 많은 opt). 각 단계 채택 시 break.
            _grade_old = grade
            _mq_old = float(getattr(final_quality, "mean_q", 0.0)) if final_quality else 0.0
            _n_cells_old = int(final_tets.shape[0])

            # N-RESPECT (2026-07) — P4-C 가 사용자의 목표 셀 수 N 을 무시하던 버그.
            # 이전엔 edge_length_fac 이 항상 0.05 (bbox diag 대비 고정 비율) 라서,
            # self-impl 이 grade A 에 못 미쳐 P4-C 가 발동하면 N 과 무관한 셀 수가
            # 나왔다 (unit cube N=100 → 35 cell grade D → P4-C 가 ~9.9k cell 로 교체,
            # 99× overshoot).  pytetwild 의 edge_length_fac 은 fTetWild `-l` 과 동일한
            # "ideal_edge_length / bbox_diag" 이므로, N 에서 유도된 target_edge_length
            # 을 bbox diag 로 나누면 그대로 쓸 수 있다.
            # N 이 없으면 (target_cells=None) 기존 env 기본값 0.05 를 그대로 유지.
            _elf_env = float(os.environ.get("AUTO_TESSELL_P4C_EDGE_LEN_FAC", "0.05"))
            _elf_base = _elf_env
            _elf_from_n = False
            if (
                os.environ.get("AUTO_TESSELL_P4C_EDGE_FROM_TARGET", "1") != "0"
                and target_cells is not None
                and int(target_cells) > 0
                and target_edge_length is not None
                and float(target_edge_length) > 0.0
                and _diag_fb > 0.0
            ):
                # fTetWild 권장 범위로 clamp — 너무 작으면 셀 폭증, 너무 크면
                # envelope 를 못 채운다.
                _elf_base = float(
                    min(max(float(target_edge_length) / _diag_fb, 0.002), 0.5)
                )
                _elf_from_n = True
                log.info(
                    "native_tet_p4c_edge_from_target_cells",
                    target_cells=int(target_cells),
                    target_edge=round(float(target_edge_length), 6),
                    bbox_diag=round(_diag_fb, 6),
                    edge_length_fac=round(_elf_base, 5),
                    edge_length_fac_default=_elf_env,
                )

            # 3 단계 파라미터 schedule. base default + tighter retries.
            # N-RESPECT: N 유도 모드에선 retry tier 도 base 의 상대 비율 (0.6× / 0.4×
            # — 기존 절대값 0.05/0.03/0.02 와 같은 비율) 로 스케일한다.  절대값을
            # 그대로 쓰면 tier2/3 가 다시 N 을 무시하고 셀을 폭증시킨다.
            _p4d_schedule = [
                # (edge_len_fac, epsilon, stop_energy, num_opt_iter, label)
                (
                    _elf_base,
                    float(os.environ.get("AUTO_TESSELL_P4C_EPSILON", "0.001")),
                    float(os.environ.get("AUTO_TESSELL_P4C_STOP_ENERGY", "10.0")),
                    int(os.environ.get("AUTO_TESSELL_P4C_NUM_OPT_ITER", "80")),
                    "tier1_default",
                ),
                # tier 2: tighter envelope + smaller edge → 더 정밀 mesh.
                (_elf_base * 0.6 if _elf_from_n else 0.03, 5e-4, 8.0, 120, "tier2_tighter"),
                # tier 3: 가장 공격적 envelope (extreme mesh 회복).
                (_elf_base * 0.4 if _elf_from_n else 0.02, 2e-4, 5.0, 200, "tier3_aggressive"),
            ]

            _best_v: np.ndarray | None = None
            _best_f: np.ndarray | None = None
            _best_q = None
            _best_grade = grade
            _best_label = ""

            for _elf, _eps, _se, _noi, _label in _p4d_schedule:
                _t_fb0 = time.perf_counter()
                try:
                    _tw_v, _tw_f = pytetwild.tetrahedralize(
                        V.astype(np.float64),
                        F.astype(np.int32),
                        edge_length_fac=_elf,
                        epsilon=_eps,
                        stop_energy=_se,
                        num_opt_iter=_noi,
                        quiet=True,
                    )
                except Exception as _ex:
                    log.warning(
                        "native_tet_p4d_tier_failed",
                        tier=_label, reason=str(_ex)[:80],
                    )
                    continue
                _t_fb = time.perf_counter() - _t_fb0
                if _tw_v.shape[0] == 0 or _tw_f.shape[0] == 0:
                    continue
                _q_fb = _qsnap_fb(_tw_v.astype(np.float64), _tw_f.astype(np.int64))
                _mq_new = float(_q_fb.mean_q)
                if _mq_new >= 0.20:
                    _g = "A"
                elif _mq_new >= 0.15:
                    _g = "B"
                elif _mq_new >= 0.10:
                    _g = "C"
                else:
                    _g = "D"
                _n_cells_new = int(_tw_f.shape[0])
                (
                    _accept,
                    _missing_source_vertices,
                    _p4c_topology,
                ) = _p4c_candidate_meets_acceptance_l0(
                    _input_source_vertices,
                    _input_source_faces,
                    _tw_v,
                    _tw_f,
                    old_mean_quality=_mq_old,
                    candidate_mean_quality=_mq_new,
                    old_cell_count=_n_cells_old,
                    candidate_cell_count=_n_cells_new,
                )
                log.info(
                    "native_tet_p4d_chain_tier",
                    tier=_label, grade=_g,
                    n_cells=_n_cells_new, mq=round(_mq_new, 3),
                    elapsed=round(_t_fb, 2), accepted=_accept,
                    missing_source_vertices=_missing_source_vertices,
                    open_edges=_p4c_topology.n_open_edges,
                    nonmanifold_edges=_p4c_topology.n_nonmanifold_edges,
                    nonmanifold_faces=_p4c_topology.n_nonmanifold_faces,
                    boundary_components=_p4c_topology.n_boundary_components,
                    duplicate_tets=_p4c_topology.n_duplicate_tets,
                    degenerate_tets=_p4c_topology.n_degenerate_tets,
                    inverted_tets=_p4c_topology.n_inverted_tets,
                )
                if not _accept:
                    continue
                # best 갱신: grade A 우선, 같으면 mq 큰 쪽.
                _best_so_far = (_best_q is None) or (
                    _g == "A" and _best_grade != "A"
                ) or (
                    _g == _best_grade and _mq_new > float(_best_q.mean_q)
                )
                if _best_so_far:
                    _best_v = _tw_v
                    _best_f = _tw_f
                    _best_q = _q_fb
                    _best_grade = _g
                    _best_label = _label
                # 조기 종료: A 도달 시 중단.
                if _g == "A":
                    break

            if _best_v is not None and _best_q is not None:
                final_pts = _best_v.astype(np.float64)
                final_tets = _best_f.astype(np.int64)
                final_quality = _best_q
                n_cells = int(_best_f.shape[0])
                n_points = int(_best_v.shape[0])
                grade = _best_grade
                # non-skip 경로에서도 아래 4428 re-write 가 P4-C mesh 를
                # 반드시 persist 하도록 표시.
                _p4c_rewrote = True
                log.info(
                    "native_tet_p4c_pytetwild_fallback",
                    grade_old=_grade_old, grade_new=grade,
                    chain_tier=_best_label,
                    n_cells_old=_n_cells_old,
                    n_cells_new=n_cells,
                    mq_old=round(_mq_old, 3),
                    mq_new=round(float(_best_q.mean_q), 3),
                    accepted=True,
                )
            else:
                # 모든 tier reject → keep self-impl mesh.
                grade = _grade_old
                log.info(
                    "native_tet_p4c_pytetwild_fallback_all_reject",
                    grade_old=_grade_old,
                )
        except Exception as exc:
            log.warning("native_tet_p4c_pytetwild_skipped", reason=str(exc)[:120])

    # CFD-QUALITY (2026-05) — 사용자 환경변수 ``AUTO_TESSELL_TET_CFD_QUALITY=1`` 시
    # grade A 도달 후에도 추가 Klingner + AMIPS 사이클을 돌려 CFD 핵심 메트릭
    # (aspect_ratio / skewness / non-orthogonality) 을 더 낮춘다. CFD solver 가
    # 요구하는 max_non_ortho<60°, max_skew<2.5, max_aspect<50 목표.
    if (
        os.environ.get("AUTO_TESSELL_TET_CFD_QUALITY", "0") == "1"
        and final_tets.shape[0] > 100
    ):
        try:
            from core.generator.native_tet.klingner_full_sweep import (
                klingner_full_sweep as _kf_cfd,
            )
            _ns_cfd = int(min(V.shape[0], final_pts.shape[0]))
            _lock_cfd = np.arange(_ns_cfd, dtype=np.int64)
            _new_pts_cfd, _new_tets_cfd, _cfd_res = _kf_cfd(
                final_pts, final_tets,
                n_cycles=4,                  # default 2 → 4: 추가 수렴.
                locked_vertex_ids=_lock_cfd,
                monotone_min_drop=0.005,     # 작은 개선도 받음 (default 0.020).
            )
            if _cfd_res.accepted:
                final_pts = _new_pts_cfd
                final_tets = _new_tets_cfd
                log.info(
                    "native_tet_cfd_quality_klingner",
                    cycles=_cfd_res.n_cycles_used,
                    mq_before=round(_cfd_res.pre_mean_q, 4),
                    mq_after=round(_cfd_res.post_mean_q, 4),
                    elapsed_s=round(_cfd_res.elapsed_s, 2),
                )
        except Exception as _cfd_exc:
            log.debug("native_tet_cfd_quality_klingner_skipped",
                      reason=str(_cfd_exc)[:120])
        # AMIPS 추가 smoothing — surface vertices 는 lock.
        try:
            from core.generator.native_tet.amips import smooth_amips as _smooth_amips
            _ns_amips = int(min(V.shape[0], final_pts.shape[0]))
            _amips_lock = np.arange(_ns_amips, dtype=np.int64)
            _amips_res, _amips_pts = _smooth_amips(
                final_pts, final_tets,
                locked_vertex_ids=_amips_lock,
                n_iter=8,           # 추가 8 iteration.
            )
            if _amips_pts is not None and _amips_pts.shape == final_pts.shape:
                final_pts = _amips_pts
                log.info(
                    "native_tet_cfd_quality_amips",
                    n_iter=int(getattr(_amips_res, "n_iter", 0)),
                    n_relocated=int(getattr(_amips_res, "n_relocated", 0)),
                    e_init=round(float(getattr(_amips_res, "e_init", 0.0)), 4),
                    e_final=round(float(getattr(_amips_res, "e_final", 0.0)), 4),
                )
        except Exception as _amips_exc:
            log.debug("native_tet_cfd_quality_amips_skipped",
                      reason=str(_amips_exc)[:120])

    # P4-B-5h (beta2245i): historical post-P4C write point.  Actual writing is
    # deferred to FINAL-SYNC below so every downstream pass contributes to one
    # and only one on-disk source of truth.
    if _phase_bc_skip or _p4c_rewrote:
        log.info(
            "native_tet_polymesh_write_post_p4c_deferred",
            phase_bc_skip=bool(_phase_bc_skip),
            p4c_rewrote=bool(_p4c_rewrote),
        )

    _prog("done", 1.0, n_cells=n_cells, n_points=n_points, elapsed=elapsed)

    # beta1140 (R180) — 개발자용 debug_info dump + input-check warnings 전파.
    debug_info: dict = {
        "seed_grid": int(grid.shape[0]),
        "target_edge": float(target_edge_length),
        "n_final_tets": int(final_tets.shape[0]),
        "n_final_points": int(final_pts.shape[0]),
    }
    if _smooth_then_drop_sidedness_transaction is not None:
        debug_info["smooth_then_drop_sidedness_transaction"] = (
            _smooth_then_drop_sidedness_transaction
        )
    if _degenerate_removal_source_transaction is not None:
        debug_info["degenerate_removal_source_transaction"] = (
            _degenerate_removal_source_transaction
        )
    warnings_list: list[str] = []
    try:
        if chk is not None and chk.warnings:
            warnings_list.extend(chk.warnings)
    except Exception:
        pass

    # Strict-topology recovery: repeated tetrahedron groups can add a third
    # face incidence even though they do not represent distinct volume.  Drop
    # every member only when the exterior boundary is byte-for-byte equivalent
    # by face key and the resulting tet complex has no remaining topology
    # defect.  A true residual non-manifold face still reaches the strict
    # writer and fails closed below.
    try:
        from core.generator.native_tet.rescue_gate import (  # noqa: PLC0415
            drop_duplicate_tet_groups_if_strict_topology_restored,
        )

        _duplicate_group_repair = (
            drop_duplicate_tet_groups_if_strict_topology_restored(
                final_pts,
                final_tets,
            )
        )
        debug_info["strict_topology_duplicate_group_repair"] = {
            "applied": bool(_duplicate_group_repair.applied),
            "n_duplicate_groups": int(_duplicate_group_repair.n_duplicate_groups),
            "n_removed_tets": int(_duplicate_group_repair.n_removed_tets),
            "reason": _duplicate_group_repair.reason,
            "boundary_preserved": bool(
                _duplicate_group_repair.boundary_preserved
            ),
            "before_nonmanifold_faces": int(
                _duplicate_group_repair.before_audit.n_nonmanifold_faces
            ),
            "after_nonmanifold_faces": int(
                _duplicate_group_repair.candidate_audit.n_nonmanifold_faces
            ),
            "before_same_side_internal_faces": int(
                _duplicate_group_repair.before_audit.n_same_side_internal_faces
            ),
            "after_same_side_internal_faces": int(
                _duplicate_group_repair.candidate_audit.n_same_side_internal_faces
            ),
            "before_ambiguous_internal_faces": int(
                _duplicate_group_repair.before_audit.n_ambiguous_internal_faces
            ),
            "after_ambiguous_internal_faces": int(
                _duplicate_group_repair.candidate_audit.n_ambiguous_internal_faces
            ),
        }
        if _duplicate_group_repair.applied:
            final_tets = _duplicate_group_repair.tets
            n_cells = int(final_tets.shape[0])
            debug_info["n_final_tets"] = n_cells
            warnings_list.append(
                "native_tet_strict_topology_duplicate_groups_removed: "
                f"{_duplicate_group_repair.n_removed_tets}"
            )
            log.warning(
                "native_tet_strict_topology_duplicate_groups_removed",
                n_duplicate_groups=int(_duplicate_group_repair.n_duplicate_groups),
                n_removed_tets=int(_duplicate_group_repair.n_removed_tets),
                before_nonmanifold_faces=int(
                    _duplicate_group_repair.before_audit.n_nonmanifold_faces
                ),
                after_nonmanifold_faces=int(
                    _duplicate_group_repair.candidate_audit.n_nonmanifold_faces
                ),
                boundary_preserved=bool(_duplicate_group_repair.boundary_preserved),
            )
    except Exception as _duplicate_group_repair_exc:
        debug_info["strict_topology_duplicate_group_repair_error"] = (
            f"{type(_duplicate_group_repair_exc).__name__}: "
            f"{_duplicate_group_repair_exc}"
        )
        log.warning(
            "native_tet_strict_topology_duplicate_group_repair_skipped",
            reason=str(_duplicate_group_repair_exc)[:160],
        )

    # VAL1 (beta2147) — final orientation validate + auto-flip (default ON).
    # Set env AUTO_TESSELL_VAL1_OFF=1 to disable.
    _val1_n_flipped = 0
    _val1_n_degen = 0
    _t_val1 = time.perf_counter()
    if os.environ.get("AUTO_TESSELL_VAL1_OFF", "0") != "1":
        try:
            from core.generator.native_tet.stellar import (  # noqa: PLC0415
                validate_and_fix_orientations as _vfo,
            )
            final_tets, _n_flipped, _n_degen = _vfo(final_pts, final_tets)
            _val1_n_flipped = int(_n_flipped)
            _val1_n_degen = int(_n_degen)
            log.info(
                "native_tet_validate",
                n_flipped=_n_flipped,
                n_degenerate=_n_degen,
                questionable=(_n_degen > 0),
            )
            if _n_degen > 0:
                warnings_list.append(
                    f"native_tet_degenerate_volume: {_n_degen} degenerate tets"
                )
        except Exception as _val1_exc:
            log.debug("native_tet_validate_skipped", reason=str(_val1_exc)[:120])
    log.info("native_tet_pass_timing", pass_name="VAL1", dt_ms=int((time.perf_counter() - _t_val1) * 1000))

    # Native-only provenance canonicalization.  The self-native path keeps
    # source surface ids as an immutable prefix, but floating arithmetic can
    # leave a few-ulp coordinate drift.  Restore exact input bits only under a
    # boundary-membership proof and a scale-relative machine-roundoff cap.
    # External P4C output may reorder points and is therefore never rewritten.
    try:
        from core.generator.native_tet.rescue_gate import (  # noqa: PLC0415
            restore_source_prefix_roundoff,
        )

        _source_prefix_restore = restore_source_prefix_roundoff(
            _input_source_vertices,
            _input_source_faces,
            np.asarray(final_pts, dtype=np.float64),
            np.asarray(final_tets, dtype=np.int64),
            prefix_contract=not bool(_p4c_rewrote),
        )
        debug_info["source_prefix_roundoff_restore"] = {
            "applied": bool(_source_prefix_restore.applied),
            "reason": _source_prefix_restore.reason,
            "restored_count": int(_source_prefix_restore.restored_count),
            "max_delta": float(_source_prefix_restore.max_delta),
            "cap": float(_source_prefix_restore.cap),
        }
        if _source_prefix_restore.applied:
            final_pts = _source_prefix_restore.points
        log.info(
            "native_tet_source_prefix_roundoff_restore",
            **debug_info["source_prefix_roundoff_restore"],
        )
    except Exception as _source_prefix_restore_exc:
        debug_info["source_prefix_roundoff_restore"] = {
            "applied": False,
            "reason": (
                f"{type(_source_prefix_restore_exc).__name__}: "
                f"{_source_prefix_restore_exc}"
            ),
            "restored_count": 0,
        }
        log.warning(
            "native_tet_source_prefix_roundoff_restore_unverified",
            reason=str(_source_prefix_restore_exc)[:160],
        )

    # Source-aware strict topology contract.  Local closed-manifold validity
    # permits one or more disconnected bodies; exact component and planar-patch
    # provenance then prove that the output neither loses, merges, splits, nor
    # invents a source component or replaces a non-coplanar source facet.
    # Candidate point order is irrelevant, including for external P4C output.
    # This audit does not move vertices, rewrite connectivity, or alter
    # target-cell policy.
    try:
        from core.generator.native_tet.rescue_gate import (  # noqa: PLC0415
            audit_source_topology,
        )

        _source_topology_audit = audit_source_topology(
            _input_source_vertices,
            _input_source_faces,
            np.asarray(final_pts, dtype=np.float64),
            np.asarray(final_tets, dtype=np.int64),
        )
        _source_component_audit = _source_topology_audit.components
        _boundary_topology_audit = _source_topology_audit.boundary
        debug_info["strict_source_component_bijection"] = {
            "bijective": bool(_source_component_audit.bijective),
            "n_source_components": int(
                _source_component_audit.n_source_components
            ),
            "n_candidate_boundary_components": int(
                _source_component_audit.n_candidate_boundary_components
            ),
            "n_source_surface_vertices": int(
                _source_component_audit.n_source_surface_vertices
            ),
            "n_source_vertices_on_boundary": int(
                _source_component_audit.n_source_vertices_on_boundary
            ),
            "n_missing_source_vertices": int(
                _source_component_audit.n_missing_source_vertices
            ),
            "n_matched_source_components": int(
                _source_component_audit.n_matched_source_components
            ),
            "n_mixed_candidate_components": int(
                _source_component_audit.n_mixed_candidate_components
            ),
            "n_split_source_components": int(
                _source_component_audit.n_split_source_components
            ),
            "n_unanchored_candidate_components": int(
                _source_component_audit.n_unanchored_candidate_components
            ),
            "n_unknown_source_vertex_anchors": int(
                _source_component_audit.n_unknown_source_vertex_anchors
            ),
            "n_source_faces": int(_source_component_audit.n_source_faces),
            "n_source_faces_on_boundary": int(
                _source_component_audit.n_source_faces_on_boundary
            ),
            "n_missing_source_faces": int(
                _source_component_audit.n_missing_source_faces
            ),
            "n_candidate_boundary_faces": int(
                _source_component_audit.n_candidate_boundary_faces
            ),
            "n_owned_candidate_faces": int(
                _source_component_audit.n_owned_candidate_faces
            ),
            "n_unowned_candidate_faces": int(
                _source_component_audit.n_unowned_candidate_faces
            ),
            "n_source_planar_patches": int(
                _source_component_audit.n_source_planar_patches
            ),
            "n_uncovered_source_patches": int(
                _source_component_audit.n_uncovered_source_patches
            ),
            "n_area_mismatch_patches": int(
                _source_component_audit.n_area_mismatch_patches
            ),
            "n_feature_boundary_mismatches": int(
                _source_component_audit.n_feature_boundary_mismatches
            ),
            "n_overlap_pairs": int(_source_component_audit.n_overlap_pairs),
            "source_faces_preserved": bool(
                _source_component_audit.source_faces_preserved
            ),
        }
        debug_info["strict_source_topology"] = {
            "valid": bool(_source_topology_audit.valid),
            "n_boundary_faces": int(_boundary_topology_audit.n_boundary_faces),
            "n_boundary_components": int(
                _boundary_topology_audit.n_boundary_components
            ),
            "n_open_edges": int(_boundary_topology_audit.n_open_edges),
            "n_nonmanifold_edges": int(
                _boundary_topology_audit.n_nonmanifold_edges
            ),
            "n_nonmanifold_faces": int(
                _boundary_topology_audit.n_nonmanifold_faces
            ),
            "n_duplicate_tets": int(_boundary_topology_audit.n_duplicate_tets),
            "n_degenerate_tets": int(
                _boundary_topology_audit.n_degenerate_tets
            ),
            "n_inverted_tets": int(_boundary_topology_audit.n_inverted_tets),
            "n_internal_faces": int(_boundary_topology_audit.n_internal_faces),
            "n_same_side_internal_faces": int(
                _boundary_topology_audit.n_same_side_internal_faces
            ),
            "n_ambiguous_internal_faces": int(
                _boundary_topology_audit.n_ambiguous_internal_faces
            ),
            "component_bijective": bool(_source_component_audit.bijective),
            "source_faces_preserved": bool(
                _source_component_audit.source_faces_preserved
            ),
        }
        if not _source_topology_audit.valid:
            import shutil  # noqa: PLC0415

            _stale_poly_mesh = Path(case_dir) / "constant" / "polyMesh"
            if _stale_poly_mesh.is_dir():
                shutil.rmtree(_stale_poly_mesh)
            debug_info["strict_source_topology"]["polymesh_artifacts_removed"] = (
                not _stale_poly_mesh.exists()
            )
            log.warning(
                "native_tet_source_topology_rejected",
                **debug_info["strict_source_topology"],
            )
            return NativeTetResult(
                False,
                time.perf_counter() - t0,
                n_cells=int(final_tets.shape[0]),
                n_points=int(final_pts.shape[0]),
                message="native_tet source-aware strict topology is invalid",
                tet_points=final_pts,
                tets=final_tets,
                warnings=warnings_list or None,
                debug_info=debug_info,
            )
    except Exception as _source_topology_exc:
        import shutil  # noqa: PLC0415

        _stale_poly_mesh = Path(case_dir) / "constant" / "polyMesh"
        if _stale_poly_mesh.is_dir():
            shutil.rmtree(_stale_poly_mesh)
        debug_info["strict_source_topology_error"] = (
            f"{type(_source_topology_exc).__name__}: {_source_topology_exc}"
        )
        debug_info["strict_source_topology_artifacts_removed"] = (
            not _stale_poly_mesh.exists()
        )
        log.warning(
            "native_tet_source_topology_unverified",
            reason=str(_source_topology_exc)[:160],
        )
        return NativeTetResult(
            False,
            time.perf_counter() - t0,
            n_cells=int(final_tets.shape[0]),
            n_points=int(final_pts.shape[0]),
            message=(
                "native_tet source-aware strict topology is unverified: "
                f"{_source_topology_exc}"
            ),
            tet_points=final_pts,
            tets=final_tets,
            warnings=warnings_list or None,
            debug_info=debug_info,
        )

    # FINAL-SYNC / beta-DET-RESULT1 — W3 and later local passes can replace
    # final_pts/final_tets after the earlier polyMesh write.  Keep the returned
    # arrays, on-disk mesh, counts, and quality snapshot on one final source of
    # truth; otherwise callers can observe (for example) 353/1869 metadata
    # paired with a 73/212 v_only_smoothed array.
    try:
        _final_stats = PolyMeshWriter().write(
            final_pts,
            final_tets,
            case_dir,
            boundary_patch_classifier=_get_boundary_patch_classifier(),
            point_precision=17,
        )
        n_cells = int(final_tets.shape[0])
        n_points = int(final_pts.shape[0])
        from core.generator.native_tet.quality import snapshot as _qsnap_final
        final_quality = _qsnap_final(final_pts, final_tets)
        _final_mq_sync = float(getattr(final_quality, "mean_q", 0.0))
        if _p4c_rewrote:
            # The pre-P4C pass gate either measured a different mesh or was
            # skipped.  Never return those values as evidence for the arrays
            # that are now on disk and in NativeTetResult.
            plane_cov_val = -1.0
            plane_area_cov_val = -1.0
            haus_rel = -1.0
            try:
                (
                    plane_cov_val,
                    plane_area_cov_val,
                    haus_rel,
                ) = _measure_final_shape_evidence_l0(
                    _input_source_vertices,
                    _input_source_faces,
                    final_pts,
                    final_tets,
                )
                debug_info["final_shape_evidence_recomputed"] = True
                log.info(
                    "native_tet_final_shape_evidence",
                    plane_coverage=round(plane_cov_val, 6),
                    plane_area_coverage=round(plane_area_cov_val, 6),
                    hausdorff_relative=round(haus_rel, 8),
                )
            except Exception as _shape_evidence_exc:
                debug_info["final_shape_evidence_recomputed"] = False
                debug_info["final_shape_evidence_error"] = (
                    f"{type(_shape_evidence_exc).__name__}: {_shape_evidence_exc}"
                )
                warnings_list.append(
                    "native_tet_final_shape_evidence_unverified: "
                    f"{type(_shape_evidence_exc).__name__}"
                )
                log.warning(
                    "native_tet_final_shape_evidence_unverified",
                    reason=str(_shape_evidence_exc)[:160],
                )
            if (
                plane_cov_val >= 0.95
                and plane_area_cov_val >= 0.95
                and 0.0 <= haus_rel <= 0.05
                and _final_mq_sync >= 0.25
            ):
                grade = "A"
            elif (
                plane_cov_val >= 0.8
                and plane_area_cov_val >= 0.8
                and 0.0 <= haus_rel <= 0.05
                and _final_mq_sync >= 0.18
            ):
                grade = "B"
            elif (
                plane_cov_val >= 0.5
                and 0.0 <= haus_rel <= 0.10
                and _final_mq_sync >= 0.10
            ):
                grade = "C"
            else:
                grade = "D"
        else:
            grade = (
                "A" if _final_mq_sync >= 0.20 else
                "B" if _final_mq_sync >= 0.15 else
                "C" if _final_mq_sync >= 0.10 else "D"
            )
        debug_info["n_final_tets"] = n_cells
        debug_info["n_final_points"] = n_points
        debug_info["final_sync_writer_cells"] = int(
            _final_stats.get("num_cells", n_cells)
        )
        debug_info["final_sync_writer_points"] = int(
            _final_stats.get("num_points", n_points)
        )
        log.info(
            "native_tet_polymesh_write_final",
            num_cells=n_cells,
            num_points=n_points,
        )
    except Exception as _final_sync_exc:
        log.warning(
            "native_tet_final_sync_failed",
            reason=str(_final_sync_exc)[:160],
        )
        return NativeTetResult(
            False,
            time.perf_counter() - t0,
            n_cells=int(final_tets.shape[0]),
            n_points=int(final_pts.shape[0]),
            message=(
                "native_tet writer rejected output topology: "
                f"{_final_sync_exc}"
            ),
            tet_points=final_pts,
            tets=final_tets,
            warnings=warnings_list or None,
            debug_info=debug_info,
        )

    # RUN_SUMMARY (beta2157) — aggregate post-pass counts (observability only).
    # C-VAL-5 / beta2402 — final mean_q 노출 (cycle 별 quality progression 추적).
    _final_mq = float(getattr(final_quality, "mean_q", 0.0)) if final_quality else 0.0
    _final_min_q = float(getattr(final_quality, "min_q", 0.0)) if final_quality else 0.0
    log.info(
        "native_tet_run_summary",
        n_cells=n_cells,
        n_points=n_points,
        grade=grade,
        mean_q=round(_final_mq, 4),
        min_q=round(_final_min_q, 4),
        n_sliver_detected=int(locals().get("_n_sliver_pre", 0) or 0),
        n_aniso_detected=int(locals().get("_n_aniso_pre", 0) or 0),
        n_chains=int(locals().get("_n711", 0) or 0),
        n_val_flipped=_val1_n_flipped,
        n_val_degen=_val1_n_degen,
        elapsed=round(elapsed, 3),
    )

    # C-QUAL-1 / beta2382 (revised beta2383, beta2405): mesh integrity suspect 감지.
    # validator finding: V/8 threshold 가 hard non-manifold mesh 의 정상 결과
    # (V=12k → 1060 cells = ratio 0.088) 도 false-positive flag.
    # 따라서 V/32 (ratio < 0.031) 로 tighten — 진짜 catastrophic collapse 만
    # 잡는다 (V=3116 → 2 cells = 0.0006 < 1/32).
    # beta2405: 추가 absolute floor — n_cells < 50 시 size 무관 always flag
    # (V 가 작아도 50 cells 이하는 mesh 로 의미 없음).
    _mesh_suspect = bool(
        n_cells > 0
        and (
            (V.shape[0] >= 100 and n_cells < V.shape[0] // 32)
            or n_cells < 50
        )
    )
    if _mesh_suspect:
        log.warning(
            "native_tet_mesh_integrity_suspect",
            component="native_tet", phase="beta2383",
            n_cells=int(n_cells),
            n_surface_v=int(V.shape[0]),
            ratio=round(n_cells / max(1, V.shape[0]), 4),
            message="cells/V_surf ratio < 1/32 — catastrophic collapse",
        )

    if min_final_vertices is not None and int(min_final_vertices) > 0:
        required_vertices = int(min_final_vertices)
        if n_points < required_vertices:
            log.warning(
                "native_tet_target_primal_vertex_floor_unmet",
                actual_vertices=int(n_points),
                required_vertices=required_vertices,
                target_cells=target_cells,
            )
            return NativeTetResult(
                success=False,
                elapsed=elapsed,
                n_cells=n_cells,
                n_points=n_points,
                message=(
                    "target_primal_vertex_floor_unmet: "
                    f"actual={n_points}, required={required_vertices}"
                ),
                tet_points=final_pts,
                tets=final_tets,
                quality=final_quality,
                warnings=warnings_list or None,
                debug_info=debug_info,
                quality_grade=grade,
                cdt_ratio=float(cdt_ratio_val),
                cdt_face_ratio=float(cdt_face_ratio_val),
                plane_coverage=float(plane_cov_val),
                plane_area_coverage=float(plane_area_cov_val),
                hausdorff_relative=float(haus_rel),
                n_self_intersect_pre=_pre_mesh_si_count,
                mesh_integrity_suspect=_mesh_suspect,
            )

    # CYLSKEW1 (beta2822) — offset-ring 삽입점이 최종 boundary 로 새지 않는지
    # 진단 (read-only, 하류 로직 변경 없음). default OFF 경로에서는 no-op.
    if _offset_ring_pts.shape[0]:
        try:
            from core.generator.native_tet.plane_coverage import _tet_boundary_faces as _tbf_or
            _bnd_ids_or = np.unique(_tbf_or(final_tets).ravel())
            _bnd_pts_or = final_pts[_bnd_ids_or] if _bnd_ids_or.size else np.zeros((0, 3))
            _n_became_boundary = 0
            for _p_or in _offset_ring_pts:
                if _bnd_pts_or.shape[0] and float(
                    np.linalg.norm(_bnd_pts_or - _p_or, axis=1).min()
                ) < 1e-9:
                    _n_became_boundary += 1
            log.info(
                "native_tet_offset_ring_diag",
                n_offset=int(_offset_ring_pts.shape[0]),
                n_became_boundary=_n_became_boundary,
            )
        except Exception as _or_diag_exc:
            log.debug("native_tet_offset_ring_diag_skipped", reason=str(_or_diag_exc)[:120])

    return NativeTetResult(
        success=True, elapsed=elapsed,
        n_cells=n_cells, n_points=n_points,
        message=(
            f"native_tet OK — cells={n_cells}, points={n_points}, "
            f"seed_grid={grid.shape[0]}, target_edge={target_edge_length:.4g}"
        ),
        tet_points=final_pts, tets=final_tets,
        quality=final_quality,
        warnings=warnings_list or None,
        debug_info=debug_info,
        quality_grade=grade,
        cdt_ratio=float(cdt_ratio_val),
        cdt_face_ratio=float(cdt_face_ratio_val),
        plane_coverage=float(plane_cov_val),
        plane_area_coverage=float(plane_area_cov_val),
        hausdorff_relative=float(haus_rel),
        # beta2336 — pre-mesh SI count (UUU2 에서 capture).
        n_self_intersect_pre=_pre_mesh_si_count,
        mesh_integrity_suspect=_mesh_suspect,
    )
