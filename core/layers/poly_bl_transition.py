"""poly 메쉬용 BL: native_bl 결과를 polyhedral-friendly 형태로 유지.

전략:
    1. native_bl.generate_native_bl() 로 wall 근처 prism (wedge) 층을 삽입.
       prism cell 은 polyMesh 포맷에서 face-list 로 정의되므로 OpenFOAM 의
       polyhedral cell type 과 호환된다 (wedge = 2 triangle + 3 quad, 5 face).
    2. bulk (내부 tet) 영역을 polyDualMesh 로 dual 변환 — OpenFOAM 사용 가능 시.
       사용 불가 시엔 native_bl 결과 그대로 반환 (tet + prism 혼합).
    3. 결과 polyMesh 는 "wall 근처 prism (polyhedral-compatible) + bulk 는
       tet 또는 polyDual" 구조.

이는 ANSYS Fluent / Star-CCM+ 등에서 쓰는 "polyhedral + prism BL" 의
표준 패턴.

Phase 2 확장 (향후):
    - bulk tet → 자체 dual 변환 구현 (scipy Voronoi 의존 제거)
    - prism vs polyhedral cell 간 face 정렬 품질 개선
"""

from __future__ import annotations

import hashlib
import os
import json
import time
from dataclasses import dataclass
from pathlib import Path

