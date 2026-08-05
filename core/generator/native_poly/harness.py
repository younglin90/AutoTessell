"""NativePolyHarness — Generator ↔ Evaluator 반복으로 poly mesh 품질 수렴.

5-Agent 하네스 패턴을 poly mesh 생성에도 적용:
  1. Generator: native_tet → tet_to_poly_dual → polyMesh.
  2. Evaluator: NativeMeshChecker + open_cells / negative_volume / skewness 판정.
  3. FAIL → Generator 파라미터 조정 (seed_density↑, sliver q↑) 후 재시도.
  4. 최대 iter 까지 반복, PASS 또는 iter 초과 시 종료.

기존 core/generator/native_poly/voronoi.py 의 scipy Voronoi 기반 경로는 legacy
fallback 으로 유지 (dual 경로가 우선).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Mapping

import numpy as np

from core.generator.native_poly.dual import PolyDualResult, tet_to_poly_dual
from core.generator.native_tet import NativeTetResult, generate_native_tet
from core.evaluator.native_poly_quality_admission import assess_native_poly_quality
from core.utils.logging import get_logger

log = get_logger(__name__)


def _install_polymesh_only(src_case: Path, dst_case: Path) -> None:
    """Install generated polyMesh without deleting pipeline metadata.

    The orchestrator stores ``geometry_report.json`` and the preprocessed STL
    under the case directory before generation.  Deleting the whole case here
    makes later fidelity checks look "missing" even when the mesh exists.
    """
    src_poly = src_case / "constant" / "polyMesh"
    if not src_poly.is_dir():
        raise FileNotFoundError(f"polyMesh 없음: {src_poly}")
    dst_poly = dst_case / "constant" / "polyMesh"
    if dst_poly.exists():
        shutil.rmtree(dst_poly)
    dst_poly.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_poly, dst_poly)
    staged_receipt = src_case / "native_poly_staged_feasibility.json"
    if staged_receipt.is_file():
        shutil.copy2(staged_receipt, dst_case / staged_receipt.name)


@dataclass
class PolyHarnessResult:
    success: bool
    elapsed: float
    iterations: int
    n_cells: int = 0
    n_points: int = 0
    open_cells: int = 0
    negative_volumes: int = 0
    max_non_ortho: float = 0.0
    max_skewness: float = 0.0
    max_aspect_ratio: float = 0.0
    message: str = ""
    target_cells_requested: int | None = None
    tet_cells_by_iteration: tuple[int, ...] = ()
    final_poly_cells: int = 0
    target_cells_absolute_error: int | None = None
    target_cells_relative_error: float | None = None
    target_cells_status: str = "not_requested"


def _target_observation(
    target_cells: int | None,
    final_poly_cells: int,
) -> tuple[int | None, int | None, float | None, str]:
    """Return report-only target evidence without admitting or rejecting a mesh."""
    if target_cells is None or int(target_cells) <= 0:
        return None, None, None, "not_requested"
    requested = int(target_cells)
    absolute_error = abs(int(final_poly_cells) - requested)
    relative_error = absolute_error / requested
    return requested, absolute_error, relative_error, "reported_not_gated"


def _run_staged_native_poly_transaction(
    case_dir: Path,
    *,
    boundary_layer: bool,
    source_certificate: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Apply the C++ staged candidate only inside a temporary release case.

    This deliberately does not require the pre-candidate mesh to be valid:
    the candidate search may repair a local signed-volume defect. The normal
    independent evaluator below remains the only publication gate.
    """
    import numpy as np
    from core.layers.native_bl import _write_points
    from core.utils.polymesh_reader import (
        parse_foam_faces,
        parse_foam_labels_array,
        parse_foam_points_array,
    )

    case = Path(case_dir)
    poly = case / "constant" / "polyMesh"
    receipt_path = case / "native_poly_staged_feasibility.json"
    kernel = None
    try:
        from core.utils.native_extensions import load_native_poly_quality_relocation
        kernel = load_native_poly_quality_relocation()
    except Exception:
        kernel = None
    if kernel is None:
        report = {
            "accepted": False,
            "status": "refused_rollback",
            "reason": "native_kernel_unavailable",
            "boundary_layer_profile": "bl" if boundary_layer else "core",
        }
        receipt_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return report
    try:
        points_path = poly / "points"
        points_before = np.asarray(parse_foam_points_array(points_path), dtype=np.float64)
        points_original_bytes = points_path.read_bytes()
        _authority_before_ok, authority_before = _evaluate_poly_mesh(case, quality_gate=False)
        faces_before = parse_foam_faces(poly / "faces")
        owner_before = np.asarray(parse_foam_labels_array(poly / "owner"), dtype=np.int64)
        neighbour_before = np.asarray(parse_foam_labels_array(poly / "neighbour"), dtype=np.int64)
        flat = np.asarray([int(vertex) for face in faces_before for vertex in face], dtype=np.int64)
        offsets = np.zeros(len(faces_before) + 1, dtype=np.int64)
        offsets[1:] = np.cumsum([len(face) for face in faces_before], dtype=np.int64)
        boundary_ids = np.asarray(
            sorted({int(vertex) for face in faces_before[len(neighbour_before):] for vertex in face}),
            dtype=np.int64,
        )
        diagonal = float(np.linalg.norm(points_before.max(axis=0) - points_before.min(axis=0)))
        iterations = int(os.environ.get("AUTO_TESSELL_POLY_NATIVE_STAGED_ITER", "2"))
        relax = float(os.environ.get("AUTO_TESSELL_POLY_NATIVE_STAGED_RELAX", "0.15"))
        max_move_ratio = float(os.environ.get("AUTO_TESSELL_POLY_NATIVE_STAGED_MAX_MOVE_RATIO", "0.02"))
        focus_non_orthogonality = os.environ.get(
            "AUTO_TESSELL_POLY_NATIVE_FOCUS_NON_ORTHOGONALITY", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
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
            focus_non_orthogonality,
        ))
        candidate = np.asarray(cpp_result.get("points"), dtype=np.float64)
        if cpp_result.get("accepted") is not True:
            report = {
                "accepted": False,
                "status": "candidate_rejected",
                "reason": cpp_result.get("reason", "candidate_rejected"),
                "boundary_layer_profile": "bl" if boundary_layer else "core",
                "destination_is_temporary": True,
                "cpp": {key: value for key, value in cpp_result.items() if key != "points"},
            }
            receipt_path.write_text(
                json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            return report
        if candidate.shape != points_before.shape or not np.isfinite(candidate).all():
            raise RuntimeError("candidate_shape_or_finite_gate")
        if not np.array_equal(
            np.ascontiguousarray(points_before[boundary_ids]).view(np.uint64),
            np.ascontiguousarray(candidate[boundary_ids]).view(np.uint64),
        ):
            raise RuntimeError("boundary_bits_changed")
        if parse_foam_faces(poly / "faces") != faces_before:
            raise RuntimeError("faces_changed")
        if not np.array_equal(parse_foam_labels_array(poly / "owner"), owner_before):
            raise RuntimeError("owner_changed")
        if not np.array_equal(parse_foam_labels_array(poly / "neighbour"), neighbour_before):
            raise RuntimeError("neighbour_changed")
        _write_points(points_path, candidate, precision=17)
        _authority_after_ok, authority_after = _evaluate_poly_mesh(case, quality_gate=False)
        cpp_metrics_after = dict(cpp_result.get("metrics_after") or {})
        metric_pairs = {
            "max_non_orthogonality_deg": "max_non_orthogonality",
            "max_skewness": "max_skewness",
            "max_aspect_ratio": "max_aspect_ratio",
        }
        metric_deltas: dict[str, float | None] = {}
        metric_parity = True
        for cpp_key, authority_key in metric_pairs.items():
            try:
                cpp_value = float(cpp_metrics_after[cpp_key])
                authority_value = float(authority_after[authority_key])
                delta = abs(cpp_value - authority_value)
                metric_deltas[cpp_key] = delta
                metric_parity = metric_parity and bool(
                    delta <= 1e-9 * max(1.0, abs(cpp_value), abs(authority_value))
                )
            except (KeyError, TypeError, ValueError):
                metric_deltas[cpp_key] = None
                metric_parity = False

        import hashlib

        def _sha256_bytes(value: bytes) -> str:
            return hashlib.sha256(value).hexdigest()

        def _sha256_file(path: Path) -> str:
            return _sha256_bytes(path.read_bytes()) if path.is_file() else ""

        topology_bytes = b"".join(
            path.read_bytes() for path in (poly / "faces", poly / "owner", poly / "neighbour")
        )
        certificate = dict(source_certificate or {})
        source_certificate_hash = str(
            certificate.get("certificate_sha256") or _sha256_file(case / "geometry_report.json")
        )
        ledger_hashes = {
            "source_certificate_hash": source_certificate_hash,
            "source_snapshot_hash": str(certificate.get("raw_source_sha256") or ""),
            "preprocessed_ingress_hash": str(
                certificate.get("preprocessed_ingress_sha256") or ""
            ),
            "output_geometry_hash": _sha256_file(points_path),
            "output_topology_hash": _sha256_bytes(topology_bytes),
            "boundary_patch_physical_group_hash": _sha256_file(poly / "boundary"),
        }
        authority_receipt = {
            "before": authority_before,
            "after": authority_after,
            "before_passed": bool(_authority_before_ok),
            "after_passed": bool(_authority_after_ok),
            "metric_pairs": metric_pairs,
            "metric_deltas": metric_deltas,
            "metric_parity": bool(metric_parity),
            "metric_parity_tolerance": 1e-9,
            "source_certificate": certificate,
            "source_certificate_verified": bool(
                certificate.get("certificate_sha256")
            ),
            "authority_chain_complete": bool(certificate.get("authority_chain_complete")),
            "ledger_hashes": ledger_hashes,
        }
        if not metric_parity:
            points_path.write_bytes(points_original_bytes)
            report = {
                "accepted": False,
                "status": "refused_rollback",
                "reason": "authority_metric_parity_mismatch",
                "boundary_layer_profile": "bl" if boundary_layer else "core",
                "destination_is_temporary": True,
                "source_topology_unchanged": True,
                "authority_receipt": authority_receipt,
                "cpp": {key: value for key, value in cpp_result.items() if key != "points"},
            }
            receipt_path.write_text(
                json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            return report
        report = {
            "accepted": True,
            "status": "candidate_applied_to_temporary_case",
            "reason": cpp_result.get("reason", ""),
            "boundary_layer_profile": "bl" if boundary_layer else "core",
            "destination_is_temporary": True,
            "source_topology_unchanged": True,
            "authority_receipt": authority_receipt,
            "cpp": {key: value for key, value in cpp_result.items() if key != "points"},
        }
        receipt_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return report
    except Exception as exc:
        report = {
            "accepted": False,
            "status": "refused_rollback",
            "reason": str(exc),
            "boundary_layer_profile": "bl" if boundary_layer else "core",
        }
        receipt_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return report


def _evaluate_poly_mesh(
    case_dir: Path,
    *,
    quality_gate: bool = False,
) -> tuple[bool, dict]:
    """NativeMeshChecker 로 open cells / negative volume / skewness 확인.

    Returns:
        (passed, metrics)
        passed = mesh 생성 OK + negative_volumes == 0.  Release callers may
        additionally request the independent quality-first admission.
    """
    try:
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415
    except Exception as exc:
        return False, {"error": f"NativeMeshChecker import 실패: {exc}"}

    try:
        r = NativeMeshChecker().run(case_dir)
    except Exception as exc:
        return False, {"error": f"check 실패: {exc}"}

    try:
        from core.evaluator.strict_volume_topology import audit_strict_volume_topology
        strict = audit_strict_volume_topology(case_dir)
    except Exception:
        return False, dict(strict_topology_valid=False)
    metrics = {
        "cells": int(r.cells),
        "points": int(r.points),
        "max_non_orthogonality": float(r.max_non_orthogonality),
        "max_skewness": float(r.max_skewness),
        "max_aspect_ratio": float(r.max_aspect_ratio),
        "negative_volumes": int(r.negative_volumes),
        "mesh_ok": bool(r.mesh_ok),
    }
    metrics.update(strict_topology_valid=bool(strict.valid))
    passed = bool(strict.valid) and r.negative_volumes == 0 and r.cells > 0
    if quality_gate:
        admission = assess_native_poly_quality(metrics)
        metrics["quality_admission"] = admission.as_dict()
        metrics["quality_gate_reason"] = admission.reason
        passed = admission.accepted
    return passed, metrics


def run_native_poly_harness(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    target_cells: int | None = None,
    seed_density: int = 10,
    max_iter: int = 2,
    max_tet_cells: int = 30000,
    smooth_iters: int = 0,
    smooth_relax: float = 0.3,
    boundary_face_classifier: Callable[[tuple[int, int, int], np.ndarray], object] | None = None,
    release_route: bool = False,
    boundary_layer: bool = False,
    source_certificate: Mapping[str, object] | None = None,
    allow_external_fallback: bool | None = None,
    timeout_seconds: float | None = None,
) -> PolyHarnessResult:
    """Generator (native_tet → dual) ↔ Evaluator 반복으로 poly mesh 생성.

    각 iteration 에서 FAIL 시 seed_density 를 증가 (더 조밀) 시도.

    beta97:
        smooth_iters > 0 이면 dual 변환 후 Laplacian smoothing 으로 경계 근방
        stretched cell 개선.
    """
    t0 = time.perf_counter()
    try:
        _timeout = float(timeout_seconds or 0.0)
    except (TypeError, ValueError):
        _timeout = 0.0
    deadline = t0 + _timeout if _timeout > 0.0 else None

    def _timed_out() -> bool:
        return deadline is not None and time.perf_counter() >= deadline

    # Release-only structured rescue for extreme thin extrusions such as NACA.
    # It is an independent polyhedral route; legacy/default dual behavior is
    # untouched. The written artifact remains the admission authority.
    if release_route and target_cells is None:
        try:
            from core.generator.native_tet.thin_extrusion import (
                build_thin_extrusion_wedges,
            )
            from core.generator.polymesh_writer import write_generic_polymesh

            extrusion = build_thin_extrusion_wedges(
                np.asarray(vertices, dtype=np.float64),
                np.asarray(faces, dtype=np.int64),
                target_cells=100,
                bl_layers=1,
                min_bbox_aspect=5.0,
            )
            if extrusion is None:
                from core.generator.native_poly.planar_extrusion import (
                    build_planar_extrusion_wedges,
                )
                extrusion = build_planar_extrusion_wedges(
                    np.asarray(vertices, dtype=np.float64),
                    np.asarray(faces, dtype=np.int64),
                    target_cells=100,
                    min_bbox_aspect=5.0,
                )
            if extrusion is not None:
                write_generic_polymesh(
                    extrusion.points,
                    extrusion.cell_faces,
                    case_dir,
                    boundary_patch_classifier=boundary_face_classifier,
                    strict=True,
                    point_precision=17,
                )
                if release_route:
                    passed, metrics = _evaluate_poly_mesh(
                        case_dir,
                        quality_gate=True,
                    )
                else:
                    passed, metrics = _evaluate_poly_mesh(case_dir)
                if passed:
                    return PolyHarnessResult(
                        success=True,
                        elapsed=time.perf_counter() - t0,
                        iterations=1,
                        n_cells=int(metrics["cells"]),
                        n_points=int(metrics["points"]),
                        negative_volumes=int(metrics["negative_volumes"]),
                        max_non_ortho=float(metrics["max_non_orthogonality"]),
                        max_skewness=float(metrics["max_skewness"]),
                        message="native_poly release thin-extrusion route accepted",
                        final_poly_cells=int(metrics["cells"]),
                        target_cells_status="not_requested",
                    )
                shutil.rmtree(case_dir / "constant" / "polyMesh", ignore_errors=True)
        except Exception as exc:
            log.warning("native_poly_release_thin_route_rejected", error=str(exc)[:200])
            shutil.rmtree(case_dir / "constant" / "polyMesh", ignore_errors=True)

    # Explicit BL=0 poly targets must not enter a known-unbounded tet path.
    # The uniform floor-grid requires interior work in addition to its nodes;
    # reserve a conservative 2x overhead before generation starts.
    try:
        vertex_array = np.asarray(vertices)
        face_array = np.asarray(faces)
        finite_vertices = bool(np.isfinite(vertex_array).all())
    except (TypeError, ValueError):
        vertex_array = np.asarray(())
        face_array = np.asarray(())
        finite_vertices = False
    preflight_eligible = (
        vertex_array.ndim == 2
        and vertex_array.shape[1:] == (3,)
        and vertex_array.shape[0] > 0
        and finite_vertices
        and face_array.ndim == 2
        and face_array.shape[1:] == (3,)
        and face_array.shape[0] > 0
        and np.issubdtype(face_array.dtype, np.integer)
        and int(face_array.min()) >= 0
        and int(face_array.max()) < vertex_array.shape[0]
    )
    if (
        preflight_eligible
        and target_cells is not None
        and int(target_cells) > 0
        and target_edge_length is not None
    ):
        bmin = np.asarray(vertices).min(axis=0)
        bmax = np.asarray(vertices).max(axis=0)
        diag = float(np.linalg.norm(bmax - bmin))
        floor = diag / 50.0
        if floor > 0.0 and float(target_edge_length) < floor:
            grid_nodes = np.ceil((bmax - bmin) / floor).astype(np.int64) + 1
            estimated_work = int(np.prod(grid_nodes)) * 2
            if estimated_work > int(max_tet_cells):
                return PolyHarnessResult(
                    success=False,
                    elapsed=time.perf_counter() - t0,
                    iterations=0,
                    message=(
                        "target_poly_budget_unreachable: "
                        f"requested={int(target_cells)}, edge_floor={floor:.9g}, "
                        f"estimated_work={estimated_work}, budget={int(max_tet_cells)}"
                    ),
                    target_cells_requested=int(target_cells),
                    target_cells_status="refused_budget_preflight",
                )

    # target_edge_length 하한: bbox_diag / 50 이하로 내려가면 (= seed 가 50+)
    # tet mesh cell 수가 폭증하므로 clamp.
    if target_edge_length is not None and preflight_eligible:
        bmin = np.asarray(vertices).min(axis=0)
        bmax = np.asarray(vertices).max(axis=0)
        diag = float(np.linalg.norm(bmax - bmin))
        floor = diag / 50.0
        if target_edge_length < floor:
            log.info(
                "native_poly_harness_target_edge_clamp",
                requested=target_edge_length,
                clamped_to=floor,
                reason="tet cell explosion 방지",
            )
            target_edge_length = floor

    last_metrics: dict = {}
    best_result: PolyDualResult | None = None
    best_case_bytes: Path | None = None
    best_metrics: dict = {}
    current_seed = int(seed_density)
    tet_cells_by_iteration: list[int] = []
    floor_failures: list[str] = []
    min_final_vertices = (
        max(int(vertex_array.shape[0]) + 1, int(ceil(int(target_cells) * 0.8)))
        if preflight_eligible and target_cells is not None and int(target_cells) > 0
        else None
    )

    for it in range(1, int(max_iter) + 1):
        if _timed_out():
            return PolyHarnessResult(
                success=False,
                elapsed=time.perf_counter() - t0,
                iterations=it - 1,
                message="native_poly_timeout_budget_exceeded",
            )
        log.info(
            "native_poly_harness_iter",
            iteration=it,
            seed_density=current_seed,
        )
        # 1) Generator: native_tet
        tmp_tet = Path(tempfile.mkdtemp(prefix=f"nph_tet_{it}_"))
        try:
            tet_target_edge = target_edge_length
            if (
                tet_target_edge is None
                and target_cells is not None
                and 0 < int(target_cells) <= 200
            ):
                bbox_span = float(np.prod(np.ptp(np.asarray(vertices), axis=0)))
                if bbox_span > 0.0:
                    # The dual has one cell per retained primal vertex; the
                    # native-tet volume heuristic is too coarse for small
                    # Poly budgets, so request an 8x denser primal volume.
                    tet_target_edge = float(
                        (bbox_span / (0.118 * int(target_cells))) ** (1.0 / 3.0)
                        * 0.5
                    )
            tet_res: NativeTetResult = generate_native_tet(
                vertices,
                faces,
                tmp_tet,
                target_edge_length=tet_target_edge,
                target_cells=target_cells,
                enable_same_side_retriangulation=True,
                allow_external_fallback=allow_external_fallback,
                # Prefer a populated primal for explicit poly cell budgets.
                prefer_base_threshold=(
                    0.10
                    if target_cells is not None and int(target_cells) > 0
                    else 0.02
                ),
                min_final_vertices=min_final_vertices,
                seed_density=current_seed,
            )
            if _timed_out():
                return PolyHarnessResult(
                    success=False,
                    elapsed=time.perf_counter() - t0,
                    iterations=it,
                    message="native_poly_timeout_budget_exceeded",
                    tet_cells_by_iteration=tuple(tet_cells_by_iteration),
                )
            if not tet_res.success or tet_res.tets is None:
                if tet_res.message.startswith("target_primal_vertex_floor_unmet:"):
                    floor_failures.append(tet_res.message)
                log.warning(
                    "native_poly_harness_tet_fail",
                    iteration=it,
                    message=tet_res.message,
                )
                current_seed = int(current_seed * 1.5)
                continue

            # tet cell 수 cap — dual 변환 비용이 O(V) 이므로 거대 mesh 피함.
            n_tet_cells = int(tet_res.tets.shape[0])
            tet_cells_by_iteration.append(n_tet_cells)
            if n_tet_cells > max_tet_cells:
                log.warning(
                    "native_poly_harness_tet_too_large",
                    n_cells=n_tet_cells,
                    cap=max_tet_cells,
                    iteration=it,
                )
                # target_edge_length 를 늘려 tet mesh 를 더 성기게 + seed 도 감소
                if target_edge_length is not None:
                    target_edge_length = float(target_edge_length) * 1.6
                current_seed = max(int(current_seed * 0.6), 3)
                if it < max_iter:
                    continue
                # 마지막 iter 에서는 진행 (TIMEOUT 보다 나음)

            # 2) tet → dual
            tmp_dual = Path(tempfile.mkdtemp(prefix=f"nph_dual_{it}_"))
            dual_res = tet_to_poly_dual(
                tet_res.tet_points,
                tet_res.tets,
                tmp_dual,
                boundary_face_classifier=boundary_face_classifier,
                allow_nonstar_topology=True,
            )
            if not dual_res.success:
                log.warning(
                    "native_poly_harness_dual_fail",
                    iteration=it,
                    message=dual_res.message,
                )
                current_seed = int(current_seed * 1.5)
                shutil.rmtree(tmp_dual, ignore_errors=True)
                continue

            # 2b) beta97: dual 이후 Laplacian smoothing — boundary cell 품질↑
            if smooth_iters > 0:
                try:
                    from core.generator.native_poly.smooth import smooth_poly_mesh  # noqa: PLC0415

                    s_res = smooth_poly_mesh(
                        tmp_dual,
                        n_iter=smooth_iters,
                        relax=smooth_relax,
                    )
                    log.info(
                        "native_poly_harness_smooth",
                        iteration=it,
                        n_iter=s_res.n_iter_done,
                        max_disp=s_res.max_displacement,
                    )
                except Exception as exc:
                    log.warning("native_poly_harness_smooth_fail", error=str(exc))

            # 2c) release-only staged C++ feasibility/quality candidate.
            staged_report: dict[str, object] | None = None
            if release_route:
                staged_report = _run_staged_native_poly_transaction(
                    tmp_dual,
                    boundary_layer=boundary_layer,
                    source_certificate=source_certificate,
                )
                log.info(
                    "native_poly_harness_staged_transaction",
                    iteration=it,
                    accepted=staged_report.get("accepted"),
                    reason=staged_report.get("reason"),
                    boundary_layer=boundary_layer,
                )

            # 3) Evaluate
            if release_route:
                passed, metrics = _evaluate_poly_mesh(
                    tmp_dual,
                    quality_gate=True,
                )
            else:
                passed, metrics = _evaluate_poly_mesh(tmp_dual)
            last_metrics = metrics
            log.info(
                "native_poly_harness_eval",
                iteration=it,
                passed=passed,
                **metrics,
            )

            # 최고 후보 추적 — negative_volumes 가 더 적거나, 같으면 cells 가 더 많은 쪽.
            cur_neg = int(metrics.get("negative_volumes", 10**9))
            cur_cells = int(metrics.get("cells", 0))
            best_neg = int(best_metrics.get("negative_volumes", 10**9))
            best_cells = int(best_metrics.get("cells", 0))
            is_better = best_result is None or (
                cur_neg < best_neg or (cur_neg == best_neg and cur_cells > best_cells)
            )
            if is_better:
                best_result = dual_res
                best_metrics = dict(metrics)
                if best_case_bytes is not None:
                    shutil.rmtree(best_case_bytes, ignore_errors=True)
                best_case_bytes = tmp_dual
            else:
                shutil.rmtree(tmp_dual, ignore_errors=True)

            if passed:
                # 최종 case_dir 로 이동
                _install_polymesh_only(tmp_dual, case_dir)
                shutil.rmtree(tmp_dual, ignore_errors=True)
                requested, absolute_error, relative_error, target_status = _target_observation(
                    target_cells,
                    int(metrics["cells"]),
                )
                log.info(
                    "native_poly_harness_target_observation",
                    requested_target_cells=requested,
                    tet_cells_by_iteration=tuple(tet_cells_by_iteration),
                    final_poly_cells=int(metrics["cells"]),
                    target_cells_absolute_error=absolute_error,
                    target_cells_relative_error=relative_error,
                    target_cells_status=target_status,
                )
                return PolyHarnessResult(
                    success=True,
                    elapsed=time.perf_counter() - t0,
                    iterations=it,
                    n_cells=metrics["cells"],
                    n_points=metrics["points"],
                    open_cells=0,
                    negative_volumes=metrics["negative_volumes"],
                    max_non_ortho=metrics["max_non_orthogonality"],
                    max_skewness=metrics["max_skewness"],
                    max_aspect_ratio=metrics["max_aspect_ratio"],
                    message=(
                        f"native_poly_harness PASS iter={it}, cells={metrics['cells']}, "
                        f"non_ortho={metrics['max_non_orthogonality']:.1f}°, "
                        f"skew={metrics['max_skewness']:.2f}"
                    ),
                    target_cells_requested=requested,
                    tet_cells_by_iteration=tuple(tet_cells_by_iteration),
                    final_poly_cells=int(metrics["cells"]),
                    target_cells_absolute_error=absolute_error,
                    target_cells_relative_error=relative_error,
                    target_cells_status=target_status,
                )
            # 실패 → seed density 올려 재시도 (완만하게 — 1.5→1.2)
            current_seed = max(int(current_seed * 1.2), current_seed + 1)
        finally:
            shutil.rmtree(tmp_tet, ignore_errors=True)

    # 모든 iter 실패 — 가장 품질 좋은 결과 복사 (best effort)
    if best_case_bytes is not None and best_case_bytes.exists():
        _install_polymesh_only(best_case_bytes, case_dir)
        shutil.rmtree(best_case_bytes, ignore_errors=True)
    final_poly_cells = int(last_metrics.get("cells", 0))
    requested, absolute_error, relative_error, target_status = _target_observation(
        target_cells,
        final_poly_cells,
    )
    log.info(
        "native_poly_harness_target_observation",
        requested_target_cells=requested,
        tet_cells_by_iteration=tuple(tet_cells_by_iteration),
        final_poly_cells=final_poly_cells,
        target_cells_absolute_error=absolute_error,
        target_cells_relative_error=relative_error,
        target_cells_status=target_status,
    )
    final_message = (
        floor_failures[-1]
        if floor_failures and len(floor_failures) == int(max_iter)
        else (
            f"native_poly_harness FAIL after {max_iter} iter "
            f"(best negative_volumes={last_metrics.get('negative_volumes', -1)})"
        )
    )
    return PolyHarnessResult(
        success=False,
        elapsed=time.perf_counter() - t0,
        iterations=int(max_iter),
        n_cells=final_poly_cells,
        n_points=last_metrics.get("points", 0),
        negative_volumes=last_metrics.get("negative_volumes", 0),
        max_non_ortho=float(last_metrics.get("max_non_orthogonality", 0.0)),
        max_skewness=float(last_metrics.get("max_skewness", 0.0)),
        max_aspect_ratio=float(last_metrics.get("max_aspect_ratio", 0.0)),
        message=final_message,
        target_cells_requested=requested,
        tet_cells_by_iteration=tuple(tet_cells_by_iteration),
        final_poly_cells=final_poly_cells,
        target_cells_absolute_error=absolute_error,
        target_cells_relative_error=relative_error,
        target_cells_status=target_status,
    )
