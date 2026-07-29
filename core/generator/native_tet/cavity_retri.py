"""Q2 — Cavity re-triangulation with surface-aligned diagonal selection.

기존 Bowyer-Watson 은 cavity boundary face 들을 새 점과 연결해 fan tet 을
만든다. 그러나 missing surface edge 가 cavity 의 두 대각선 중 어느 쪽에
있는지를 고려하지 않아 cube 같은 형상에서 surface 대각선을 못 살린다.

본 모듈은 다른 접근을 취한다: 두 tet (A,B,C,D) / (A,B,C,E) 가 face (A,B,C)
를 공유할 때, missing edge (D, E) 가 surface 인 경우 — 이건 정확히 2-3 flip
으로 회복 가능. 더 일반화해서 "edge (u, v) 가 missing 이고, u 와 v 사이를
잇는 4개 tet 패턴" (ring of 3 around edge) 도 검사해 회복.

전략
    1) 각 missing edge (u, v) 에 대해, u 의 1-ring tet 들 중 v 와 face 공유
       가능한 짝을 모두 찾는다.
    2) 짝마다 가상 2-3 flip 시뮬레이션: face (a,b,c) 를 (u-v) 로 교체.
    3) 모든 새 tet 의 부피 양수 + min quality > threshold 면 적용.
    4) 한 번에 non-conflicting 짝만 batch 적용.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass
class CavityRetriResult:
    n_attempted: int
    n_recovered: int
    n_skipped_quality: int
    n_skipped_no_neighbor: int


def _tet_signed_vol6(a, b, c, d) -> float:
    return float(np.dot(b - a, np.cross(c - a, d - a)))


def _tet_quality(a, b, c, d) -> float:
    e = [
        np.linalg.norm(b - a), np.linalg.norm(c - a), np.linalg.norm(d - a),
        np.linalg.norm(c - b), np.linalg.norm(d - b), np.linalg.norm(d - c),
    ]
    emax = max(e)
    if emax < 1e-20:
        return 0.0
    vol = abs(_tet_signed_vol6(a, b, c, d)) / 6.0
    return 8.48 * vol / (emax ** 3)


def cavity_retri_for_missing_edges(
    pts: np.ndarray,
    tets: np.ndarray,
    missing_edges: list[tuple[int, int]],
    *,
    min_quality: float = 0.0,
    max_attempts: int = 1000,
    protected_faces: Sequence[Sequence[int]] | None = None,
) -> tuple[np.ndarray, CavityRetriResult]:
    """missing edge 들을 대각선 선택 기반 2-3 flip 으로 회복.

    각 missing edge (u, v) 에 대해:
        - u 와 v 가 모두 한 face 를 공유하는 두 tet 페어 (a,b,c,u) / (a,b,c,v)
          를 찾는다.
        - 새 3 tet (a,b,u,v), (b,c,u,v), (c,a,u,v) 가 모두 valid 면 교체.

    ``protected_faces`` guards only source faces that are direct immediately
    before a candidate 2-to-3 operation. It never treats a raw-key change as
    preserved and does not move points or insert Steiner vertices.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64).copy()
    if tets.size == 0 or not missing_edges:
        return tets, CavityRetriResult(0, 0, 0, 0)

    n_attempt = 0
    n_rec = 0
    n_skip_q = 0
    n_skip_n = 0

    # alive flag.
    alive = np.ones(tets.shape[0], dtype=bool)

    # vertex → tet index.
    # C-PERF-31 / beta2482 — vectorize via flat sort + bincount-offset slicing.
    n = pts.shape[0]
    if tets.shape[0] == 0:
        v2t: list[list[int]] = [[] for _ in range(n)]
    else:
        flat_v_v2t = tets.reshape(-1).astype(np.int64)
        flat_t_v2t = np.repeat(np.arange(tets.shape[0], dtype=np.int64), 4)
        order_v2t = np.argsort(flat_v_v2t, kind="stable")
        sorted_v_v2t = flat_v_v2t[order_v2t]
        sorted_t_v2t = flat_t_v2t[order_v2t]
        counts_v2t = np.bincount(sorted_v_v2t, minlength=n)
        offs_v2t = np.concatenate(([0], np.cumsum(counts_v2t).astype(np.int64)))
        v2t = [
            sorted_t_v2t[offs_v2t[i]:offs_v2t[i + 1]].tolist()
            for i in range(n)
        ]

    new_tets_list: list[list[int]] = []

    for (u, v) in missing_edges:
        if n_attempt >= max_attempts:
            break
        n_attempt += 1

        u_inc = [t for t in v2t[u] if alive[t]]
        v_inc = [t for t in v2t[v] if alive[t]]
        if not u_inc or not v_inc:
            n_skip_n += 1
            continue

        # u 가 들어 있는 tet 의 face (u 제외 3 개) 가 v 가 들어 있는 다른 tet 의
        # face (v 제외 3 개) 와 동일한지 검사.
        u_faces: dict[tuple[int, int, int], int] = {}
        for ti in u_inc:
            verts = tets[ti].tolist()
            face = tuple(sorted(int(x) for x in verts if int(x) != u))
            if len(face) == 3:
                u_faces[face] = ti

        chosen_pair: tuple[int, int, tuple[int, int, int]] | None = None
        for ti in v_inc:
            verts = tets[ti].tolist()
            face = tuple(sorted(int(x) for x in verts if int(x) != v))
            if len(face) != 3:
                continue
            if face in u_faces:
                tu = u_faces[face]
                if tu != ti:
                    chosen_pair = (tu, ti, face)
                    break

        if chosen_pair is None:
            n_skip_n += 1
            continue
        tu, tv, (a, b, c) = chosen_pair

        # 새 3 tet 후보 — 음수 부피면 face vertex swap 으로 양수화.
        raw_combos = [(a, b, u, v), (b, c, u, v), (c, a, u, v)]
        new_combos: list[tuple[int, int, int, int]] = []
        ok = True
        q_min = 1.0
        for nt in raw_combos:
            ia, ib, ic, id_ = nt
            if len({ia, ib, ic, id_}) != 4:
                ok = False; break
            vol = _tet_signed_vol6(pts[ia], pts[ib], pts[ic], pts[id_])
            if abs(vol) < 1e-18:
                ok = False; break
            if vol < 0:
                # swap ib, ic → 양수 부피.
                ia, ib, ic, id_ = ia, ic, ib, id_
            new_combos.append((ia, ib, ic, id_))
            q = _tet_quality(pts[ia], pts[ib], pts[ic], pts[id_])
            if q < q_min:
                q_min = q
        if not ok or q_min < float(min_quality):
            n_skip_q += 1
            continue

        if protected_faces:
            from core.generator.native_tet.duwang_constraint_protection_l0 import (
                audit_direct_constraint_face_protection_l0,
            )

            prior_new = (
                np.asarray(new_tets_list, dtype=np.int64)
                if new_tets_list
                else np.empty((0, 4), dtype=np.int64)
            )
            before_candidate = (
                np.vstack([tets[alive], prior_new]) if prior_new.size else tets[alive]
            )
            candidate_alive = alive.copy()
            candidate_alive[tu] = False
            candidate_alive[tv] = False
            candidate = np.vstack([
                tets[candidate_alive],
                prior_new,
                np.asarray(new_combos, dtype=np.int64),
            ])
            before_face_keys = {
                tuple(sorted(int(tet[index]) for index in range(4) if index != omitted))
                for tet in before_candidate
                for omitted in range(4)
            }
            direct_faces = tuple(
                face
                for face in protected_faces
                if tuple(sorted(int(vertex) for vertex in face)) in before_face_keys
            )
            if direct_faces and not audit_direct_constraint_face_protection_l0(
                before_candidate.tolist(), candidate.tolist(), direct_faces
            ).accepted:
                n_skip_q += 1
                continue

        # 적용: 기존 tu, tv kill + 새 3 tet append.
        alive[tu] = False
        alive[tv] = False
        for nt in new_combos:
            new_tets_list.append(list(nt))
            new_idx = len(new_tets_list) + tets.shape[0] - 1
            for vi in nt:
                v2t[int(vi)].append(new_idx - tets.shape[0] + tets.shape[0])
            # 위 indexing 은 단순화 — 새 tet 은 다음 missing edge 처리에 사용
            # 안 해도 무방 (한 missing edge 당 한 번만 작업).
        n_rec += 1

    keep = tets[alive]
    out = np.vstack([keep, np.asarray(new_tets_list, dtype=np.int64)]) \
        if new_tets_list else keep
    return out, CavityRetriResult(
        n_attempted=int(n_attempt),
        n_recovered=int(n_rec),
        n_skipped_quality=int(n_skip_q),
        n_skipped_no_neighbor=int(n_skip_n),
    )
