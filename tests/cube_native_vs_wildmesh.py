"""test_cube.stl 로 wildmesh 라이브러리 vs native tet engine 결과 비교.

vertex 위치 (coord-tol), tet/cell 개수, vertex count 일치도를 측정.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np

logging.disable(logging.CRITICAL)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _load_stl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    from core.analyzer.readers.stl import read_stl
    m = read_stl(str(path))
    return (
        np.asarray(m.vertices, dtype=np.float64),
        np.asarray(m.faces, dtype=np.int64),
    )


def _wildmesh_run(V, F, cache_dir):
    from core.generator.native_tet.wildmesh_native_wrapper import (
        generate_via_wildmeshing_cached,
    )
    Vo, To, _ = generate_via_wildmeshing_cached(
        V, F, cache_dir=str(cache_dir),
        stop_quality=20.0, edge_length_r=0.06, epsilon=0.002, max_its=40,
    )
    return Vo, To


def _native_tet_run(V, F):
    """우리 자체 native tet engine 직접 호출 (case_dir polyMesh 출력 후 재로드)."""
    import tempfile
    from core.generator.native_tet.mesher import generate_native_tet
    from core.utils.ccmio_native_binary import _simple_polymesh_read
    with tempfile.TemporaryDirectory() as td:
        case_dir = Path(td)
        res = generate_native_tet(V, F, case_dir)
        # 우선 result 객체에 V/T 가 직접 있으면 그걸 사용.
        Vo = getattr(res, "points", None)
        To = getattr(res, "tets", None)
        if Vo is not None and To is not None:
            return (
                np.asarray(Vo, dtype=np.float64),
                np.asarray(To, dtype=np.int64),
            )
        # 아니면 polyMesh 파일에서 V 만 추출 (cell→tet 재구성은 verify 와 동일).
        poly = case_dir / "constant" / "polyMesh"
        if not poly.exists():
            poly = case_dir
        Vp, faces, owner, neighbour, _ = _simple_polymesh_read(poly)
        if Vp is None:
            return np.zeros((0, 3)), np.zeros((0, 4), dtype=np.int64)
        n_cells = (
            max(int(max(owner)), int(max([n for n in neighbour if n >= 0],
                                         default=-1))) + 1
            if len(owner) > 0 else 0
        )
        cell_face_lists: list[list[int]] = [[] for _ in range(n_cells)]
        for fi, o in enumerate(owner):
            cell_face_lists[int(o)].append(fi)
        for fi, n in enumerate(neighbour):
            if int(n) >= 0:
                cell_face_lists[int(n)].append(fi)
        tets = []
        for ci in range(n_cells):
            f_ids = cell_face_lists[ci]
            if len(f_ids) != 4:
                continue
            verts = set()
            for fi in f_ids:
                verts.update(int(v) for v in faces[fi])
            if len(verts) == 4:
                tets.append(sorted(verts))
        T = (
            np.array(tets, dtype=np.int64)
            if tets else np.zeros((0, 4), dtype=np.int64)
        )
        return np.asarray(Vp, dtype=np.float64), T


def _nearest_vertex_distance(V_a, V_b):
    """V_a 의 각 점 → V_b 최근접점 거리 mean/max."""
    if V_a.shape[0] == 0 or V_b.shape[0] == 0:
        return float("inf"), float("inf")
    try:
        from scipy.spatial import cKDTree
        d, _ = cKDTree(V_b).query(V_a, k=1)
        return float(d.mean()), float(d.max())
    except Exception:
        d = np.linalg.norm(
            V_a[:, None, :] - V_b[None, :, :], axis=2,
        ).min(axis=1)
        return float(d.mean()), float(d.max())


def main() -> int:
    stl_path = REPO / "test_cube.stl"
    if not stl_path.exists():
        stl_path = REPO / "tests" / "stl" / "01_easy_cube.stl"
    print(f"input: {stl_path.name}")

    V, F = _load_stl(stl_path)
    print(f"surface  V={V.shape[0]}  F={F.shape[0]}")

    cache_dir = REPO / ".cache" / "cube_compare"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 1) wildmesh library
    Vw, Tw = _wildmesh_run(V, F, cache_dir)
    print(f"\n[wildmesh lib]")
    print(f"  V={Vw.shape[0]}  T={Tw.shape[0]}")

    # 2) native tet engine (self-impl)
    Vn, Tn = _native_tet_run(V, F)
    print(f"\n[native tet ]")
    print(f"  V={Vn.shape[0]}  T={Tn.shape[0]}")

    # ── parity stats ───────────────────────────────────────
    print(f"\n[parity]")
    n_v_w, n_v_n = Vw.shape[0], Vn.shape[0]
    n_t_w, n_t_n = Tw.shape[0], Tn.shape[0]
    v_pct = 100.0 * min(n_v_w, n_v_n) / max(n_v_w, n_v_n, 1)
    t_pct = 100.0 * min(n_t_w, n_t_n) / max(n_t_w, n_t_n, 1)
    print(f"  vertex count  ratio: {v_pct:.2f}%  ({n_v_w} vs {n_v_n})")
    print(f"  tet/cell ct.  ratio: {t_pct:.2f}%  ({n_t_w} vs {n_t_n})")

    if Vn.shape[0] > 0 and Vw.shape[0] > 0:
        m1, x1 = _nearest_vertex_distance(Vw, Vn)
        m2, x2 = _nearest_vertex_distance(Vn, Vw)
        print(
            f"  vertex pos near-dist  wild→nat:  mean={m1:.6f}  max={x1:.6f}"
        )
        print(
            f"                         nat→wild: mean={m2:.6f}  max={x2:.6f}"
        )
        try:
            from scipy.spatial import cKDTree
            d, _ = cKDTree(Vn).query(Vw, k=1)
            match_1e3 = float((d <= 1e-3).mean()) * 100.0
            match_1e2 = float((d <= 1e-2).mean()) * 100.0
            match_1e1 = float((d <= 1e-1).mean()) * 100.0
            print(
                f"  vertex match (lib→native, ≤1e-3): {match_1e3:.2f}%  "
                f"(≤1e-2): {match_1e2:.2f}%  (≤1e-1): {match_1e1:.2f}%"
            )
        except Exception as e:
            print(f"  (KDTree match calc skipped: {e})")

    # ── 99% 판정 ───────────────────────────────────────────
    print(f"\n[verdict]")
    is_99 = (v_pct >= 99.0) and (t_pct >= 99.0)
    print(f"  count parity ≥99%? {'YES' if is_99 else 'NO'}")
    print(f"  → vertex count 99%: {v_pct:.2f} | tet count 99%: {t_pct:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