from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.layers.native_bl import (
    BLConfig,
    _native_bl_zero_request_blocker,
    _refresh_native_bl_state_output,
    generate_native_bl,
)
from core.evaluator.native_canonical_quality_witness import (
    build_canonical_volume_quality_witness,
)
from core.evaluator.native_volume_transaction_adapter import (
    evaluate_and_publish_native_volume_artifact,
)
from core.utils.native_extensions import (
    load_native_poly_quality_relocation,
    load_native_polymesh,
)
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)
from core.layers.native_bl import _write_faces, _write_points
from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class PolyBLResult:
    success: bool
    elapsed: float
    n_prism_cells: int = 0
    bulk_dual_applied: bool = False
    message: str = ""
    quality_relocation: dict[str, object] | None = None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _poly_quality_relocation_enabled() -> bool:
    return os.environ.get("AUTO_TESSELL_POLY_NATIVE_QUALITY_RELOCATE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _quality_tuple(witness: dict[str, object]) -> tuple[float, float, float]:
    quality = witness.get("quality", {})
    if not isinstance(quality, dict):
        return (float("inf"), float("inf"), float("inf"))
    values: list[float] = []
    for key in ("internal_non_orthogonality", "release_skew", "aspect_ratio"):
        metric = quality.get(key, {})
        value = metric.get("max") if isinstance(metric, dict) else None
        values.append(float(value) if isinstance(value, (int, float)) else float("inf"))
    return tuple(values)  # type: ignore[return-value]


def _write_poly_quality_relocation_report(case_dir: Path, report: dict[str, object]) -> None:
    (Path(case_dir) / "native_poly_quality_relocation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _apply_native_poly_quality_relocation(case_dir: Path) -> dict[str, object]:
    """Run one opt-in, coordinate-only Poly quality transaction.

    The native kernel proposes a bounded Laplacian move.  This adapter is the
    authority boundary: it locks the current boundary vertex bit patterns,
    leaves face/owner/neighbour arrays untouched, re-runs strict topology and
    the canonical C++ quality witness, and restores the original points bytes
    on every rejection.
    """
    import numpy as np

    case = Path(case_dir)
    poly = case / "constant" / "polyMesh"
    points_path = poly / "points"
    if not poly.is_dir() or not points_path.is_file():
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "polymesh_missing",
            "destination_unchanged": True,
        }
    kernel = load_native_poly_quality_relocation()
    if kernel is None:
        report = {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "native_poly_quality_relocation_unavailable",
            "destination_unchanged": True,
        }
        _write_poly_quality_relocation_report(case, report)
        return report

    try:
        points_before = np.asarray(parse_foam_points_array(points_path), dtype=np.float64)
        faces_before = parse_foam_faces(poly / "faces")
        owner_before = np.asarray(parse_foam_labels_array(poly / "owner"), dtype=np.int64)
        neighbour_before = np.asarray(parse_foam_labels_array(poly / "neighbour"), dtype=np.int64)
        before_witness = build_canonical_volume_quality_witness(case)
        if before_witness.get("accepted") is not True:
            raise RuntimeError(f"baseline_quality_unavailable:{before_witness.get('reason')}")
        flat = np.asarray([int(vertex) for face in faces_before for vertex in face], dtype=np.int64)
        offsets = np.zeros(len(faces_before) + 1, dtype=np.int64)
        offsets[1:] = np.cumsum([len(face) for face in faces_before], dtype=np.int64)
        boundary_ids = np.asarray(
            sorted({int(vertex) for face in faces_before[len(neighbour_before):] for vertex in face}),
            dtype=np.int64,
        )
        iterations = int(os.environ.get("AUTO_TESSELL_POLY_NATIVE_QUALITY_ITER", "3"))
        relax = float(os.environ.get("AUTO_TESSELL_POLY_NATIVE_QUALITY_RELAX", "0.001"))
        diagonal = float(np.linalg.norm(points_before.max(axis=0) - points_before.min(axis=0)))
        max_move_ratio = float(os.environ.get("AUTO_TESSELL_POLY_NATIVE_QUALITY_MAX_MOVE_RATIO", "0.02"))
        cpp_result = dict(kernel.relocate_poly_quality(
            points_before,
            flat,
            offsets,
            owner_before,
            neighbour_before,
            boundary_ids,
            iterations,
            relax,
            max(0.0, diagonal * max_move_ratio),
        ))
        candidate = np.asarray(cpp_result["points"], dtype=np.float64)
        if candidate.shape != points_before.shape or not np.isfinite(candidate).all():
            raise RuntimeError("native_candidate_shape_or_finite_gate")
        if not np.array_equal(
            np.ascontiguousarray(points_before[boundary_ids]).view(np.uint64),
            np.ascontiguousarray(candidate[boundary_ids]).view(np.uint64),
        ):
            raise RuntimeError("boundary_vertex_bits_changed")
        if (
            cpp_result.get("topology_input_valid") is not True
            or cpp_result.get("boundary_vertices_locked") is not True
            or cpp_result.get("accepted") is not True
        ):
            raise RuntimeError(f"native_candidate_rejected:{cpp_result.get('reason')}")
        original_bytes = points_path.read_bytes()
        _write_points(points_path, candidate, precision=17)
        try:
            points_after = np.asarray(parse_foam_points_array(points_path), dtype=np.float64)
            if not np.array_equal(
                np.ascontiguousarray(points_before[boundary_ids]).view(np.uint64),
                np.ascontiguousarray(points_after[boundary_ids]).view(np.uint64),
            ):
                raise RuntimeError("serialized_boundary_vertex_bits_changed")
            if parse_foam_faces(poly / "faces") != faces_before:
                raise RuntimeError("faces_changed")
            if not np.array_equal(parse_foam_labels_array(poly / "owner"), owner_before):
                raise RuntimeError("owner_changed")
            if not np.array_equal(parse_foam_labels_array(poly / "neighbour"), neighbour_before):
                raise RuntimeError("neighbour_changed")
            strict = audit_strict_volume_topology(case)
            after_witness = build_canonical_volume_quality_witness(case)
            if not strict.valid:
                raise RuntimeError("strict_topology_failed")
            if after_witness.get("accepted") is not True:
                raise RuntimeError(f"post_quality_unavailable:{after_witness.get('reason')}")
            before_tuple = _quality_tuple(before_witness)
            after_tuple = _quality_tuple(after_witness)
            if not after_tuple < before_tuple:
                raise RuntimeError("authoritative_quality_tuple_not_improved")
        except Exception:
            points_path.write_bytes(original_bytes)
            raise
        report: dict[str, object] = {
            "accepted": True,
            "status": "accepted",
            "reason": "strict_quality_improvement",
            "destination_unchanged": False,
            "strict_topology": strict.as_dict(),
            "quality_before": before_witness.get("quality", {}),
            "quality_after": after_witness.get("quality", {}),
            "quality_tuple_before": list(before_tuple),
            "quality_tuple_after": list(after_tuple),
            "cpp": {key: value for key, value in cpp_result.items() if key != "points"},
            "boundary_vertex_count": int(len(boundary_ids)),
            "face_count": int(len(faces_before)),
            "cell_count": int(max(
                owner_before.max(initial=-1),
                neighbour_before.max(initial=-1),
            ) + 1),
        }
        _write_poly_quality_relocation_report(case, report)
        return report
    except Exception as exc:  # noqa: BLE001
        report = {
            "accepted": False,
            "status": "refused_rollback",
            "reason": str(exc),
            "destination_unchanged": True,
        }
        _write_poly_quality_relocation_report(case, report)
        return report


def canonicalize_staged_poly_bl_candidate(
    stage_dir: Path,
    *,
    tolerance: float = 1e-12,
) -> dict[str, object]:
    """Canonicalize only a fresh staged Poly BL candidate.

    BL0 is observation-only. BL>=1 may change only internal face cycle order;
    the destination is never touched by this function.
    """
    stage = Path(stage_dir)
    poly = stage / "constant" / "polyMesh"
    faces_path = poly / "faces"
    state_path = stage / "native_bl_state.json"
    quality_path = stage / "native_bl_quality.json"
    if not poly.is_dir() or not faces_path.is_file():
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "staged_polymesh_missing",
            "destination_unchanged": True,
        }
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "bl_state_missing",
            "destination_unchanged": True,
        }
    if not isinstance(state, dict):
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "bl_state_invalid",
            "destination_unchanged": True,
        }
    requested = state.get("requested_layers")
    actual = state.get("actual_layers")
    if requested == 0 and actual == 0:
        return {
            "accepted": True,
            "status": "observation_only",
            "reason": "bl0_cycle_correction_forbidden",
            "reversed_indices": [],
            "destination_unchanged": True,
            "faces_sha256": _sha256_bytes(faces_path.read_bytes()),
        }
    if (
        not isinstance(requested, int)
        or isinstance(requested, bool)
        or requested < 1
        or actual != requested
        or state.get("state") != "completed"
    ):
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "bl_positive_count_or_state_invalid",
            "destination_unchanged": True,
        }
    try:
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "bl_quality_missing",
            "destination_unchanged": True,
        }
    if (
        not isinstance(quality, dict)
        or not isinstance(quality.get("total_thickness"), (int, float))
        or quality["total_thickness"] <= 0.0
        or not isinstance(quality.get("n_prism_cells"), int)
        or quality["n_prism_cells"] <= 0
        or not isinstance(quality.get("bad_internal_faces"), dict)
        or quality["bad_internal_faces"].get("n_bad_faces") != 0
    ):
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "bl_quality_gate",
            "destination_unchanged": True,
        }
    provenance_path = stage / "native_bl_provenance.json"
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "bl_lineage_missing",
            "destination_unchanged": True,
        }
    required_lineage = (
        "wall_edge_layer_sha256",
        "source_face_preservation_sha256",
        "outer_front_sha256",
        "source_sha256",
        "candidate_source_sha256",
    )
    if (
        not isinstance(provenance, dict)
        or provenance.get("lineage_complete") is not True
        or any(
            not isinstance(provenance.get(name), str)
            or len(provenance[name]) != 64
            or any(char not in "0123456789abcdef" for char in provenance[name])
            for name in required_lineage
        )
    ):
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "bl_lineage_incomplete",
            "destination_unchanged": True,
        }
    try:
        import numpy as np

        points = parse_foam_points_array(poly / "points")
        faces = parse_foam_faces(faces_path)
        owners = parse_foam_labels_array(poly / "owner")
        neighbours = parse_foam_labels_array(poly / "neighbour")
        native = load_native_polymesh()
        if native is None:
            raise RuntimeError("native_polymesh_unavailable")
        result = native.canonicalize_internal_winding_or_refuse(
            np.asarray(points, dtype=np.float64),
            faces,
            np.asarray(owners, dtype=np.int64),
            np.asarray(neighbours, dtype=np.int64),
            float(tolerance),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": f"orientation_kernel_unavailable:{type(exc).__name__}",
            "destination_unchanged": True,
        }
    if result.get("accepted") is not True:
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": str(result.get("reason", "orientation_refused")),
            "destination_unchanged": True,
            "orientation_ledger": list(result.get("orientation_ledger", [])),
        }

    before = faces_path.read_bytes()
    corrected = [list(face) for face in result["faces"]]
    _write_faces(faces_path, corrected)
    try:
        strict = audit_strict_volume_topology(stage)
        witness = build_canonical_volume_quality_witness(stage)
        if not strict.valid:
            raise RuntimeError("strict_topology_failed")
        if witness.get("accepted") is not True:
            raise RuntimeError(str(witness.get("reason", "quality_witness_failed")))
        metrics = witness.get("quality", {})
        no = metrics.get("internal_non_orthogonality", {})
        sk = metrics.get("release_skew", {})
        ar = metrics.get("aspect_ratio", {})
        if (
            no.get("p95") is not None and no.get("p95") > 35.0
            or no.get("max") is not None and no.get("max") > 50.0
            or sk.get("p95") is not None and sk.get("p95") > 0.25
            or sk.get("max") is not None and sk.get("max") > 0.50
            or ar.get("max") is not None and ar.get("max") > 3.0
        ):
            raise RuntimeError("quality_threshold_failed")
    except Exception as exc:  # noqa: BLE001
        faces_path.write_bytes(before)
        return {
            "accepted": False,
            "status": "refused_rollback",
            "reason": f"post_canonicalization_gate:{type(exc).__name__}",
            "destination_unchanged": True,
            "orientation_ledger": list(result.get("orientation_ledger", [])),
        }
    return {
        "accepted": True,
        "status": "staged_measured",
        "reason": "internal_orientation_canonicalized",
        "reversed_indices": list(result.get("reversed_indices", [])),
        "orientation_ledger": list(result.get("orientation_ledger", [])),
        "faces_sha256_before": _sha256_bytes(before),
        "faces_sha256_after": _sha256_bytes(faces_path.read_bytes()),
        "strict_topology": strict.as_dict(),
        "quality_witness_sha256": witness.get("witness_sha256"),
        "destination_unchanged": True,
    }


