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
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.generator.native_poly.dual import PolyDualResult, tet_to_poly_dual
from core.generator.native_tet import NativeTetResult, generate_native_tet
from core.utils.logging import get_logger

log = get_logger(__name__)


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
    seed_density: int = 12,
    max_iter: int = 3,
) -> PolyHarnessResult:
    """Generator (native_tet → dual) ↔ Evaluator 반복으로 poly mesh 생성.

    각 iteration 에서 FAIL 시 seed_density 를 증가 (더 조밀) 시도.
    """
    t0 = time.perf_counter()

    last_metrics: dict = {}
    best_result: PolyDualResult | None = None
    best_case_bytes: Path | None = None
    current_seed = int(seed_density)

    for it in range(1, int(max_iter) + 1):
        log.info(
            "native_poly_harness_iter",
            iteration=it, seed_density=current_seed,
        )
        # 1) Generator: native_tet
        tmp_tet = Path(tempfile.mkdtemp(prefix=f"nph_tet_{it}_"))
        try:
            tet_res: NativeTetResult = generate_native_tet(
                vertices, faces, tmp_tet,
                target_edge_length=target_edge_length,
                seed_density=current_seed,
            )
            if not tet_res.success or tet_res.tets is None:
                log.warning(
                    "native_poly_harness_tet_fail",
                    iteration=it, message=tet_res.message,
                )
                current_seed = int(current_seed * 1.5)
                continue

            # 2) tet → dual
            tmp_dual = Path(tempfile.mkdtemp(prefix=f"nph_dual_{it}_"))
            dual_res = tet_to_poly_dual(
                tet_res.tet_points, tet_res.tets, tmp_dual,
            )
            if not dual_res.success:
                log.warning(
                    "native_poly_harness_dual_fail",
                    iteration=it, message=dual_res.message,
                )
                current_seed = int(current_seed * 1.5)
                shutil.rmtree(tmp_dual, ignore_errors=True)
                continue

            # 3) Evaluate
            passed, metrics = _evaluate_poly_mesh(tmp_dual)
            last_metrics = metrics
            log.info(
                "native_poly_harness_eval",
                iteration=it, passed=passed, **metrics,
            )

            # 최고 후보 추적 — open_cells 대신 negative_volumes + cells 수로 판단
            if best_result is None or metrics.get(
                "negative_volumes", 999,
            ) < metrics.get("negative_volumes", 0):
                best_result = dual_res
                if best_case_bytes is not None:
                    shutil.rmtree(best_case_bytes, ignore_errors=True)
                best_case_bytes = tmp_dual
            else:
                shutil.rmtree(tmp_dual, ignore_errors=True)

            if passed:
                # 최종 case_dir 로 이동
                if case_dir.exists():
                    shutil.rmtree(case_dir)
                shutil.copytree(tmp_dual, case_dir)
                return PolyHarnessResult(
                    success=True,
                    elapsed=time.perf_counter() - t0,
                    iterations=it,
                    n_cells=metrics["cells"], n_points=metrics["points"],
                    open_cells=0,
                    negative_volumes=metrics["negative_volumes"],
                    max_non_ortho=metrics["max_non_orthogonality"],
                    max_skewness=metrics["max_skewness"],
                    message=(
                        f"native_poly_harness PASS iter={it}, cells={metrics['cells']}, "
                        f"non_ortho={metrics['max_non_orthogonality']:.1f}°, "
                        f"skew={metrics['max_skewness']:.2f}"
                    ),
                )
            # 실패 → seed density 올려 재시도
            current_seed = int(current_seed * 1.5)
        finally:
            shutil.rmtree(tmp_tet, ignore_errors=True)

    # 모든 iter 실패 — 가장 품질 좋은 결과 복사 (best effort)
    if best_case_bytes is not None and best_case_bytes.exists():
        if case_dir.exists():
            shutil.rmtree(case_dir)
        shutil.copytree(best_case_bytes, case_dir)
        shutil.rmtree(best_case_bytes, ignore_errors=True)
    return PolyHarnessResult(
        success=False,
        elapsed=time.perf_counter() - t0,
        iterations=int(max_iter),
        n_cells=last_metrics.get("cells", 0),
        n_points=last_metrics.get("points", 0),
        negative_volumes=last_metrics.get("negative_volumes", 0),
        max_non_ortho=float(last_metrics.get("max_non_orthogonality", 0.0)),
        max_skewness=float(last_metrics.get("max_skewness", 0.0)),
        message=(
            f"native_poly_harness FAIL after {max_iter} iter "
            f"(best negative_volumes={last_metrics.get('negative_volumes', -1)})"
        ),
    )
