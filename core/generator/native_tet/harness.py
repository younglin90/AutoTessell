"""NativeTetHarness — Generator ↔ Evaluator 반복으로 tet mesh 품질 수렴.

harness 패턴의 native_tet 전용 변형:
  1. Generator: generate_native_tet (scipy Delaunay + envelope + sliver filter).
  2. Evaluator: NativeMeshChecker + Hausdorff (가용 시) + non-ortho / skewness.
  3. FAIL 시 파라미터 조정 (seed_density↑ → surface 보존도↑, sliver q_thresh↑ →
     non-ortho 개선) 후 재시도.
  4. 최대 max_iter 반복, 통과 또는 iter 초과 시 종료. 최선 결과 (negative_volumes
     최소 우선, 그다음 non_ortho 최소) 를 case_dir 로 복사.

제약:
    - Hausdorff 측정은 core/evaluator/fidelity 경유 (예외 시 skip).

beta62: q_thresh 를 kwarg 로 노출. 생성 실패 시 adaptive 로 threshold 를 0.8×
완화 → 복잡 형상에서도 수렴하도록.
"""
from __future__ import annotations

import math
import os
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
    # beta840: harness 가 들고 있는 최종 quality snapshot.
    quality: "Any" = None


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
    # PASS = negative_volumes == 0 + non_ortho < 89 (tet mesh 구조적 특성 허용)
    # tet mesh 는 boundary sliver cell 로 인해 max_non_ortho 가 88-90° 에 가깝게
    # 나오는 것이 구조적 특성이다. 이전 기준(< 80°)은 너무 엄격해 불필요한
    # harness 재시도를 유발하고 오히려 품질을 악화시켰다.
    # 실제 PASS/FAIL 판정은 evaluator (EvaluationReporter) 에서 tier-specific
    # 임계로 처리한다.
    passed = (
        metrics["negative_volumes"] == 0
        and metrics["max_non_orthogonality"] < 89.0
        and metrics["cells"] > 0
    )
    return passed, metrics


def _rebudget_band(
    target_cells: int | None, max_cells: int
) -> tuple[int, int, int, bool]:
    """(target_low, target_high, reference, two_sided) 셀 수 목표 band.

    - ``target_cells`` 명시 → 양방향 band ``[lo·N, hi·N]`` (초과 시 성기게,
      미달 시 촘촘하게).  사용자가 "N 개쯤" 을 요구한 계약.
    - ``target_cells`` 없음 → ``max_cells`` 를 **단방향 cap** 으로만 사용
      (``[0, cap]``).  ``max_cells`` 는 signature default 가 50000 이라
      "사용자가 50000 을 원했다" 와 구분할 수 없으므로, 절대 셀 수를 cap 쪽으로
      **늘리지 않는다**.  기존 cap 의미 그대로.
    """
    if target_cells is not None and target_cells > 0:
        lo_f = float(os.environ.get("AUTO_TESSELL_NATIVE_TET_REBUDGET_LO", "0.85"))
        hi_f = float(os.environ.get("AUTO_TESSELL_NATIVE_TET_REBUDGET_HI", "1.15"))
        t_low = max(1, int(round(float(target_cells) * lo_f)))
        t_high = max(t_low, int(round(float(target_cells) * hi_f)))
        return t_low, t_high, int(target_cells), True
    return 0, max(1, int(max_cells)), max(1, int(max_cells)), False


