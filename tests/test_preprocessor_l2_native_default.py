"""beta33 — Preprocessor L2 native 기본화 회귀 테스트.

CLI `--prefer-native` default=True (beta26) 은 L1 뿐 아니라 L2 경로도 영향.
즉 prefer_native=True 주입 시 _l2_remesh 가 _l2_remesh_native 로 dispatch.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


def test_l2_remesh_native_dispatch_when_prefer_native_true() -> None:
    """prefer_native=True 면 _l2_remesh 가 native 경로로 dispatch."""
    import trimesh

    from core.preprocessor.pipeline import Preprocessor

    # sphere — native isotropic_remesh 가 다룰 수 있는 단순 형상
    sphere = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    pp = Preprocessor()

    new_mesh, passed, record = pp._l2_remesh(
        sphere, target_faces=None, prefer_native=True,
    )
    assert record["method"] in ("native_isotropic", "skipped")
    # native 경로 성공 시 mesh 가 비어있지 않음
    assert len(new_mesh.vertices) > 0
    assert len(new_mesh.faces) > 0


def test_l2_remesh_legacy_dispatch_when_prefer_native_false() -> None:
    """prefer_native=False 면 _l2_remesh 가 legacy SurfaceRemesher 로 dispatch.
    legacy 의존 (pyACVD 등) 미설치 환경에서는 gracefully skip / pass-through 허용.
    """
    import trimesh

    from core.preprocessor.pipeline import Preprocessor

    sphere = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    pp = Preprocessor()

    new_mesh, passed, record = pp._l2_remesh(
        sphere, target_faces=None, prefer_native=False,
    )
    # native 경로로 가면 method=native_isotropic 일 것이므로,
    # legacy 경로에서는 method 가 다른 값이어야 함 (pyACVD / pymeshlab / skipped /
    # remesh_vorpalite 등).
    assert record["method"] != "native_isotropic"


def test_l2_remesh_native_pymeshfix_not_required() -> None:
    """native L2 경로는 pymeshfix / pyACVD 설치 없이도 작동해야."""
    import trimesh

    from core.preprocessor.pipeline import Preprocessor

    # 작은 sphere
    sphere = trimesh.creation.icosphere(subdivisions=0, radius=1.0)
    pp = Preprocessor()
    new_mesh, passed, record = pp._l2_remesh_native(sphere, target_faces=None)
    assert record["method"] == "native_isotropic"
    assert "input_faces" in record
    assert "output_faces" in record
