"""Native C kernels for native_tet hot loops.

Auto-build pattern identical to core/utils/_shewchuk/__init__.py.

Exposed functions (all return None / arrays via ctypes; None on failure):

    tet_quality_batch(pts, tets) -> np.ndarray  shape (n_tets,)
    tet_signed_vol6_batch(pts, tets) -> np.ndarray  shape (n_tets,)
    build_face_to_tets(tets) -> (faces, tet_idx, slot)
        faces   : (n_tets*4, 3) int64   sorted triples
        tet_idx : (n_tets*4,)   int64
        slot    : (n_tets*4,)   int64
    build_edge_to_tets(tets) -> (edges, tet_idx)
        edges   : (n_tets*6, 2) int64   sorted pairs
        tet_idx : (n_tets*6,)   int64
    edge_lengths_batch(pts, edges) -> np.ndarray  shape (n_edges,)

All functions return None on failure; callers must fall back to Python.
"""
from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

_HERE = Path(__file__).parent.resolve()
_SO_PATH = _HERE / "libtet_kernels.so"
_C_SRC = _HERE / "tet_kernels.c"

_lib: Optional[ctypes.CDLL] = None
_available: bool = False


def _try_compile() -> bool:
    if not _C_SRC.exists():
        return False
    try:
        result = subprocess.run(
            [
                "cc", "-O3", "-march=native", "-fPIC", "-shared",
                "-std=c99",
                str(_C_SRC),
                "-o", str(_SO_PATH),
                "-lm",
            ],
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def _load_lib() -> Optional[ctypes.CDLL]:
    if not _SO_PATH.exists():
        return None
    try:
        lib = ctypes.CDLL(str(_SO_PATH))
    except OSError:
        return None

    c_double_p = ctypes.POINTER(ctypes.c_double)
    c_long_p   = ctypes.POINTER(ctypes.c_long)

    try:
        # tet_quality_batch
        lib.tet_quality_batch.restype  = None
        lib.tet_quality_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
        ]
        # tet_signed_vol6_batch
        lib.tet_signed_vol6_batch.restype  = None
        lib.tet_signed_vol6_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
        ]
        # build_face_to_tets
        lib.build_face_to_tets.restype  = ctypes.c_int
        lib.build_face_to_tets.argtypes = [
            c_long_p, ctypes.c_int,
            c_long_p, c_long_p, c_long_p,
            ctypes.c_int,
        ]
        # build_edge_to_tets
        lib.build_edge_to_tets.restype  = ctypes.c_int
        lib.build_edge_to_tets.argtypes = [
            c_long_p, ctypes.c_int,
            c_long_p, c_long_p,
            ctypes.c_int,
        ]
        # edge_lengths_batch
        lib.edge_lengths_batch.restype  = None
        lib.edge_lengths_batch.argtypes = [
            c_double_p,
            c_long_p, ctypes.c_int,
            c_double_p,
        ]
    except Exception:
        return None

    return lib


def _init() -> None:
    global _lib, _available  # noqa: PLW0603
    if not _SO_PATH.exists():
        _try_compile()
    lib = _load_lib()
    if lib is None:
        return
    _lib = lib
    _available = True


def is_available() -> bool:
    return _available


# ---------------------------------------------------------------------------
# Public API helpers
# ---------------------------------------------------------------------------

def _c_double_ptr(arr: np.ndarray) -> ctypes.POINTER:
    a = np.ascontiguousarray(arr, dtype=np.float64)
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), a


def _c_long_ptr(arr: np.ndarray) -> ctypes.POINTER:
    a = np.ascontiguousarray(arr, dtype=np.int64)
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_long)), a


def tet_quality_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[np.ndarray]:
    """Return quality array shape (n_tets,), or None if C unavailable."""
    if _lib is None:
        return None
    pts  = np.ascontiguousarray(pts,  dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    out = np.empty(n_tets, dtype=np.float64)

    pts_p,  _pts_k  = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    out_p,  _out_k  = _c_double_ptr(out)

    _lib.tet_quality_batch(
        pts_p,  ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        out_p,
    )
    return _out_k


def tet_signed_vol6_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[np.ndarray]:
    """Return signed vol*6 array shape (n_tets,), or None if C unavailable."""
    if _lib is None:
        return None
    pts  = np.ascontiguousarray(pts,  dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    out = np.empty(n_tets, dtype=np.float64)

    pts_p,  _pts_k  = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    out_p,  _out_k  = _c_double_ptr(out)

    _lib.tet_signed_vol6_batch(
        pts_p,  ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        out_p,
    )
    return _out_k


def build_face_to_tets(
    tets: np.ndarray,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Return (faces, tet_idx, slot) arrays, each length n_tets*4, or None."""
    if _lib is None:
        return None
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets  = tets.shape[0]
    n_faces = n_tets * 4

    faces   = np.empty((n_faces, 3), dtype=np.int64)
    tet_idx = np.empty(n_faces,      dtype=np.int64)
    slot    = np.empty(n_faces,      dtype=np.int64)

    tets_p, _tets_k = _c_long_ptr(tets)
    f_p,    _f_k    = _c_long_ptr(faces)
    ti_p,   _ti_k   = _c_long_ptr(tet_idx)
    sl_p,   _sl_k   = _c_long_ptr(slot)

    ret = _lib.build_face_to_tets(
        tets_p, ctypes.c_int(n_tets),
        f_p, ti_p, sl_p,
        ctypes.c_int(n_faces),
    )
    if ret < 0:
        return None
    return _f_k[:ret], _ti_k[:ret], _sl_k[:ret]


def build_edge_to_tets(
    tets: np.ndarray,
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Return (edges, tet_idx) arrays, each length n_tets*6, or None."""
    if _lib is None:
        return None
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets  = tets.shape[0]
    n_edges = n_tets * 6

    edges   = np.empty((n_edges, 2), dtype=np.int64)
    tet_idx = np.empty(n_edges,      dtype=np.int64)

    tets_p, _tets_k = _c_long_ptr(tets)
    e_p,    _e_k    = _c_long_ptr(edges)
    ti_p,   _ti_k   = _c_long_ptr(tet_idx)

    ret = _lib.build_edge_to_tets(
        tets_p, ctypes.c_int(n_tets),
        e_p, ti_p,
        ctypes.c_int(n_edges),
    )
    if ret < 0:
        return None
    return _e_k[:ret], _ti_k[:ret]


def edge_lengths_batch(
    pts: np.ndarray,
    edges: np.ndarray,
) -> Optional[np.ndarray]:
    """Return length array shape (n_edges,), or None if C unavailable."""
    if _lib is None:
        return None
    pts   = np.ascontiguousarray(pts,   dtype=np.float64)
    edges = np.ascontiguousarray(edges, dtype=np.int64)
    n_edges = edges.shape[0]
    out = np.empty(n_edges, dtype=np.float64)

    pts_p,  _pts_k  = _c_double_ptr(pts)
    e_p,    _e_k    = _c_long_ptr(edges)
    out_p,  _out_k  = _c_double_ptr(out)

    _lib.edge_lengths_batch(
        pts_p,
        e_p, ctypes.c_int(n_edges),
        out_p,
    )
    return _out_k


# Run at import time
_init()
