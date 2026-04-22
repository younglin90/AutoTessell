"""NativeTetHarness — Generator ↔ Evaluator 반복으로 tet mesh 품질 수렴.

harness 패턴의 native_tet 전용 변형:
  1. Generator: generate_native_tet (scipy Delaunay + envelope + sliver filter).
  2. Evaluator: NativeMeshChecker + Hausdorff (가용 시) + non-ortho / skewness.
  3. FAIL 시 파라미터 조정 (seed_density↑ → surface 보존도↑, sliver q_thresh↑ →
     non-ortho 개선) 후 재시도.
  4. 최대 max_iter 반복, 통과 또는 iter 초과 시 종료. 최선 결과 (negative_volumes
     최소 우선, 그다음 non_ortho 최소) 를 case_dir 로 복사.

제약:
    - native_tet 의 q_thresh 는 공용 상수라 harness 에서 변경 불가. 대신
      seed_density 만 조정.
    - Hausdorff 측정은 core/evaluator/fidelity 경유 (예외 시 skip).
"""
from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.generator.native_tet.mesher import (
    NativeTetResult,
    generate_native_tet,
)
from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class TetHarnessResult:
    success: bool
    elapsed: float
    iterations: int
    n_cells: int = 0
    n_points: int = 0
    negative_volumes: int = 0
    max_non_ortho: float = 0.0
    max_skewness: float = 0.0
    message: str = ""


def _evaluate_tet_mesh(case_dir: Path) -> tuple[bool, dict]:
    """NativeMeshChecker 로 negative_volumes / non_ortho 확인."""
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
    # PASS = negative_volumes == 0 + non_ortho < 80
    passed = (
        metrics["negative_volumes"] == 0
        and metrics["max_non_orthogonality"] < 80.0
        and metrics["cells"] > 0
    )
    return passed, metrics


def run_native_tet_harness(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 12,
    max_iter: int = 2,
    max_cells: int = 50000,
) -> TetHarnessResult:
    """native_tet Generator ↔ Evaluator 반복.

    FAIL 시 seed_density 를 1.3× 늘려 mesh 를 더 조밀하게. 이는 surface 근처
    tet 이 많아져 Hausdorff 개선 + boundary sliver 감소 → non-ortho 도 개선.

    Safety cap:
      - target_edge_length < bbox_diag/40 이면 clamp (tet 폭증 방지).
      - tet 생성 결과 cells > max_cells 이면 target_edge 1.6×, seed 0.7× 재시도.
    """
    t0 = time.perf_counter()

    # target_edge_length 하한 clamp
    if target_edge_length is not None:
        bmin = np.asarray(vertices).min(axis=0)
        bmax = np.asarray(vertices).max(axis=0)
        diag = float(np.linalg.norm(bmax - bmin))
        floor = diag / 40.0
        if target_edge_length < floor:
            log.info(
                "native_tet_harness_target_edge_clamp",
                requested=target_edge_length, clamped_to=floor,
            )
            target_edge_length = floor

    last_metrics: dict = {}
    best_case: Path | None = None
    best_non_ortho = float("inf")
    current_seed = int(seed_density)

    for it in range(1, int(max_iter) + 1):
        log.info(
            "native_tet_harness_iter",
            iteration=it, seed_density=current_seed,
        )
        tmp = Path(tempfile.mkdtemp(prefix=f"nth_{it}_"))
        try:
            res: NativeTetResult = generate_native_tet(
                vertices, faces, tmp,
                target_edge_length=target_edge_length,
                seed_density=current_seed,
            )
            if not res.success:
                log.warning(
                    "native_tet_harness_gen_fail",
                    iteration=it, message=res.message,
                )
                current_seed = int(current_seed * 1.3)
                shutil.rmtree(tmp, ignore_errors=True)
                continue

            # cell 수 cap
            if res.n_cells > max_cells and it < max_iter:
                log.warning(
                    "native_tet_harness_too_many_cells",
                    n_cells=res.n_cells, cap=max_cells, iteration=it,
                )
                if target_edge_length is not None:
                    target_edge_length = float(target_edge_length) * 1.6
                current_seed = max(int(current_seed * 0.7), 4)
                shutil.rmtree(tmp, ignore_errors=True)
                continue

            passed, metrics = _evaluate_tet_mesh(tmp)
            last_metrics = metrics
            log.info(
                "native_tet_harness_eval",
                iteration=it, passed=passed, **metrics,
            )

            # best 후보 추적 (non_ortho 최소 우선)
            cur_non_ortho = metrics.get("max_non_orthogonality", 999.0)
            if metrics.get("negative_volumes", 1) == 0 and cur_non_ortho < best_non_ortho:
                best_non_ortho = cur_non_ortho
                if best_case is not None and best_case.exists():
                    shutil.rmtree(best_case, ignore_errors=True)
                best_case = tmp
            else:
                shutil.rmtree(tmp, ignore_errors=True)

            if passed:
                if case_dir.exists():
                    shutil.rmtree(case_dir)
                shutil.copytree(best_case if best_case else tmp, case_dir)
                return TetHarnessResult(
                    success=True,
                    elapsed=time.perf_counter() - t0,
                    iterations=it,
                    n_cells=metrics["cells"], n_points=metrics["points"],
                    negative_volumes=metrics["negative_volumes"],
                    max_non_ortho=metrics["max_non_orthogonality"],
                    max_skewness=metrics["max_skewness"],
                    message=(
                        f"native_tet_harness PASS iter={it}, cells={metrics['cells']}, "
                        f"non_ortho={metrics['max_non_orthogonality']:.1f}°"
                    ),
                )
            # 실패 → seed density 늘려 재시도 (surface 보존 개선)
            current_seed = int(current_seed * 1.3)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            current_seed = int(current_seed * 1.3)

    # 모든 iter 실패 — best 결과 복사
    if best_case is not None and best_case.exists():
        if case_dir.exists():
            shutil.rmtree(case_dir)
        shutil.copytree(best_case, case_dir)
        shutil.rmtree(best_case, ignore_errors=True)
    return TetHarnessResult(
        success=False,
        elapsed=time.perf_counter() - t0,
        iterations=int(max_iter),
        n_cells=last_metrics.get("cells", 0),
        n_points=last_metrics.get("points", 0),
        negative_volumes=last_metrics.get("negative_volumes", 0),
        max_non_ortho=float(last_metrics.get("max_non_orthogonality", 0.0)),
        max_skewness=float(last_metrics.get("max_skewness", 0.0)),
        message=(
            f"native_tet_harness best_effort after {max_iter} iter "
            f"(best non_ortho={best_non_ortho:.1f}°)"
        ),
    )
