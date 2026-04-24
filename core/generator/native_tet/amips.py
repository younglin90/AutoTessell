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
    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64)
    n = pts.shape[0]
    if tets.size == 0:
        return AMIPSResult(0, 0, 0.0, 0.0, 0.0), pts

    locked_mask = np.zeros(n, dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    # vertex → 1-ring tet index 리스트.
    v2t: list[list[int]] = [[] for _ in range(n)]
    for ti in range(tets.shape[0]):
        for k in range(4):
            v2t[int(tets[ti, k])].append(ti)

    def _energy_incident(vi: int) -> tuple[float, bool]:
        inc = v2t[vi]
        if not inc:
            return 0.0, True
        t = tets[inc]
        v = pts[t]
        # volume sign 체크 — 하나라도 <=0 이면 invalid.
        vol6 = np.einsum(
            "ij,ij->i",
            v[:, 1] - v[:, 0],
            np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
        )
        if (vol6 <= 1e-20).any():
            return float("inf"), False
        e = _tet_amips_energy(v[:, 0], v[:, 1], v[:, 2], v[:, 3], alpha)
        return float(e.sum()), True

    e_before = 0.0
    for vi in range(n):
        eb, _ = _energy_incident(vi)
        if np.isfinite(eb):
            e_before += eb

    max_disp = 0.0
    moved = 0
    for _ in range(int(n_iter)):
        for vi in range(n):
            if locked_mask[vi]:
                continue
            e0, ok0 = _energy_incident(vi)
            if not ok0 or not np.isfinite(e0):
                continue

            # finite-diff gradient.
            orig = pts[vi].copy()
            grad = np.zeros(3, dtype=np.float64)
            for ax in range(3):
                pts[vi, ax] = orig[ax] + grad_eps
                eplus, _ = _energy_incident(vi)
                pts[vi, ax] = orig[ax] - grad_eps
                eminus, _ = _energy_incident(vi)
                pts[vi, ax] = orig[ax]
                grad[ax] = (eplus - eminus) / (2.0 * grad_eps)

            gnorm = float(np.linalg.norm(grad))
            if gnorm < 1e-20:
                continue
            direction = -grad / gnorm

            step = float(step_init)
            improved = False
            while step >= step_min:
                pts[vi] = orig + step * direction
                e1, ok1 = _energy_incident(vi)
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

    e_after = 0.0
    for vi in range(n):
        ea, _ = _energy_incident(vi)
        if np.isfinite(ea):
            e_after += ea

    return AMIPSResult(
        n_iter=int(n_iter),
        n_moved=int(moved),
        max_disp=float(max_disp),
        energy_before=float(e_before),
        energy_after=float(e_after),
    ), pts
