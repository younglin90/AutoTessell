"""Shewchuk exact geometric predicates — bundled C implementation.

Public domain — Jonathan R. Shewchuk 1996/1997.
Bundled for AutoTessell: https://www.cs.cmu.edu/~quake/robust.html

This module:
1. Checks for a pre-built libshewchuk_predicates.so next to this file.
2. If not found, attempts to compile it with ``cc -O2 -fPIC -shared``.
3. Loads the .so via ctypes and exposes two Python-callable functions:
   - orient3d(a, b, c, d) -> int  (-1 / 0 / +1)
   - insphere(a, b, c, d, e) -> int  (-1 / 0 / +1)
4. If compilation or loading fails, orient3d / insphere are set to None
   (silent fallback — caller must check).

Design rationale (CLAUDE.md "외부 의존 점진적 제거"):
  This is a self-contained C bundle with no PyPI dependency.
  The .so is compiled once on first import and cached on disk.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

_HERE = Path(__file__).parent.resolve()
_SO_PATH = _HERE / "libshewchuk_predicates.so"
_WRAPPER_C = _HERE / "wrapper.c"

# Public: None if unavailable, otherwise ctypes-backed callable.
orient3d: Optional[callable] = None
insphere: Optional[callable] = None

_lib: Optional[ctypes.CDLL] = None


def _try_compile() -> bool:
    """Attempt to compile wrapper.c -> libshewchuk_predicates.so.

    Returns True on success, False otherwise (silent).
    """
    if not _WRAPPER_C.exists():
        return False
    try:
        result = subprocess.run(
            [
                "cc", "-O2", "-fPIC", "-shared",
                str(_WRAPPER_C),
                "-o", str(_SO_PATH),
                "-lm",
            ],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def _load_lib() -> Optional[ctypes.CDLL]:
    """Load the shared library and configure function signatures.

    Returns the ctypes.CDLL handle, or None on failure.
    """
    if not _SO_PATH.exists():
        return None
    try:
        lib = ctypes.CDLL(str(_SO_PATH))
    except OSError:
        return None

    # void shewchuk_init(void)
    try:
        lib.shewchuk_init.restype = None
        lib.shewchuk_init.argtypes = []
        lib.shewchuk_init()
    except Exception:
        return None

    # int orient3d_sign(double*, double*, double*, double*)
    try:
        lib.orient3d_sign.restype = ctypes.c_int
        lib.orient3d_sign.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
        ]
    except Exception:
        return None

    # int insphere_sign(double*, double*, double*, double*, double*)
    try:
        lib.insphere_sign.restype = ctypes.c_int
        lib.insphere_sign.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
        ]
    except Exception:
        return None

    return lib


def _make_c_array(seq: Sequence[float]) -> ctypes.Array:
    """Convert a 3-element sequence to a ctypes double[3]."""
    return (ctypes.c_double * 3)(float(seq[0]), float(seq[1]), float(seq[2]))


def _make_orient3d(lib: ctypes.CDLL):
    """Return a Python wrapper for orient3d_sign."""
    _fn = lib.orient3d_sign

    def _orient3d(a, b, c, d) -> int:
        """Adaptive exact 3D orientation test.

        Returns +1 if d is below the plane through a,b,c (ccw from above),
        -1 if above, 0 if coplanar.
        """
        return int(_fn(_make_c_array(a), _make_c_array(b),
                        _make_c_array(c), _make_c_array(d)))

    return _orient3d


def _make_insphere(lib: ctypes.CDLL):
    """Return a Python wrapper for insphere_sign."""
    _fn = lib.insphere_sign

    def _insphere(a, b, c, d, e) -> int:
        """Adaptive exact 3D insphere test.

        a,b,c,d must form a positively-oriented tetrahedron.
        Returns +1 if e is inside the circumsphere, -1 if outside, 0 if on.
        """
        return int(_fn(_make_c_array(a), _make_c_array(b), _make_c_array(c),
                        _make_c_array(d), _make_c_array(e)))

    return _insphere


def _init() -> None:
    global _lib, orient3d, insphere  # noqa: PLW0603

    # Step 1: compile if .so missing.
    if not _SO_PATH.exists():
        _try_compile()

    # Step 2: load.
    lib = _load_lib()
    if lib is None:
        # Silent fallback — predicates_staged.py will use Fraction path.
        return

    _lib = lib
    orient3d = _make_orient3d(lib)
    insphere = _make_insphere(lib)


def is_available() -> bool:
    """Return True if the Shewchuk C predicates are loaded and usable."""
    return orient3d is not None


# Run at import time.
_init()
