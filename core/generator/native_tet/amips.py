"""P2 — AMIPS (Advanced MIPS) energy-based vertex relocation.

레퍼런스
    - Fu, Liu, Guo 2015, "Computing Locally Injective Mappings by Advanced
      MIPS".
    - fTetWild (Hu et al. 2020) §3.3 — sliver 제거 smoothing 의 핵심.

본 모듈은 원본 C++ 를 복제하지 않는 독립 Python 재구현이다. 기본 흐름:

    E_amips(T) = exp(α · D(T))
    D(T)       = tr(Jᵀ J) / det(J)^{2/3}

여기서 J 는 tet T 를 ideal (regular) tet 으로 매핑하는 Jacobian. regular
tet 에서 D=3, sliver 에서 D→∞. α 는 stiffness (fTetWild 기본 1.0).

vertex v 의 relocation: v 의 1-ring tet 들의 energy 합 → numerical gradient
→ backtracking line-search.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# regular tet (edge length √2) 의 world → reference Jacobian 역행렬.
# reference tet: v0=(0,0,0), v1=(1,0,0), v2=(0.5, √3/2, 0),
#                v3=(0.5, √3/6, √(2/3)).
_REF = np.array([
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [0.5, np.sqrt(3.0) / 2.0, 0.0],
    [0.5, np.sqrt(3.0) / 6.0, np.sqrt(2.0 / 3.0)],
], dtype=np.float64)

_REF_MAT = np.stack(
    [_REF[1] - _REF[0], _REF[2] - _REF[0], _REF[3] - _REF[0]], axis=1,
)
_REF_INV = np.linalg.inv(_REF_MAT)


@dataclass
class AMIPSResult:
    n_iter: int
    n_moved: int
    max_disp: float
    energy_before: float
    energy_after: float


def _tet_amips_energy(v0, v1, v2, v3, alpha: float = 1.0) -> np.ndarray:
    """batch AMIPS energy per tet. v0..v3: (T, 3)."""
    J = np.stack([v1 - v0, v2 - v0, v3 - v0], axis=2)   # (T, 3, 3) world.
    # world → ref: F = J · _REF_INV. 등방 스케일 무시 위해 J 를 그대로 사용.
    F = J @ _REF_INV                                     # (T, 3, 3)
    tr = np.einsum("...ij,...ij->...", F, F)
    det = np.linalg.det(F)
    # 음수/0 det 는 inverted — 큰 에너지.
    safe = det > 1e-30
    d = np.full(det.shape, 1e30, dtype=np.float64)
    d[safe] = tr[safe] / np.power(det[safe], 2.0 / 3.0)
    # overflow 방지 — 큰 d 는 clip (sliver 는 단조 증가만 유지하면 충분).
    d_clip = np.minimum(d, 50.0 / max(float(alpha), 1e-30))
    return np.exp(float(alpha) * d_clip) - np.exp(float(alpha) * 3.0)


def _one_ring_energy(
    pts: np.ndarray, tets_inc: np.ndarray, alpha: float,
) -> float:
    v = pts[tets_inc]
    e = _tet_amips_energy(v[:, 0], v[:, 1], v[:, 2], v[:, 3], alpha)
    return float(e.sum())


def _amips_local_energy(
    pts: np.ndarray, tet_rows: np.ndarray, alpha: float,
) -> tuple[float, bool]:
    """1-ring tet 의 합 energy + 모든 부피 양수 여부.

    tet_rows: (k, 4) — vertex 의 1-ring tet vertex index.
    """
    if tet_rows.shape[0] == 0:
        return 0.0, True
    v = pts[tet_rows]
    vol6 = np.einsum(
        "ij,ij->i",
        v[:, 1] - v[:, 0],
        np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
    )
    if (vol6 <= 1e-20).any():
        return float("inf"), False
    e = _tet_amips_energy(v[:, 0], v[:, 1], v[:, 2], v[:, 3], alpha)
    return float(e.sum()), True


def _amips_grad_analytic(
    pts: np.ndarray, tet_rows: np.ndarray, vi: int, alpha: float,
) -> np.ndarray:
    """Q5 — analytic ∂E/∂v_i for vertex vi over its 1-ring tets.

    수식
        E(F)   = exp(α D) - exp(3α),  D = tr(FᵀF) / det(F)^(2/3)
        F      = J · M⁻¹,  J = [v1-v0, v2-v0, v3-v0]^T (column 별)
        ∂E/∂v_i = exp(α D) · α · ∂D/∂v_i
        ∂D/∂F  = 2 F / det(F)^(2/3)
                  - (2/3) · tr(FᵀF) / det(F)^(5/3) · cof(F)
        ∂F/∂v_i = (∂J/∂v_i) · M⁻¹
                = chain rule: J 는 v_i 가 v0 (k=0) 이면 모든 column 에 -I,
                  v_i 가 v_k (k=1..3) 이면 column k-1 에 +I.
    1-ring 의 모든 tet 에 대해 v_i 의 위치가 어떤 indexing 인지 (k=0..3) 따라
    적절한 부호의 contribution 합.
    """
    if tet_rows.shape[0] == 0:
        return np.zeros(3, dtype=np.float64)
    grad = np.zeros(3, dtype=np.float64)
    for row in tet_rows:
        v0, v1, v2, v3 = (int(x) for x in row)
        P0 = pts[v0]; P1 = pts[v1]; P2 = pts[v2]; P3 = pts[v3]
        J = np.stack([P1 - P0, P2 - P0, P3 - P0], axis=1)   # (3, 3) columns
        F = J @ _REF_INV
        det_F = float(np.linalg.det(F))
        if det_F <= 1e-30:
            continue
        tr_FtF = float(np.einsum("ij,ij->", F, F))
        D = tr_FtF / (det_F ** (2.0 / 3.0))
        # cofactor(F) = inv(F).T * det(F).
        try:
            inv_F = np.linalg.inv(F)
        except Exception:
            continue
        cof_F = inv_F.T * det_F
        dD_dF = (2.0 / (det_F ** (2.0 / 3.0))) * F \
            - (2.0 / 3.0) * tr_FtF / (det_F ** (5.0 / 3.0)) * cof_F
        # ∂F/∂v_i: index of vi in row.
        idx = -1
        for k, vid in enumerate((v0, v1, v2, v3)):
            if vid == vi:
                idx = k
                break
        if idx < 0:
            continue
        # ∂J/∂v_i: 3x3 행렬, column 별 contribution.
        # k=0 (v0): J 의 모든 column 에 -I → ∂F = -sum(_REF_INV columns) = -_REF_INV row sum.
        # k>=1: column (k-1) 에 +I → ∂F = _REF_INV row k-1 의 외적 형태.
        # 더 간단: dJ_dvi 는 (3,3) 텐서로 한 column 만 ±I.
        if idx == 0:
            # 각 column j 에 대해 dJ[:, j] = -e_d (axis d). 즉 dJ_d/dvi_d = -1 모든 col.
            # → ∂F = -_REF_INV 의 모든 column 합 (row 별).
            # dF[a, b] = - sum_j _REF_INV[j, b]  if a == d (axis of v_i) else 0.
            # axis-별 grad: g[d] = sum_{a,b} dD_dF[a,b] * dF[a,b]_d = -sum_b dD_dF[d, b] * sum_j _REF_INV[j, b].
            row_sum = _REF_INV.sum(axis=0)        # (3,)
            for d in range(3):
                grad[d] += float(np.exp(min(alpha * D, 50.0)) * alpha *
                                 (-np.dot(dD_dF[d], row_sum)))
        else:
            j = idx - 1                            # J 의 column index.
            for d in range(3):
                grad[d] += float(np.exp(min(alpha * D, 50.0)) * alpha *
                                 np.dot(dD_dF[d], _REF_INV[j]))
    return grad


def smooth_amips_analytic(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray | None = None,
    n_iter: int = 3,
    alpha: float = 1.0,
    step_init: float = 0.1,
    step_min: float = 1e-6,
) -> tuple[AMIPSResult, np.ndarray]:
    """Q5 — analytic gradient + line-search.

    finite-diff 6-eval 대신 closed-form gradient. 1-ring 한정.
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64)
    n = pts.shape[0]
    if tets.size == 0:
        return AMIPSResult(0, 0, 0.0, 0.0, 0.0), pts

    locked_mask = np.zeros(n, dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    # CSR 1-ring.
    counts = np.zeros(n, dtype=np.int64)
    for k in range(4):
        np.add.at(counts, tets[:, k], 1)
    offsets = np.concatenate([[0], np.cumsum(counts)])
    flat = np.empty(int(counts.sum()), dtype=np.int64)
    cursor = offsets[:-1].copy()
    for ti in range(tets.shape[0]):
        for k in range(4):
            v = int(tets[ti, k])
            flat[cursor[v]] = ti
            cursor[v] += 1

    def _energy_local(vi):
        inc = flat[offsets[vi]:offsets[vi + 1]]
        if inc.size == 0:
            return 0.0, True
        return _amips_local_energy(pts, tets[inc], alpha)

    v_all = pts[tets]
    e_all = _tet_amips_energy(v_all[:, 0], v_all[:, 1], v_all[:, 2], v_all[:, 3], alpha)
    e_before = float(e_all[np.isfinite(e_all)].sum())

    max_disp = 0.0
    moved = 0
    for _ in range(int(n_iter)):
        for vi in range(n):
            if locked_mask[vi] or counts[vi] == 0:
                continue
            e0, ok0 = _energy_local(vi)
            if not ok0 or not np.isfinite(e0):
                continue
            inc = flat[offsets[vi]:offsets[vi + 1]]
            grad = _amips_grad_analytic(pts, tets[inc], vi, alpha)
            gnorm = float(np.linalg.norm(grad))
            if gnorm < 1e-20:
                continue
            direction = -grad / gnorm
            orig = pts[vi].copy()
            step = float(step_init)
            improved = False
            while step >= step_min:
                pts[vi] = orig + step * direction
                e1, ok1 = _energy_local(vi)
                if ok1 and np.isfinite(e1) and e1 < e0 - 1e-20:
                    improved = True
                    disp = float(np.linalg.norm(step * direction))
                    if disp > max_disp:
                        max_disp = disp
                    moved += 1
                    break
                step *= 0.5
            if not improved:
                pts[vi] = orig

    v_all2 = pts[tets]
    e_all2 = _tet_amips_energy(v_all2[:, 0], v_all2[:, 1], v_all2[:, 2], v_all2[:, 3], alpha)
    e_after = float(e_all2[np.isfinite(e_all2)].sum())

    return AMIPSResult(
        n_iter=int(n_iter), n_moved=int(moved),
        max_disp=float(max_disp),
        energy_before=float(e_before),
        energy_after=float(e_after),
    ), pts


def smooth_amips(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray | None = None,
    n_iter: int = 3,
    alpha: float = 1.0,
    step_init: float = 0.1,
    step_min: float = 1e-6,
    grad_eps: float = 1e-5,
) -> tuple[AMIPSResult, np.ndarray]:
    """AMIPS energy 를 per-vertex line-search 로 감소시키는 relocation.

    각 non-locked vertex:
        1) 1-ring tet 의 energy E_0 계산.
        2) 3 축 ± grad_eps finite-diff gradient.
        3) step = step_init, backtracking line-search:
             pt_new = pt - step · grad
             새 energy E_1 이 E_0 보다 작고 1-ring 모든 tet 의 det > 0 이면
             accept. 아니면 step /= 2.
        4) step < step_min 이면 skip.
    """
    """Q1 (beta1390) — 1-ring restricted + vectorized 3-axis finite-diff.

    핵심 가속:
      - vertex i 의 1-ring tet 만 numpy slice 로 가져와 evaluation.
      - gradient 의 3축 forward/backward 6 evaluation 을 1-ring tet 에 한정.
      - global energy 합산은 시작/종료 시 1번씩만 (중간엔 local 만).
      - line-search 가 fail 하면 1-ring 에 손대지 않고 즉시 skip.

    finite-diff 자체 유지 (analytic gradient 는 별도 라운드).
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64)
    n = pts.shape[0]
    if tets.size == 0:
        return AMIPSResult(0, 0, 0.0, 0.0, 0.0), pts

    locked_mask = np.zeros(n, dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    # 1-ring tet index — np.add.at 으로 호환 빌드.
    counts = np.zeros(n, dtype=np.int64)
    for k in range(4):
        np.add.at(counts, tets[:, k], 1)
    offsets = np.concatenate([[0], np.cumsum(counts)])
    flat = np.empty(int(counts.sum()), dtype=np.int64)
    cursor = offsets[:-1].copy()
    for ti in range(tets.shape[0]):
        for k in range(4):
            v = int(tets[ti, k])
            flat[cursor[v]] = ti
            cursor[v] += 1

    def _incident_tets(vi: int) -> np.ndarray:
        return flat[offsets[vi]:offsets[vi + 1]]

    def _energy_local(vi: int) -> tuple[float, bool]:
        inc = _incident_tets(vi)
        if inc.size == 0:
            return 0.0, True
        return _amips_local_energy(pts, tets[inc], alpha)

    # 전역 energy (시작/종료 1회).
    v_all = pts[tets]
    e_all_before = _tet_amips_energy(
        v_all[:, 0], v_all[:, 1], v_all[:, 2], v_all[:, 3], alpha,
    )
    e_before = float(e_all_before[np.isfinite(e_all_before)].sum())

    max_disp = 0.0
    moved = 0
    for _ in range(int(n_iter)):
        for vi in range(n):
            if locked_mask[vi] or counts[vi] == 0:
                continue
            e0, ok0 = _energy_local(vi)
            if not ok0 or not np.isfinite(e0):
                continue

            orig = pts[vi].copy()
            grad = np.zeros(3, dtype=np.float64)
            for ax in range(3):
                pts[vi, ax] = orig[ax] + grad_eps
                eplus, _ = _energy_local(vi)
                pts[vi, ax] = orig[ax] - grad_eps
                eminus, _ = _energy_local(vi)
                pts[vi, ax] = orig[ax]
                if not (np.isfinite(eplus) and np.isfinite(eminus)):
                    grad = np.zeros(3, dtype=np.float64)
                    break
                grad[ax] = (eplus - eminus) / (2.0 * grad_eps)

            gnorm = float(np.linalg.norm(grad))
            if gnorm < 1e-20:
                continue
            direction = -grad / gnorm

            step = float(step_init)
            improved = False
            while step >= step_min:
                pts[vi] = orig + step * direction
                e1, ok1 = _energy_local(vi)
                if ok1 and np.isfinite(e1) and e1 < e0 - 1e-20:
                    improved = True
                    disp = float(np.linalg.norm(step * direction))
                    if disp > max_disp:
                        max_disp = disp
                    moved += 1
                    break
                step *= 0.5
            if not improved:
                pts[vi] = orig

    v_all2 = pts[tets]
    e_all_after = _tet_amips_energy(
        v_all2[:, 0], v_all2[:, 1], v_all2[:, 2], v_all2[:, 3], alpha,
    )
    e_after = float(e_all_after[np.isfinite(e_all_after)].sum())

    return AMIPSResult(
        n_iter=int(n_iter),
        n_moved=int(moved),
        max_disp=float(max_disp),
        energy_before=float(e_before),
        energy_after=float(e_after),
    ), pts
