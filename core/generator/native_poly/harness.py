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

import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from pathlib import Path

import numpy as np

from core.generator.native_poly.dual import PolyDualResult, tet_to_poly_dual
from core.generator.native_tet import NativeTetResult, generate_native_tet
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


def _evaluate_poly_mesh(case_dir: Path) -> tuple[bool, dict]:
    """NativeMeshChecker 로 open cells / negative volume / skewness 확인.

    Returns:
        (passed, metrics)
        passed = mesh 생성 OK + negative_volumes == 0
    """
    try:
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415
    except Exception as exc:
        return False, {"error": f"NativeMeshChecker import 실패: {exc}"}

    try:
        r = NativeMeshChecker().run(case_dir)
    except Exception as exc:
        return False, {"error": f"check 실패: {exc}"}

    metrics = {
        "cells": int(r.cells),
        "points": int(r.points),
        "max_non_orthogonality": float(r.max_non_orthogonality),
        "max_skewness": float(r.max_skewness),
        "negative_volumes": int(r.negative_volumes),
        "mesh_ok": bool(r.mesh_ok),
    }
    passed = metrics["negative_volumes"] == 0 and metrics["cells"] > 0
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
) -> PolyHarnessResult:
    """Generator (native_tet → dual) ↔ Evaluator 반복으로 poly mesh 생성.

    각 iteration 에서 FAIL 시 seed_density 를 증가 (더 조밀) 시도.

    beta97:
        smooth_iters > 0 이면 dual 변환 후 Laplacian smoothing 으로 경계 근방
        stretched cell 개선.
    """
    t0 = time.perf_counter()

    # Explicit BL=0 poly targets must not enter a known-unbounded tet path.
    # The uniform floor-grid requires interior work in addition to its nodes;
    # reserve a conservative 2x overhead before generation starts.
    if target_cells is not None and int(target_cells) > 0 and target_edge_length is not None:
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
                    target_cells_status="reported_not_gated",
                )

    # target_edge_length 하한: bbox_diag / 50 이하로 내려가면 (= seed 가 50+)
    # tet mesh cell 수가 폭증하므로 clamp.
    if target_edge_length is not None:
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
        max(int(np.asarray(vertices).shape[0]) + 1, int(ceil(int(target_cells) * 0.5)))
        if target_cells is not None and int(target_cells) > 0
        else None
    )

    for it in range(1, int(max_iter) + 1):
        log.info(
            "native_poly_harness_iter",
            iteration=it,
            seed_density=current_seed,
        )
        # 1) Generator: native_tet
        tmp_tet = Path(tempfile.mkdtemp(prefix=f"nph_tet_{it}_"))
        try:
            tet_res: NativeTetResult = generate_native_tet(
                vertices,
                faces,
                tmp_tet,
                target_edge_length=target_edge_length,
                target_cells=target_cells,
                min_final_vertices=min_final_vertices,
                seed_density=current_seed,
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

            # 3) Evaluate
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
        message=final_message,
        target_cells_requested=requested,
        tet_cells_by_iteration=tuple(tet_cells_by_iteration),
        final_poly_cells=final_poly_cells,
        target_cells_absolute_error=absolute_error,
        target_cells_relative_error=relative_error,
        target_cells_status=target_status,
    )