def finalize_staged_poly_bl_candidate(
    destination: Path,
    staged_artifact: Path,
    baseline: dict,
    candidate: dict,
    *,
    requested_layers: int,
    actual_layers: int,
    evidence: dict,
) -> dict[str, object]:
    """Run staged orientation/readback then the existing atomic authority gate."""
    orientation = canonicalize_staged_poly_bl_candidate(staged_artifact)
    if orientation.get("accepted") is not True:
        return {"orientation": orientation, "published": False}
    publication = evaluate_and_publish_native_volume_artifact(
        destination,
        staged_artifact,
        baseline,
        candidate,
        requested_layers=requested_layers,
        actual_layers=actual_layers,
        evidence=evidence,
    )
    return {
        "orientation": orientation,
        "publication": publication.as_dict(),
        "published": publication.published,
    }


def _classify_cells_by_vertex_count(
    owner,
    neighbour,
    faces,
) -> tuple[int, list[set[int]], list[int], list[int]]:
    """polyMesh face/owner/neighbour 로부터 각 cell 의 unique vertex set 복원.

    Returns:
        (n_cells, cell_verts, tet_cell_ids, non_tet_cell_ids).
        - cell_verts[ci] = cell ci 를 구성하는 vertex index set.
        - tet_cell_ids: 4 unique vertex (= tet) cell 인덱스 목록.
        - non_tet_cell_ids: 그 외 (prism 6, hex 8, polyhedron n) 인덱스 목록.
    """
    n_cells = int(owner.max()) + 1 if len(owner) else 0
    if len(neighbour):
        n_cells = max(n_cells, int(neighbour.max()) + 1)
    cell_verts: list[set[int]] = [set() for _ in range(n_cells)]
    for fi, f in enumerate(faces):
        cell_verts[int(owner[fi])].update(int(v) for v in f)
        if fi < len(neighbour):
            cell_verts[int(neighbour[fi])].update(int(v) for v in f)
    tet_ids: list[int] = []
    non_tet_ids: list[int] = []
    for ci, cv in enumerate(cell_verts):
        if len(cv) == 4:
            tet_ids.append(ci)
        else:
            non_tet_ids.append(ci)
    return n_cells, cell_verts, tet_ids, non_tet_ids