def _generate_with_cell_rebudget(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    iteration: int,
    target_edge_length: float | None,
    seed_density: int,
    sliver_quality_threshold: float,
    max_input_vertices: int,
    max_cells: int,
    gen_kwargs: dict,
) -> tuple[NativeTetResult, Path, float | None]:
    """측정 기반 closed-loop 로 목표 셀 수에 수렴시키며 tet mesh 생성.

    ``tier_wildmesh.py`` 의 ``wildmesh_cell_rebudget`` 루프와 동일한 구조:
    실제 생성된 셀 수를 측정 → ``factor = (n_cells / target)**(1/3)`` (n ∝ 1/e³
    역산) → per-step clamp 로 damping → band 안에 들 때까지 재생성.

    한 번의 blunt 보정 (기존 ``edge × 1.6``) 으로는 수렴하지 않는다: native_tet 의
    실측 n(edge) 지수는 3 이 아니라 2.8-3.9 사이에서 변동하므로 (unit cube 실측)
    1/3 역산이 매번 over/under 한다.  그래서 damped 다단 pass 가 필요하다.

    이 루프는 harness 의 ``max_iter`` (Gen↔Eval **품질** 반복) 예산을 쓰지 않고
    **자체 예산** (``AUTO_TESSELL_NATIVE_TET_CELL_REBUDGET_PASSES``) 을 갖는다.
    draft 의 ``max_iter=1`` 에서도 셀 수 보정이 동작해야 하기 때문이다.

    Returns:
        (result, tmp_dir, 최종 target_edge_length).  tmp_dir 소유권은 caller 로
        이전 — best pass 의 mesh 만 남기고 나머지는 정리한다.
    """
    _tc_raw = gen_kwargs.get("target_cells")
    try:
        target_cells = int(_tc_raw) if _tc_raw else None
    except (TypeError, ValueError):
        target_cells = None

    t_low, t_high, ref, two_sided = _rebudget_band(target_cells, max_cells)
    passes = max(
        0, int(os.environ.get("AUTO_TESSELL_NATIVE_TET_CELL_REBUDGET_PASSES", "6"))
    )
    # target_edge_length 가 None 이면 mesher 가 내부 heuristic 으로 edge 를
    # 정하므로 보정 base 를 알 수 없다 → 루프 비활성 (기존 cap 경로 유지).
    active = (
        os.environ.get("AUTO_TESSELL_NATIVE_TET_CELL_REBUDGET", "1") != "0"
        and target_edge_length is not None
        and passes > 0
    )

    v = np.asarray(vertices, dtype=float)
    diag = (
        float(np.linalg.norm(v.max(axis=0) - v.min(axis=0))) if v.size else 0.0
    )
    edge_min = diag / 200.0 if diag > 0 else 0.0
    edge_max = diag / 2.0 if diag > 0 else float("inf")

    edge = target_edge_length
    best: tuple[float, NativeTetResult, Path, float | None] | None = None
    # stall: best 가 개선되지 않은 연속 pass 수.  native_tet 의 n(edge) 는
    # 연속·단조가 아니다 — 성긴 영역에선 셀 수가 양자화되고 (unit cube: 50 →
    # 1444 로 점프), P4-C 발동 경계에서 불연속이다.  목표가 그 gap 안에 있으면
    # 루프는 두 값 사이를 진동만 하므로, 개선이 멈추면 조기 종료하고 지금까지의
    # best (목표에 가장 가까운 mesh) 를 쓴다.
    stall = 0
    stall_limit = max(
        1, int(os.environ.get("AUTO_TESSELL_NATIVE_TET_REBUDGET_STALL", "2"))
    )

    for p in range(passes + 1 if active else 1):
        tmp = Path(tempfile.mkdtemp(prefix=f"nth_{iteration}_{p}_"))
        res: NativeTetResult = generate_native_tet(
            vertices, faces, tmp,
            target_edge_length=edge,
            seed_density=int(seed_density),
            sliver_quality_threshold=float(sliver_quality_threshold),
            max_input_vertices=int(max_input_vertices),
            **gen_kwargs,
        )
        if not active:
            return res, tmp, edge
        if not res.success:
            # 보정 중 생성 실패 → 이전 pass 의 성공 mesh 가 있으면 그것을 살린다.
            # (그냥 실패를 반환하면 이미 확보한 mesh 를 버리고 harness 가 seed 를
            #  올려 재시도 → 더 나쁜 결과.)
            if best is not None:
                shutil.rmtree(tmp, ignore_errors=True)
                log.info(
                    "native_tet_cell_rebudget_gen_failed_keep_best",
                    iteration=iteration, pass_index=p,
                    best_n_cells=int(best[1].n_cells), target=ref,
                )
                return best[1], best[2], best[3]
            return res, tmp, edge

        n = int(res.n_cells)
        # best = 목표에 가장 가까운 pass (로그 비율 거리 — over/under 대칭).
        score = abs(math.log(max(n, 1) / max(ref, 1)))
        # 2026-07-18 — 축퇴 페널티 (cylinder 간헐 FAIL 의 공모 결함).
        # 셀-수 거리만으로 고르면 "크기만 맞는 축퇴 mesh" (min_q≈0, skew~1e15)
        # 가 band 밖의 grade-A mesh 를 밀어내고 채택된다 (실측: 2030-cell 축퇴가
        # 3048-cell P4-C mesh 를 이김 → 곡면벽 dev 0.359 로 테스트 FAIL).
        # min_q 가 사실상 0 인 pass 는 큰 페널티를 더해, 유효한 대안이 하나라도
        # 있으면 축퇴 mesh 가 best 로 뽑히지 않게 한다.  모든 pass 가 축퇴면
        # 종전처럼 가장 가까운 것이 반환된다 (best-effort 유지).
        _q = getattr(res, "quality", None)
        _min_q = float(getattr(_q, "min_q", 1.0)) if _q is not None else 1.0
        if _min_q < 1e-6:
            score += 10.0
        if best is None or score < best[0] - 1e-9:
            if best is not None:
                shutil.rmtree(best[2], ignore_errors=True)
            best = (score, res, tmp, edge)
            stall = 0
        else:
            shutil.rmtree(tmp, ignore_errors=True)
            stall += 1

        if t_low <= n <= t_high:
            break
        if p >= passes or edge is None:
            break
        if stall >= stall_limit:
            log.info(
                "native_tet_cell_rebudget_stalled",
                iteration=iteration, passes_used=p + 1,
                best_n_cells=int(best[1].n_cells), target=ref,
                target_low=t_low, target_high=t_high,
                reason="n(edge) is quantized/discontinuous near target",
            )
            break

        if n > t_high:
            _tgt = max(1.0, float(t_high) * 0.9)
            factor = (float(n) / _tgt) ** (1.0 / 3.0)
            factor = min(max(factor, 1.05), 2.0)
        elif two_sided and n < t_low:
            _tgt = max(1.0, float(t_low) * 1.1)
            factor = (float(max(n, 1)) / _tgt) ** (1.0 / 3.0)
            factor = max(min(factor, 0.95), 0.5)
        else:
            break

        new_edge = float(min(max(edge * factor, edge_min), edge_max))
        if abs(new_edge / max(edge, 1e-30) - 1.0) < 0.02:
            break
        log.info(
            "native_tet_cell_rebudget",
            iteration=iteration, pass_index=p + 1,
            n_cells=n, target=ref, target_low=t_low, target_high=t_high,
            two_sided=two_sided,
            edge_old=round(float(edge), 6), edge_new=round(new_edge, 6),
            factor=round(factor, 4),
        )
        edge = new_edge

    assert best is not None  # active + success 경로에서만 도달
    return best[1], best[2], best[3]


