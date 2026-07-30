"""Round 67 — Targeted edge flip for CDT recovery.

Missing surface edge (u, v) 가 존재할 때, u 와 v 를 동시에 포함하는 tet 쌍의
"잘못된 대각선" 을 뒤집어 (u, v) 를 edge 로 생성. standard 2-3 flip 과 달리
quality 가 아닌 "edge (u, v) 가 결과에 존재" 를 기준으로 선택.

레퍼런스
    - Shewchuk 1998, "Tetrahedral Mesh Generation by Delaunay Refinement".
    - Si 2015 TetGen §4 edge recovery via flips.
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass

import numpy as np


@dataclass
class TargetedFlipResult:
    n_edges_attempted: int
    n_edges_recovered: int
    n_guard_rejected: int = 0


def _find_tets_containing_both(tets: np.ndarray, u: int, v: int) -> list[int]:
    """u 와 v 를 동시에 포함한 tet id 리스트."""
    mask = ((tets == u).any(axis=1)) & ((tets == v).any(axis=1))
    return np.where(mask)[0].tolist()


def _has_edge(tets: np.ndarray, u: int, v: int) -> bool:
    """현재 tet 배열에 edge (u, v) 가 존재하는지."""
    return bool(((tets == u).any(axis=1) & (tets == v).any(axis=1)).any())


def _boundary_face_keys(rows: np.ndarray) -> frozenset[tuple[int, int, int]]:
    """Return the local boundary face keys of a small tet-row collection."""

    counts: Counter[tuple[int, int, int]] = Counter()
    for row in np.asarray(rows, dtype=np.int64).tolist():
        a, b, c, d = (int(value) for value in row)
        for face in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
            counts[tuple(sorted(face))] += 1
    return frozenset(key for key, count in counts.items() if count == 1)


def _local_flip_is_safe(
    pts: np.ndarray,
    old_rows: np.ndarray,
    new_rows: np.ndarray,
) -> bool:
    """Check local topology and non-degeneracy before applying one 2-3 flip."""

    if _boundary_face_keys(old_rows) != _boundary_face_keys(new_rows):
        return False
    from core.generator.native_tet.validate import signed_volume6

    volumes = signed_volume6(pts, new_rows)
    if volumes.size == 0 or not np.all(np.isfinite(volumes)):
        return False
    bbox_diag = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    volume_tol = max(bbox_diag ** 3, 1.0) * 1.0e-14
    return bool(np.all(np.abs(volumes) > volume_tol))


def _edge_in_any_tet_set(tets_list: list[list[int]], u: int, v: int) -> bool:
    for t in tets_list:
        if u in t and v in t:
            return True
    return False


def recover_edges_via_flip(
    pts: np.ndarray,
    tets: np.ndarray,
    missing_edges: list[tuple[int, int]],
    *,
    max_attempts: int = 200,
) -> tuple[np.ndarray, TargetedFlipResult]:
    """각 missing edge 에 대해 2-3 flip 을 시도해 edge 생성.

    전략: edge (u, v) 가 없고, u 와 v 가 각각 포함된 "인접 2 tet (공유 face 존재)"
    쌍이 있다면, 해당 face 를 뒤집어 2-3 flip 수행. 새 edge 가 u-v 가 되도록.

    현재 구현은 간이 — 공유 face 가 (a, b, c) 이고 두 tet 이 (a,b,c,u) /
    (a,b,c,v) 이면 정확히 2-3 flip 이 edge (u, v) 를 만든다.
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets_arr = np.asarray(tets, dtype=np.int64).copy()
    n_attempts = 0
    n_recovered = 0
    n_guard_rejected = 0

    # TET-CDT-SCALE-PERF-1 diagnostic lane.  The legacy path deliberately
    # remains the default until the indexed lookup has been compared against
    # it on the permanent recovery fixtures.  The old implementation scans
    # every tet for the exact opposite tet on each candidate edge, which turns
    # this local search into O(missing_edges * n_tets).
    use_tet_index = os.environ.get(
        "AUTO_TESSELL_TET_EDGE_FLIP_INDEX", "0",
    ).strip().lower() in {"1", "true", "on", "yes"}
    use_candidate_guard = os.environ.get(
        "AUTO_TESSELL_TET_EDGE_FLIP_GUARD", "0",
    ).strip().lower() in {"1", "true", "on", "yes"}

    # The C++23 kernel implements the default deterministic 2→3 route.  Keep
    # the Python diagnostic/index and extra candidate-guard experiments on
    # their existing paths until their full contracts are native as well.
    explicit_diagnostic_route = (
        "AUTO_TESSELL_TET_EDGE_FLIP_INDEX" in os.environ
        or "AUTO_TESSELL_TET_EDGE_FLIP_GUARD" in os.environ
    )
    if not explicit_diagnostic_route:
        from core.utils.native_extensions import load_native_tet_predicates

        native = load_native_tet_predicates()
        kernel = (
            getattr(native, "recover_targeted_edges_23", None)
            if native is not None else None
        )
        if kernel is not None:
            edges = np.asarray(
                sorted((min(int(u), int(v)), max(int(u), int(v))) for u, v in missing_edges),
                dtype=np.int64,
            ).reshape(-1, 2)
            output, stats = kernel(pts, tets_arr, edges, int(max_attempts))
            native_stats = dict(stats)
            return np.asarray(output, dtype=np.int64), TargetedFlipResult(
                n_edges_attempted=int(native_stats["attempted"]),
                n_edges_recovered=int(native_stats["recovered"]),
            )

    if use_tet_index:
        # Stable row IDs avoid rebuilding a full sorted-tet index after every
        # accepted flip. Active rows retain the legacy order; new rows are
        # appended, matching the old keep-mask + vstack result exactly.
        row_records: list[tuple[int, int, int, int]] = [
            tuple(int(x) for x in row) for row in tets_arr.tolist()
        ]
        row_active = [True] * len(row_records)
        tet_index: dict[tuple[int, ...], int] = {}
        vertex_index: dict[int, set[int]] = {}
        edge_counts: dict[tuple[int, int], int] = {}

        def _row_edges(row: tuple[int, int, int, int]):
            a, b, c, d = row
            return (
                (min(a, b), max(a, b)), (min(a, c), max(a, c)),
                (min(a, d), max(a, d)), (min(b, c), max(b, c)),
                (min(b, d), max(b, d)), (min(c, d), max(c, d)),
            )

        def _activate(row_id: int) -> None:
            row = row_records[row_id]
            tet_index.setdefault(tuple(sorted(row)), row_id)
            for vertex in row:
                vertex_index.setdefault(vertex, set()).add(row_id)
            for edge in _row_edges(row):
                edge_counts[edge] = edge_counts.get(edge, 0) + 1

        def _deactivate(row_id: int) -> None:
            row = row_records[row_id]
            key = tuple(sorted(row))
            if tet_index.get(key) == row_id:
                tet_index.pop(key, None)
                # Preserve a valid first match for malformed duplicate rows.
                for other_id, other_row in enumerate(row_records):
                    if (
                        row_active[other_id]
                        and other_id != row_id
                        and tuple(sorted(other_row)) == key
                    ):
                        tet_index[key] = other_id
                        break
            for vertex in row:
                ids = vertex_index.get(vertex)
                if ids is not None:
                    ids.discard(row_id)
                    if not ids:
                        vertex_index.pop(vertex, None)
            for edge in _row_edges(row):
                count = edge_counts[edge] - 1
                if count:
                    edge_counts[edge] = count
                else:
                    edge_counts.pop(edge, None)

        for initial_id in range(len(row_records)):
            _activate(initial_id)
    else:
        row_records = []
        row_active = []
        tet_index = None
        vertex_index = None
        edge_counts = None

    # ``check_edge_recovery`` historically derives this list from a set.  The
    # order is therefore not a valid source of meshing decisions: applying
    # one 2-3 flip changes which later candidates still have a compatible
    # opposite tet.  Canonicalize the input so recovery is independent of
    # caller/set iteration order while retaining the bounded-attempt contract.
    candidate_edges = sorted(
        (min(int(u), int(v)), max(int(u), int(v)))
        for u, v in missing_edges
    )
    for (u, v) in candidate_edges[:max_attempts]:
        n_attempts += 1
        if use_tet_index:
            has_edge = (min(u, v), max(u, v)) in edge_counts
        else:
            has_edge = _has_edge(tets_arr, u, v)
        if has_edge:
            n_recovered += 1
            continue
        # u 포함 tet 중 v 와 face 공유 가능한 쌍 탐색.
        if use_tet_index:
            u_tets = sorted(vertex_index.get(u, ()))
        else:
            u_tets = np.where((tets_arr == u).any(axis=1))[0]
        found = False
        for tu in u_tets:
            if use_tet_index and not row_active[tu]:
                continue
            # tu 의 각 face 중 v 를 포함한 두 tet 이 있는지.
            tu_verts = set(row_records[tu]) if use_tet_index else set(
                int(x) for x in tets_arr[tu]
            )
            face_verts = tu_verts - {u}
            if len(face_verts) != 3:
                continue
            # face 가 (a, b, c) 이면 상대 tet 은 (a, b, c, v).
            face_sorted = tuple(sorted(face_verts))
            fa, fb, fc = face_sorted
            # (fa, fb, fc, v) tet 검색.  The indexed branch is an opt-in
            # performance experiment; the fallback is byte-for-byte the
            # existing candidate search logic.
            target = tuple(sorted([fa, fb, fc, v]))
            if use_tet_index:
                candidate_tv = tet_index.get(target) if tet_index is not None else None
                tv_candidates = () if candidate_tv is None else (candidate_tv,)
            else:
                tv_candidates = range(tets_arr.shape[0])
            for tv in tv_candidates:
                if tv == tu:
                    continue
                target_matches = (
                    row_active[tv]
                    if use_tet_index
                    else tuple(sorted(tets_arr[tv].tolist())) == target
                )
                if target_matches:
                    # 2-3 flip: 제거 tu, tv. 신규 3 tet: (a,b,u,v),(b,c,u,v),(c,a,u,v).
                    new_rows = np.array(
                        [[fa, fb, u, v], [fb, fc, u, v], [fc, fa, u, v]],
                        dtype=np.int64,
                    )
                    if use_candidate_guard:
                        old_rows = np.asarray(
                            [row_records[tu], row_records[tv]]
                            if use_tet_index
                            else [tets_arr[tu], tets_arr[tv]],
                            dtype=np.int64,
                        )
                        if not _local_flip_is_safe(pts, old_rows, new_rows):
                            n_guard_rejected += 1
                            continue
                    if use_tet_index:
                        _deactivate(tu)
                        _deactivate(tv)
                        row_active[tu] = False
                        row_active[tv] = False
                        for new_row in new_rows.tolist():
                            row_records.append(tuple(int(x) for x in new_row))
                            row_active.append(True)
                            _activate(len(row_records) - 1)
                    else:
                        # 기존 두 tet 제거.
                        keep_mask = np.ones(tets_arr.shape[0], dtype=bool)
                        keep_mask[tu] = False
                        keep_mask[tv] = False
                        tets_arr = np.vstack([tets_arr[keep_mask], new_rows])
                    n_recovered += 1
                    found = True
                    break
            if found:
                break

    if use_tet_index:
        tets_arr = np.asarray(
            [row_records[i] for i, active in enumerate(row_active) if active],
            dtype=np.int64,
        )
    return tets_arr, TargetedFlipResult(
        n_edges_attempted=n_attempts,
        n_edges_recovered=n_recovered,
        n_guard_rejected=n_guard_rejected,
    )
