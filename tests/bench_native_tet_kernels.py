"""Micro-benchmark: C kernels vs Python for native_tet hot loops.

Run standalone:
    python3 tests/bench_native_tet_kernels.py

No pytest dependency required.
"""
from __future__ import annotations

import time

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mesh(n_pts: int, n_tets: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    pts  = rng.standard_normal((n_pts, 3))
    tets = rng.integers(0, n_pts, size=(n_tets, 4), dtype=np.int64)
    return pts, tets


def _timeit(fn, *args, repeat: int = 5) -> float:
    """Return minimum wall time (seconds) over `repeat` runs."""
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn(*args)
        times.append(time.perf_counter() - t0)
    return min(times)


# ---------------------------------------------------------------------------
# Python reference kernels
# ---------------------------------------------------------------------------

def _py_quality_batch(pts, tets):
    out = np.empty(tets.shape[0])
    for i, row in enumerate(tets):
        A, B, C, D = pts[row[0]], pts[row[1]], pts[row[2]], pts[row[3]]
        v = abs(float(np.dot(B - A, np.cross(C - A, D - A)))) / 6.0
        e = [A - B, A - C, A - D, B - C, B - D, C - D]
        emax = max(float(np.linalg.norm(x)) for x in e)
        out[i] = 0.0 if emax < 1e-30 else 8.48 * v / (emax ** 3)
    return out


def _np_quality_batch(pts, tets):
    """Vectorised numpy quality (no Python per-tet loop)."""
    A = pts[tets[:, 0]]
    B = pts[tets[:, 1]]
    C = pts[tets[:, 2]]
    D = pts[tets[:, 3]]
    BA = B - A; CA = C - A; DA = D - A
    cr  = np.cross(CA, DA)
    vol = np.abs(np.einsum("ij,ij->i", BA, cr)) / 6.0
    edges = np.stack([BA, CA, DA, B - C, B - D, C - D], axis=1)
    emax  = np.linalg.norm(edges, axis=2).max(axis=1)
    return np.where(emax < 1e-30, 0.0, 8.48 * vol / (emax ** 3))


def _py_vol6_batch(pts, tets):
    out = np.empty(tets.shape[0])
    for i, row in enumerate(tets):
        A, B, C, D = pts[row[0]], pts[row[1]], pts[row[2]], pts[row[3]]
        out[i] = float(np.dot(B - A, np.cross(C - A, D - A)))
    return out


def _np_vol6_batch(pts, tets):
    A = pts[tets[:, 0]]; B = pts[tets[:, 1]]
    C = pts[tets[:, 2]]; D = pts[tets[:, 3]]
    BA = B - A; CA = C - A; DA = D - A
    return np.einsum("ij,ij->i", BA, np.cross(CA, DA))


def _py_face_map(tets):
    face_arr = np.stack(
        [tets[:, [1, 2, 3]], tets[:, [0, 2, 3]],
         tets[:, [0, 1, 3]], tets[:, [0, 1, 2]]],
        axis=1,
    ).reshape(-1, 3)
    face_arr.sort(axis=1)
    m = {}
    for idx in range(face_arr.shape[0]):
        ti = idx // 4
        k = (int(face_arr[idx, 0]), int(face_arr[idx, 1]), int(face_arr[idx, 2]))
        m.setdefault(k, []).append(ti)
    return m


def _py_edge_lengths_dict(pts, tets):
    pairs = np.stack(
        [tets[:, [0, 1]], tets[:, [0, 2]], tets[:, [0, 3]],
         tets[:, [1, 2]], tets[:, [1, 3]], tets[:, [2, 3]]],
        axis=1,
    ).reshape(-1, 2)
    pairs.sort(axis=1)
    struct = np.ascontiguousarray(pairs).view(
        np.dtype((np.void, pairs.dtype.itemsize * 2))
    )
    _, idx = np.unique(struct, return_index=True)
    uniq = pairs[idx]
    lens = np.linalg.norm(pts[uniq[:, 0]] - pts[uniq[:, 1]], axis=1)
    return {(int(uniq[i, 0]), int(uniq[i, 1])): float(lens[i]) for i in range(uniq.shape[0])}


# ---------------------------------------------------------------------------
# C kernel wrappers
# ---------------------------------------------------------------------------

from core.generator.native_tet._native import (
    build_edge_to_tets as _c_build_edge_to_tets,
    build_face_to_tets as _c_build_face_to_tets,
    edge_lengths_batch as _c_edge_lengths_batch,
    is_available,
    tet_quality_batch as _c_quality_batch,
    tet_signed_vol6_batch as _c_vol6_batch,
)


def _c_face_map_full(tets):
    result = _c_build_face_to_tets(tets)
    if result is None:
        return {}
    face_arr, tet_idx, _ = result
    m = {}
    for i in range(face_arr.shape[0]):
        k = (int(face_arr[i, 0]), int(face_arr[i, 1]), int(face_arr[i, 2]))
        m.setdefault(k, []).append(int(tet_idx[i]))
    return m


def _c_edge_lengths_full(pts, tets):
    result = _c_build_edge_to_tets(tets)
    if result is None:
        return {}
    edges_all, _ = result
    struct = np.ascontiguousarray(edges_all).view(
        np.dtype((np.void, edges_all.dtype.itemsize * 2))
    )
    _, idx = np.unique(struct, return_index=True)
    uniq = edges_all[idx]
    lens = _c_edge_lengths_batch(pts, uniq)
    return {(int(uniq[i, 0]), int(uniq[i, 1])): float(lens[i]) for i in range(uniq.shape[0])}


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def fmt_speedup(t_slow, t_fast):
    if t_fast == 0:
        return "inf"
    return f"{t_slow / t_fast:.1f}x"


def run_benchmarks(n_tets: int = 100_000, repeat: int = 5):
    print(f"\n{'='*72}")
    print(f"  native_tet C kernel benchmark   n_tets={n_tets:,}  repeat={repeat}")
    print(f"{'='*72}\n")

    if not is_available():
        print("  C kernels NOT available — skipping benchmark.")
        return {}

    pts, tets = _make_mesh(n_pts=n_tets + 200, n_tets=n_tets, seed=0)

    results = {}

    # ---------- quality ----------
    t_py  = _timeit(_py_quality_batch, pts, tets, repeat=repeat)
    t_np  = _timeit(_np_quality_batch, pts, tets, repeat=repeat)
    t_c   = _timeit(_c_quality_batch,  pts, tets, repeat=repeat)
    results["quality_py_s"]  = t_py
    results["quality_np_s"]  = t_np
    results["quality_c_s"]   = t_c
    results["quality_py_vs_c"]  = t_py / t_c if t_c > 0 else float("inf")
    results["quality_np_vs_c"]  = t_np / t_c if t_c > 0 else float("inf")
    print(f"  quality_batch ({n_tets:,} tets):")
    print(f"    Python loop : {t_py*1000:.1f} ms")
    print(f"    numpy vec   : {t_np*1000:.1f} ms   speedup vs Python: {fmt_speedup(t_py, t_np)}")
    print(f"    C kernel    : {t_c*1000:.1f} ms   speedup vs Python: {fmt_speedup(t_py, t_c)}")
    print(f"                                    speedup vs numpy:  {fmt_speedup(t_np, t_c)}\n")

    # ---------- vol6 ----------
    t_py  = _timeit(_py_vol6_batch, pts, tets, repeat=repeat)
    t_np  = _timeit(_np_vol6_batch, pts, tets, repeat=repeat)
    t_c   = _timeit(_c_vol6_batch,  pts, tets, repeat=repeat)
    results["vol6_py_s"]  = t_py
    results["vol6_np_s"]  = t_np
    results["vol6_c_s"]   = t_c
    results["vol6_py_vs_c"]  = t_py / t_c if t_c > 0 else float("inf")
    results["vol6_np_vs_c"]  = t_np / t_c if t_c > 0 else float("inf")
    print(f"  vol6_batch ({n_tets:,} tets):")
    print(f"    Python loop : {t_py*1000:.1f} ms")
    print(f"    numpy vec   : {t_np*1000:.1f} ms   speedup vs Python: {fmt_speedup(t_py, t_np)}")
    print(f"    C kernel    : {t_c*1000:.1f} ms   speedup vs Python: {fmt_speedup(t_py, t_c)}")
    print(f"                                    speedup vs numpy:  {fmt_speedup(t_np, t_c)}\n")

    # ---------- face map ----------
    t_py  = _timeit(_py_face_map,      tets, repeat=repeat)
    t_c   = _timeit(_c_face_map_full,  tets, repeat=repeat)
    results["face_map_py_s"]  = t_py
    results["face_map_c_s"]   = t_c
    results["face_map_py_vs_c"]  = t_py / t_c if t_c > 0 else float("inf")
    print(f"  face_map ({n_tets:,} tets):")
    print(f"    Python      : {t_py*1000:.1f} ms")
    print(f"    C kernel    : {t_c*1000:.1f} ms   speedup: {fmt_speedup(t_py, t_c)}\n")

    # ---------- edge_lengths ----------
    t_py  = _timeit(_py_edge_lengths_dict,   pts, tets, repeat=repeat)
    t_c   = _timeit(_c_edge_lengths_full,    pts, tets, repeat=repeat)
    results["edge_lengths_py_s"]  = t_py
    results["edge_lengths_c_s"]   = t_c
    results["edge_lengths_py_vs_c"]  = t_py / t_c if t_c > 0 else float("inf")
    print(f"  edge_lengths ({n_tets:,} tets):")
    print(f"    Python      : {t_py*1000:.1f} ms")
    print(f"    C kernel    : {t_c*1000:.1f} ms   speedup: {fmt_speedup(t_py, t_c)}\n")

    print(f"{'='*72}\n")
    return results


if __name__ == "__main__":
    run_benchmarks(n_tets=100_000, repeat=5)