def run_native_tet_harness(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 12,
    max_iter: int = 2,
    max_cells: int = 50000,
    sliver_quality_threshold: float = 0.05,
    max_input_vertices: int = 100000,
    # beta310: quality=standard/fine 에서 전달되는 Phase B/C/adaptive kwargs.
    **kwargs,
) -> TetHarnessResult:
    """native_tet Generator ↔ Evaluator 반복.

    FAIL 시 seed_density 를 1.3× 늘리고 sliver_quality_threshold 를 0.8× 완화 →
    더 많은 tet 유지 → surface 보존 + non-ortho 개선. Hausdorff 도 같이 개선.

    Safety cap:
      - target_edge_length < bbox_diag/40 이면 clamp (tet 폭증 방지).
      - 셀 수는 ``_generate_with_cell_rebudget`` 의 measured-ratio closed loop 가
        맞춘다 (``target_cells`` 있으면 ±band 양방향, 없으면 ``max_cells`` 단방향
        cap).  target_edge_length=None 이면 seed 0.7× fallback.

    beta62: sliver_quality_threshold adaptive 완화.
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
    current_q_thresh = float(sliver_quality_threshold)
    # beta840: 가장 최근 성공한 iteration 의 quality snapshot 보존.
    latest_quality = None

    for it in range(1, int(max_iter) + 1):
        log.info(
            "native_tet_harness_iter",
            iteration=it, seed_density=current_seed,
            q_thresh=current_q_thresh,
        )
        tmp: Path | None = None
        try:
            res, tmp, target_edge_length = _generate_with_cell_rebudget(
                vertices, faces,
                iteration=it,
                target_edge_length=target_edge_length,
                seed_density=current_seed,
                sliver_quality_threshold=current_q_thresh,
                max_input_vertices=int(max_input_vertices),
                max_cells=int(max_cells),
                gen_kwargs=kwargs,
            )
            if res.success and getattr(res, "quality", None) is not None:
                latest_quality = res.quality
            if not res.success:
                log.warning(
                    "native_tet_harness_gen_fail",
                    iteration=it, message=res.message,
                )
                current_seed = int(current_seed * 1.3)
                # gen 실패 시 q_thresh 도 완화 — "inside tet 0" 메시지면 특히
                # sliver 필터가 너무 공격적인 경우 많다.
                current_q_thresh *= 0.8
                shutil.rmtree(tmp, ignore_errors=True)
                continue

            # cell 수 cap — target_edge_length 가 None 이라 _generate_with_cell_rebudget
            # 의 measured-ratio 보정이 동작하지 못한 경우의 fallback (seed 기반).
            # edge 가 주어진 경로에선 이미 rebudget 루프가 cap 을 처리했다.
            #
            # ``it < max_iter`` 는 의도적: 예산이 남아 있을 때만 mesh 를 버리고
            # 재시도한다.  마지막 iteration 에서 버리면 best_case=None 으로 루프를
            # 빠져나가 success=False / n_cells=0 (완전 실패) 이 된다 — overshoot
            # 보다 나쁘다.
            if (
                target_edge_length is None
                and res.n_cells > max_cells
                and it < max_iter
            ):
                log.warning(
                    "native_tet_harness_too_many_cells",
                    n_cells=res.n_cells, cap=max_cells, iteration=it,
                )
                current_seed = max(int(current_seed * 0.7), 4)
                shutil.rmtree(tmp, ignore_errors=True)
                continue

            passed, metrics = _evaluate_tet_mesh(tmp)
            last_metrics = metrics

            # beta900: CDT edge recovery ratio 도 harness log 에 기록.
            try:
                from core.generator.native_tet.cdt_check import (
                    check_edge_recovery,
                )

                if res.tets is not None and res.tets.shape[0] > 0:
                    cdt = check_edge_recovery(faces, res.tets)
                    if cdt.n_surface_edges > 0:
                        metrics["cdt_recovered"] = int(cdt.n_present_as_tet_edges)
                        metrics["cdt_total"] = int(cdt.n_surface_edges)
                        metrics["cdt_ratio"] = round(
                            cdt.n_present_as_tet_edges / cdt.n_surface_edges, 3
                        )
            except Exception:
                pass

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
                    quality=latest_quality,
                )
            # 실패 → seed density 늘려 재시도 (surface 보존 개선)
            current_seed = int(current_seed * 1.3)
        except Exception:
            if tmp is not None:
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
        quality=latest_quality,
    )