def _try_native_poly_dual(
    case_dir: Path,
    *,
    interface_smoothing: bool = True,
    interface_smooth_iters: int = 2,
) -> tuple[bool, str]:
    """v0.4 native: polyMesh 에서 tet array 를 복원해 tet_to_poly_dual 로 변환.

    OpenFOAM polyDualMesh 호출 없이 순수 Python.

    지원 케이스:
        - **전체 tet** polyMesh: 표준 dual 변환 → 완전 polyhedral mesh.
        - **hybrid (tet + prism)** polyMesh: prism BL 층이 섞여 있는 경우 dual 변환
          을 건너뛰고 원본 hybrid mesh 를 그대로 보존한다 (pass-through). 이때
          ``(True, "…hybrid preserved")`` 가 아닌 ``(False, …)`` 를 반환해 호출측이
          ``bulk_dual_applied=False`` 로 기록. mesh 자체는 여전히 valid polyMesh.

    완전한 hybrid dual (tet 부분만 polyhedral 로 변환하면서 prism 과 interface
    stitching 까지 수행) 은 beta15+ 로드맵. 현재는 prism 과 dual cell 사이 interface
    face 토폴로지 불일치 (prism 삼각형 vs dual 폴리곤) 문제 때문에 dual 을 skip.
    """
    try:
        import numpy as np  # noqa: PLC0415

        from core.generator.native_poly.dual import tet_to_poly_dual  # noqa: PLC0415
        from core.utils.polymesh_reader import (  # noqa: PLC0415
            parse_foam_faces,
            parse_foam_labels,
            parse_foam_points,
        )
    except Exception as exc:
        return False, f"native dual import 실패: {exc}"

    poly_dir = case_dir / "constant" / "polyMesh"
    try:
        pts = np.array(parse_foam_points(poly_dir / "points"), dtype=np.float64)
        faces = parse_foam_faces(poly_dir / "faces")
        owner = np.array(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
        neighbour = np.array(
            parse_foam_labels(poly_dir / "neighbour"),
            dtype=np.int64,
        )
    except Exception as exc:
        return False, f"polyMesh 읽기 실패: {exc}"

    n_cells, cell_verts, tet_ids, non_tet_ids = _classify_cells_by_vertex_count(
        owner,
        neighbour,
        faces,
    )
    if n_cells == 0:
        return False, "cell 없음"

    n_tets = len(tet_ids)
    n_non_tet = len(non_tet_ids)

    if n_tets == 0:
        return False, f"tet cell 0 — dual 변환 불가 (non-tet={n_non_tet})"

    if n_non_tet > 0:
        # Hybrid (tet + prism) — v0.4.0-beta25: best-effort dual-on-tet-subset +
        # prism 보존. interface face 가 dual cell 경계와 정합하지 않을 경우
        # pass-through 로 fallback.
        ok, msg = _try_hybrid_dual(
            pts,
            faces,
            owner,
            neighbour,
            cell_verts,
            tet_ids,
            non_tet_ids,
            case_dir,
            interface_smoothing=interface_smoothing,
            interface_smooth_iters=interface_smooth_iters,
        )
        if ok:
            return True, msg
        # fallback: 원본 mesh 보존 (beta13 동작)
        log.info(
            "poly_bl_hybrid_pass_through",
            n_tets=n_tets,
            n_non_tet=n_non_tet,
            fallback_reason=msg,
        )
        return False, (
            f"hybrid mesh preserved (tet={n_tets}, non-tet={n_non_tet}) — "
            f"hybrid dual fallback: {msg}"
        )

    # 순수 tet → 전체 dual 변환
    tets_list: list[tuple[int, int, int, int]] = [
        tuple(sorted(cell_verts[ci]))
        for ci in tet_ids  # type: ignore[misc]
    ]
    T = np.array(tets_list, dtype=np.int64)
    res = tet_to_poly_dual(pts, T, case_dir)
    if not res.success:
        return False, f"native tet_to_poly_dual 실패: {res.message}"
    return True, f"native tet→poly dual OK ({res.message})"


def _smooth_interface_vertices(
    pts,
    faces,
    owner,
    neighbour,
    prism_cell_ids: set[int],
    tet_cell_ids: list[int],
    n_iter: int = 2,
    relax: float = 0.2,
):
    """prism-tet interface 근방 tet vertex 를 prism face centroid 방향으로 이동.

    전략:
        1. prism cell 의 모든 face 에서 prism 과 tet 양쪽이 owner/neighbour 인
           "interface face" 를 찾는다.
        2. interface face 에 속하는 tet vertex 들을 식별한다.
        3. 각 해당 vertex 를 인접 interface face centroid 방향으로 살짝 이동.
        4. n_iter 번 반복.

    Args:
        pts: (N, 3) float64 vertex 좌표.
        faces: list of face vertex index lists.
        owner: (F,) int64 owner cell.
        neighbour: (F,) int64 neighbour cell (-1 이면 boundary).
        prism_cell_ids: prism/non-tet cell 인덱스 집합.
        tet_cell_ids: tet cell 인덱스 목록.
        n_iter: smoothing 반복 횟수.
        relax: 이동 비율 (0=고정, 1=centroid 로 완전 이동).

    Returns:
        새로운 pts array (원본 pts 는 수정하지 않음).
    """
    import numpy as np  # noqa: PLC0415

    new_pts = pts.copy()
    tet_set = set(tet_cell_ids)
    n_nbr = len(neighbour)

    for _ in range(n_iter):
        # interface face: prism 과 tet 가 공유하는 face
        # owner=prism, neighbour=tet  or  owner=tet, neighbour=prism
        vert_centroids: dict[int, list] = {}  # vertex idx → list of centroid positions

        for fi, fv in enumerate(faces):
            o = int(owner[fi])
            n = int(neighbour[fi]) if fi < n_nbr else -1
            is_interface = (o in prism_cell_ids and n in tet_set) or (
                o in tet_set and n in prism_cell_ids
            )
            if not is_interface:
                continue
            centroid = new_pts[list(fv)].mean(axis=0)
            # tet 쪽 vertex 만 이동 대상
            for v in fv:
                vert_centroids.setdefault(int(v), []).append(centroid)

        # tet vertex 만 이동
        for vi, centroids in vert_centroids.items():
            avg_c = np.mean(centroids, axis=0)
            new_pts[vi] = new_pts[vi] + relax * (avg_c - new_pts[vi])

    return new_pts


def _try_hybrid_dual(
    pts,
    faces,
    owner,
    neighbour,
    cell_verts,
    tet_ids,
    non_tet_ids,
    case_dir: Path,
    *,
    interface_smoothing: bool = True,
    interface_smooth_iters: int = 2,
    interface_smooth_relax: float = 0.2,
) -> tuple[bool, str]:
    """v0.4.0-beta25 best-effort hybrid dual.

    전략:
        1. tet 서브셋만 추출 → 임시 디렉터리에서 ``tet_to_poly_dual`` 실행.
        2. non-tet (prism) cell 을 원본에서 face-list 형태로 복원.
        3. 두 집합을 ``write_generic_polymesh`` 로 합쳐 새 폴리메쉬 생성.
        4. interface face 는 prism outer 삼각형이 dual 결과의 boundary 에 동일한
           3-vertex 로 존재해야 매칭 — 존재하지 않으면 topology 불일치 →
           fallback (False 반환).

    주의: dual tet 서브셋이 prism outer 를 "boundary" 로 인식해야 tet_to_poly_dual
    의 boundary-vertex 처리가 원본 삼각형 정점을 유지함. tet subset 만 추출할 때
    prism 과의 인터페이스 face 도 tet subset 내에서 1-cell only face (= boundary)
    가 되므로 이 조건은 자연스럽게 만족.
    """
    import tempfile  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    from core.generator.native_poly.dual import tet_to_poly_dual  # noqa: PLC0415
    from core.generator.polymesh_writer import (  # noqa: PLC0415
        write_generic_polymesh,
    )
    from core.utils.polymesh_reader import (  # noqa: PLC0415
        parse_foam_faces,
        parse_foam_labels,
        parse_foam_points,
    )

    if len(tet_ids) == 0:
        return False, "no_tet_cells"

    try:
        # 0. interface smoothing — prism-tet 경계 vertex 를 centroid 방향으로
        # 살짝 이동해 face topology 불일치 감소 → dual 성공률 향상.
        working_pts = pts
        if interface_smoothing and interface_smooth_iters > 0:
            prism_set = set(non_tet_ids)
            working_pts = _smooth_interface_vertices(
                pts,
                faces,
                owner,
                neighbour,
                prism_cell_ids=prism_set,
                tet_cell_ids=tet_ids,
                n_iter=interface_smooth_iters,
                relax=interface_smooth_relax,
            )
            log.info(
                "poly_bl_hybrid_interface_smoothed",
                n_iter=interface_smooth_iters,
                relax=interface_smooth_relax,
            )

        # 1. tet 서브셋 — 원본 vertex indexing 그대로 유지 (boundary 정점이
        # prism 과 공유되므로 별도 remap 금지).
        tets_arr = np.array(
            [tuple(sorted(cell_verts[ci])) for ci in tet_ids],
            dtype=np.int64,
        )

        # 2. 임시 디렉터리에서 dual 수행 (smoothed vertex 좌표 사용)
        with tempfile.TemporaryDirectory(prefix="hybrid_dual_") as tmp:
            tmp_case = Path(tmp) / "dual_case"
            res = tet_to_poly_dual(working_pts, tets_arr, tmp_case)
            if not res.success:
                return False, f"tet_to_poly_dual_failed: {res.message}"

            # 3. dual 결과 읽기
            dual_poly = tmp_case / "constant" / "polyMesh"
            dual_pts = np.array(
                parse_foam_points(dual_poly / "points"),
                dtype=np.float64,
            )
            dual_faces = parse_foam_faces(dual_poly / "faces")
            dual_owner = np.array(
                parse_foam_labels(dual_poly / "owner"),
                dtype=np.int64,
            )
            dual_nbr = np.array(
                parse_foam_labels(dual_poly / "neighbour"),
                dtype=np.int64,
            )

            # 4. dual 의 cell-wise face-list 재구성 → write_generic_polymesh 입력 형식
            n_dual_cells = int(dual_owner.max()) + 1
            if len(dual_nbr):
                n_dual_cells = max(n_dual_cells, int(dual_nbr.max()) + 1)
            dual_cell_faces: list[list[list[int]]] = [[] for _ in range(n_dual_cells)]
            for fi, fv in enumerate(dual_faces):
                o = int(dual_owner[fi])
                dual_cell_faces[o].append(list(fv))
                if fi < len(dual_nbr):
                    n = int(dual_nbr[fi])
                    # neighbour 측도 같은 face 를 갖지만 orientation 은 반대
                    dual_cell_faces[n].append(list(reversed(fv)))

        # 5. 원본 prism cell 의 face-list 복원 — 원본 pts indexing 기준
        prism_cell_faces: list[list[list[int]]] = [[] for _ in range(len(non_tet_ids))]
        prism_idx_map = {ci: local_i for local_i, ci in enumerate(non_tet_ids)}
        for fi, fv in enumerate(faces):
            o = int(owner[fi])
            if o in prism_idx_map:
                prism_cell_faces[prism_idx_map[o]].append(list(fv))
            if fi < len(neighbour):
                n = int(neighbour[fi])
                if n in prism_idx_map:
                    prism_cell_faces[prism_idx_map[n]].append(
                        list(reversed(fv)),
                    )

        # 6. 두 point 집합 합치기 (working_pts 는 dual 의 boundary 정점과 교집합).
        # dual_pts 에 이미 원본 boundary 정점이 포함되어 있을 수 있으므로 좌표
        # 기반 dedup (scale quantization) 사용. smoothing 적용 후 좌표 사용.
        combined_V, vertex_remap_orig, vertex_remap_dual = _merge_vertices(
            working_pts,
            dual_pts,
        )

        # 7. cell_faces 재인덱싱
        def _remap_prism(face: list[int]) -> list[int]:
            return [int(vertex_remap_orig[int(v)]) for v in face]

        def _remap_dual(face: list[int]) -> list[int]:
            return [int(vertex_remap_dual[int(v)]) for v in face]

        combined_cell_faces: list[list[list[int]]] = []
        for cf in prism_cell_faces:
            combined_cell_faces.append([_remap_prism(f) for f in cf])
        for cf in dual_cell_faces:
            combined_cell_faces.append([_remap_dual(f) for f in cf])

        # 8. write_generic_polymesh — face dedup 이 canonical sorted 기반이라
        # interface 삼각형이 prism outer + dual boundary 양쪽에서 같은 3-vertex
        # 집합이면 자연스럽게 internal face 로 합쳐진다. 불일치 시 양쪽이 각자의
        # boundary 로 남아 mesh 는 여전히 valid (단 bulk-wall 간 연결 누락).
        stats = write_generic_polymesh(combined_V, combined_cell_faces, case_dir)
        log.info(
            "poly_bl_hybrid_dual_success",
            n_prism=len(prism_cell_faces),
            n_dual_cells=len(dual_cell_faces),
            **stats,
        )
        return True, (
            f"hybrid dual OK — prism={len(prism_cell_faces)}, "
            f"dual_cells={len(dual_cell_faces)}, faces={stats['num_faces']}"
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"hybrid_dual_exception: {exc}"


def _merge_vertices(
    orig_pts,
    dual_pts,
    tol: float = 1e-9,
):
    """두 vertex 집합을 좌표 양자화 기반으로 dedup 하여 합친다.

    Returns:
        (combined_V, remap_orig, remap_dual) — remap_* 는 각 원본 인덱스 → 합쳐진
        인덱스 매핑 (np.int64 array).
    """
    import numpy as np  # noqa: PLC0415

    scale = 1.0 / max(tol, 1e-30)
    orig_keys = np.round(orig_pts * scale).astype(np.int64)
    dual_keys = np.round(dual_pts * scale).astype(np.int64)

    all_keys = np.concatenate([orig_keys, dual_keys], axis=0)
    all_pts = np.concatenate([orig_pts, dual_pts], axis=0)
    uq_keys, inverse = np.unique(all_keys, axis=0, return_inverse=True)

    n_orig = orig_pts.shape[0]
    # 첫 등장 위치에서 좌표 추출
    combined_V = np.zeros((uq_keys.shape[0], 3), dtype=np.float64)
    seen = np.zeros(uq_keys.shape[0], dtype=bool)
    for i, new_idx in enumerate(inverse):
        if not seen[new_idx]:
            combined_V[new_idx] = all_pts[i]
            seen[new_idx] = True

    remap_orig = inverse[:n_orig].astype(np.int64)
    remap_dual = inverse[n_orig:].astype(np.int64)
    return combined_V, remap_orig, remap_dual


def run_poly_bl_transition(
    case_dir: Path,
    *,
    num_layers: int,
    growth_ratio: float,
    first_thickness: float,
    wall_patch_names: list[str] | None = None,
    backup_original: bool = True,
    max_total_ratio: float = 0.3,
    apply_bulk_dual: bool = True,
    dual_feature_angle: float = 30.0,
    interface_smooth_iters: int = 2,
) -> PolyBLResult:
    """poly 메쉬용 BL 삽입 + (옵션) bulk dual 변환.

    Args:
        case_dir: OpenFOAM case 디렉터리.
        num_layers/growth_ratio/first_thickness: BL 파라미터.
        apply_bulk_dual: True 이면 OpenFOAM polyDualMesh 로 bulk 를 dual 변환.
            False 이면 prism + tet 혼합 메쉬 그대로 반환.
        dual_feature_angle: polyDualMesh featureAngle (BL 을 보존하려면 낮게).

    Returns:
        PolyBLResult.
    """
    t0 = time.perf_counter()
    requested_layers = int(num_layers)
    if requested_layers < 0:
        return PolyBLResult(
            success=False,
            elapsed=time.perf_counter() - t0,
            message=f"boundary layer 수는 0 이상이어야 함: {requested_layers}",
        )
    if requested_layers == 0:
        blocker = _native_bl_zero_request_blocker(case_dir)
        if blocker is not None:
            return PolyBLResult(
                success=False,
                elapsed=time.perf_counter() - t0,
                message=blocker,
            )
        return PolyBLResult(
            success=True,
            elapsed=time.perf_counter() - t0,
            n_prism_cells=0,
            bulk_dual_applied=False,
            message="poly_bl_transition no-op — requested_layers=0, actual_layers=0",
        )

    cfg = BLConfig(
        num_layers=requested_layers,
        growth_ratio=float(growth_ratio),
        first_thickness=float(first_thickness),
        wall_patch_names=wall_patch_names,
        backup_original=backup_original,
        max_total_ratio=float(max_total_ratio),
    )
    local_front_key = "AUTO_TESSELL_NATIVE_BL_LOCAL_FRONT_QOPT"
    previous_local_front = os.environ.get(local_front_key)
    if _poly_quality_relocation_enabled():
        os.environ[local_front_key] = "1"
    try:
        bl_res = generate_native_bl(case_dir, cfg)
    finally:
        if previous_local_front is None:
            os.environ.pop(local_front_key, None)
        else:
            os.environ[local_front_key] = previous_local_front
    if not bl_res.success:
        return PolyBLResult(
            success=False,
            elapsed=time.perf_counter() - t0,
            message=f"native_bl 실패: {bl_res.message}",
        )

    bulk_dual_applied = False
    dual_msg = ""
    if apply_bulk_dual:
        # v0.4: OpenFOAM polyDualMesh 대신 자체 구현 tet→poly dual 사용.
        # dual_feature_angle 은 현재 native 경로에서 사용 안 함 (호환용으로 유지).
        ok, dual_msg = _try_native_poly_dual(
            case_dir,
            interface_smoothing=True,
            interface_smooth_iters=interface_smooth_iters,
        )
        bulk_dual_applied = ok
        if not ok:
            log.info("poly_bl_bulk_dual_skipped", reason=dual_msg)

    quality_relocation = None
    if _poly_quality_relocation_enabled():
        quality_relocation = _apply_native_poly_quality_relocation(case_dir)
        if quality_relocation.get("accepted") is not True:
            return PolyBLResult(
                success=False,
                elapsed=time.perf_counter() - t0,
                n_prism_cells=int(bl_res.n_prism_cells),
                bulk_dual_applied=bulk_dual_applied,
                message=(
                    "native Poly quality relocation refused with rollback: "
                    f"{quality_relocation.get('reason')}"
                ),
                quality_relocation=quality_relocation,
            )

    state_error = _refresh_native_bl_state_output(
        case_dir,
        last_transform=("poly_bl_transition_dual" if bulk_dual_applied else "poly_bl_transition"),
    )
    if state_error is not None:
        return PolyBLResult(
            success=False,
            elapsed=time.perf_counter() - t0,
            n_prism_cells=int(bl_res.n_prism_cells),
            bulk_dual_applied=bulk_dual_applied,
            message=state_error,
            quality_relocation=quality_relocation,
        )

    strict = audit_strict_volume_topology(case_dir)
    if not strict.valid:
        return PolyBLResult(
            success=False,
            elapsed=time.perf_counter() - t0,
            n_prism_cells=int(bl_res.n_prism_cells),
            bulk_dual_applied=bulk_dual_applied,
            message=(
                "poly_bl_transition strict topology rejected: "
                f"duplicate={strict.n_duplicate_faces}, "
                f"nonmanifold={strict.n_nonmanifold_faces}, "
                f"cell_edges={strict.n_nonmanifold_cell_edges}, "
                f"open_edges={strict.n_open_cell_edges}, "
                f"inverted={strict.n_inverted_cells}"
            ),
        )
    elapsed = time.perf_counter() - t0
    return PolyBLResult(
        success=True,
        elapsed=elapsed,
        n_prism_cells=int(bl_res.n_prism_cells),
        bulk_dual_applied=bulk_dual_applied,
        message=(
            f"poly_bl_transition OK — prism={bl_res.n_prism_cells}, "
            f"bulk_dual={bulk_dual_applied}. "
            + (f"dual: {dual_msg}" if apply_bulk_dual else "dual skipped")
        ),
    )
