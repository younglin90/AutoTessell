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


# ---------------------------------------------------------------------------
# trimesh 벤치마크 형상 생성 픽스처
# ---------------------------------------------------------------------------


def _generate_procedural_benchmarks():
    """trimesh 라이브러리로 벤치마크 형상 생성 (필요 시에만).

    생성할 형상:
    - trimesh_duct.stl: 덕트 형상 (원통 + 박스)
    - trimesh_channel.stl: 채널 형상
    - trimesh_box.stl: 박스 형상
    """
    import trimesh
    import numpy as np

    # trimesh_box.stl: 단순 박스
    try:
        box_path = BENCHMARKS_DIR / "trimesh_box.stl"
        if not box_path.exists():
            box_mesh = trimesh.creation.box(extents=[2.0, 1.5, 1.0])
            box_mesh.export(str(box_path))
    except Exception:
        pass

    # trimesh_duct.stl: 원통 (덕트 간단한 버전)
    try:
        duct_path = BENCHMARKS_DIR / "trimesh_duct.stl"
        if not duct_path.exists():
            cylinder_mesh = trimesh.creation.cylinder(
                radius=1.0, height=3.0, sections=32
            )
            cylinder_mesh.export(str(duct_path))
    except Exception:
        pass

    # trimesh_channel.stl: 토러스 (채널 형상의 단순화 버전)
    try:
        channel_path = BENCHMARKS_DIR / "trimesh_channel.stl"
        if not channel_path.exists():
            torus_mesh = trimesh.creation.torus(
                major_radius=2.0, minor_radius=0.5, sections=32
            )
            torus_mesh.export(str(channel_path))
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def setup_procedural_benchmarks():
    """Session 시작 시 절차적 벤치마크 생성."""
    try:
        _generate_procedural_benchmarks()
    except Exception:
        # 생성 실패 시 무시
        pass
