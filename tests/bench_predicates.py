"""Benchmark: Shewchuk C predicates vs Python Fraction (Stage 3).

Usage:
    python3 tests/bench_predicates.py

Reports wall-clock time for:
    orient3d Stage3 — Fraction only (no Shewchuk)
    orient3d Stage3 — Shewchuk C
    insphere Stage3 — Fraction only
    insphere Stage3 — Shewchuk C
"""
from __future__ import annotations

import time
import math
import random
import sys
from pathlib import Path

# Ensure repo root is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

rng = random.Random(42)

N_RANDOM = 100_000
N_DEGENERATE = 1_000

def _rand3():
    return (rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))

# Random (non-degenerate) orient3d cases.
random_orient = [
    (_rand3(), _rand3(), _rand3(), _rand3())
    for _ in range(N_RANDOM)
]

# Near-coplanar cases (Stage 1 will fail, must fall through).
near_coplanar = []
for _ in range(N_DEGENERATE):
    a = (0.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    c = (0.0, 1.0, 0.0)
    eps = rng.uniform(-1e-16, 1e-16)
    d = (0.5, 0.5, eps)
    near_coplanar.append((a, b, c, d))

# Random insphere cases.
random_insphere = []
for _ in range(N_RANDOM):
    a, b, c, d = _rand3(), _rand3(), _rand3(), _rand3()
    e = _rand3()
    random_insphere.append((a, b, c, d, e))

# Near-cospherical insphere cases.
near_cosphere = []
for _ in range(N_DEGENERATE):
    a = (0.0, 0.0, 0.0)
    b = (1.0, 0.0, 0.0)
    c = (0.0, 1.0, 0.0)
    d = (0.0, 0.0, 1.0)
    # circumsphere of (0,0,0),(1,0,0),(0,1,0),(0,0,1): center=(0.5,0.5,0.5), r=sqrt(0.75)
    r = math.sqrt(0.75) + rng.uniform(-1e-15, 1e-15)
    theta = rng.uniform(0, math.pi)
    phi = rng.uniform(0, 2 * math.pi)
    cx, cy, cz = 0.5, 0.5, 0.5
    e = (cx + r * math.sin(theta) * math.cos(phi),
         cy + r * math.sin(theta) * math.sin(phi),
         cz + r * math.cos(theta))
    near_cosphere.append((a, b, c, d, e))

# ---------------------------------------------------------------------------
# Implementations under test
# ---------------------------------------------------------------------------

from core.utils.predicates_exact import orient3d as frac_o3d, insphere as frac_isp

try:
    from core.utils._shewchuk import orient3d as sw_o3d, insphere as sw_isp
    HAS_SHEWCHUK = sw_o3d is not None
except Exception:
    HAS_SHEWCHUK = False

# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def _time_orient3d(fn, cases, label):
    t0 = time.perf_counter()
    for a, b, c, d in cases:
        fn(a, b, c, d)
    elapsed = time.perf_counter() - t0
    print(f"  {label:45s} {elapsed * 1000:.1f} ms  ({len(cases)} calls, {elapsed/len(cases)*1e6:.3f} us/call)")
    return elapsed


def _time_insphere(fn, cases, label):
    t0 = time.perf_counter()
    for a, b, c, d, e in cases:
        fn(a, b, c, d, e)
    elapsed = time.perf_counter() - t0
    print(f"  {label:45s} {elapsed * 1000:.1f} ms  ({len(cases)} calls, {elapsed/len(cases)*1e6:.3f} us/call)")
    return elapsed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"\n{'='*70}")
    print("Predicate benchmark — Fraction vs Shewchuk C")
    print(f"  N_random = {N_RANDOM:,}   N_degenerate = {N_DEGENERATE:,}")
    print(f"  HAS_SHEWCHUK = {HAS_SHEWCHUK}")
    print(f"{'='*70}\n")

    print("orient3d — random (100k):")
    t_frac_r = _time_orient3d(frac_o3d, random_orient, "Fraction")
    if HAS_SHEWCHUK:
        t_sw_r = _time_orient3d(sw_o3d, random_orient, "Shewchuk C")
        print(f"  Speedup (random): {t_frac_r / t_sw_r:.1f}x")

    print("\norient3d — near-coplanar (1k):")
    t_frac_d = _time_orient3d(frac_o3d, near_coplanar, "Fraction")
    if HAS_SHEWCHUK:
        t_sw_d = _time_orient3d(sw_o3d, near_coplanar, "Shewchuk C")
        print(f"  Speedup (degenerate): {t_frac_d / t_sw_d:.1f}x")

    print("\ninsphere — random (100k):")
    t_frac_r = _time_insphere(frac_isp, random_insphere, "Fraction")
    if HAS_SHEWCHUK:
        t_sw_r = _time_insphere(sw_isp, random_insphere, "Shewchuk C")
        print(f"  Speedup (random): {t_frac_r / t_sw_r:.1f}x")

    print("\ninsphere — near-cospherical (1k):")
    t_frac_d = _time_insphere(frac_isp, near_cosphere, "Fraction")
    if HAS_SHEWCHUK:
        t_sw_d = _time_insphere(sw_isp, near_cosphere, "Shewchuk C")
        print(f"  Speedup (degenerate): {t_frac_d / t_sw_d:.1f}x")

    print()


if __name__ == "__main__":
    main()
