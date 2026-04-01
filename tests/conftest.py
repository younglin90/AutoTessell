"""pytest 공통 픽스처."""

from __future__ import annotations

from pathlib import Path

import pytest


BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"


@pytest.fixture(scope="session")
def sphere_stl() -> Path:
    p = BENCHMARKS_DIR / "sphere.stl"
    assert p.exists(), f"벤치마크 STL 없음: {p}"
    return p


@pytest.fixture(scope="session")
def cylinder_stl() -> Path:
    p = BENCHMARKS_DIR / "cylinder.stl"
    assert p.exists(), f"벤치마크 STL 없음: {p}"
    return p
