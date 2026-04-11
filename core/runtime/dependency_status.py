"""런타임 의존성 상태 탐지 유틸리티."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass

from core.utils.openfoam_utils import get_openfoam_label_size


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    category: str
    optional: bool
    detected: bool
    detector: str
    fallback: str
    action: str


def _has_module(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _has_bin(binary: str) -> bool:
    return shutil.which(binary) is not None


def collect_dependency_statuses() -> list[DependencyStatus]:
    """코드의 실제 런타임 탐지 기준으로 의존성 상태를 반환한다."""
    label_bits = get_openfoam_label_size()
    openfoam_ok = label_bits in (32, 64)

    return [
        DependencyStatus(
            name="OpenFOAM",
            category="core",
            optional=False,
            detected=openfoam_ok,
            detector="get_openfoam_label_size()",
            fallback="native checker + PolyMeshWriter 중심 경로",
            action="OpenFOAM 2406+ 설치 후 환경변수 OPENFOAM_DIR 설정",
        ),
        DependencyStatus(
            name="pymeshfix",
            category="surface-repair",
            optional=True,
            detected=_has_module("pymeshfix"),
            detector="import pymeshfix",
            fallback="trimesh repair fallback",
            action="pip install pymeshfix",
        ),
        DependencyStatus(
            name="mesh2sdf",
            category="surface-repair",
            optional=True,
            detected=_has_module("mesh2sdf"),
            detector="import mesh2sdf",
            fallback="L1 mesh2sdf fallback 비활성",
            action="pip install mesh2sdf",
        ),
        DependencyStatus(
            name="pyacvd+pyvista",
            category="surface-remesh",
            optional=True,
            detected=_has_module("pyacvd") and _has_module("pyvista"),
            detector="import pyacvd, pyvista",
            fallback="리메쉬 패스스루",
            action="pip install pyacvd pyvista",
        ),
        DependencyStatus(
            name="pymeshlab",
            category="surface-remesh",
            optional=True,
            detected=_has_module("pymeshlab"),
            detector="import pymeshlab",
            fallback="isotropic remesh 생략",
            action="pip install pymeshlab",
        ),
        DependencyStatus(
            name="quadwild",
            category="surface-remesh",
            optional=True,
            detected=_has_bin("quadwild"),
            detector="shutil.which('quadwild')",
            fallback="vorpalite/pyacvd/pymeshlab 순 fallback",
            action="quadwild 바이너리 설치 후 PATH 등록",
        ),
        DependencyStatus(
            name="vorpalite",
            category="surface-remesh",
            optional=True,
            detected=_has_bin("vorpalite"),
            detector="shutil.which('vorpalite')",
            fallback="pyacvd/pymeshlab fallback",
            action="vorpalite(geogram) 설치 후 PATH 등록",
        ),
        DependencyStatus(
            name="netgen-mesher",
            category="volume-mesh",
            optional=True,
            detected=_has_module("netgen"),
            detector="import netgen",
            fallback="MeshPy/cfMesh/TetWild fallback",
            action="pip install netgen-mesher",
        ),
        DependencyStatus(
            name="meshpy",
            category="volume-mesh",
            optional=True,
            detected=_has_module("meshpy"),
            detector="import meshpy",
            fallback="cfMesh/TetWild fallback",
            action="pip install meshpy",
        ),
        DependencyStatus(
            name="pytetwild",
            category="volume-mesh",
            optional=True,
            detected=_has_module("pytetwild"),
            detector="import pytetwild",
            fallback="다른 tier로 fallback",
            action="pip install pytetwild",
        ),
        DependencyStatus(
            name="jigsawpy",
            category="volume-mesh",
            optional=True,
            detected=_has_module("jigsawpy"),
            detector="import jigsawpy",
            fallback="다른 tier로 fallback",
            action="pip install jigsawpy",
        ),
        DependencyStatus(
            name="classy_blocks",
            category="volume-mesh",
            optional=True,
            detected=_has_module("classy_blocks"),
            detector="import classy_blocks",
            fallback="cfMesh/snappy/netgen fallback",
            action="pip install classy-blocks",
        ),
        DependencyStatus(
            name="mmg3d",
            category="postprocess",
            optional=True,
            detected=_has_bin("mmg3d"),
            detector="shutil.which('mmg3d')",
            fallback="후처리 없이 진행",
            action="MMG3D 설치 후 PATH 등록",
        ),
        DependencyStatus(
            name="cadquery",
            category="cad-convert",
            optional=True,
            detected=_has_module("cadquery"),
            detector="import cadquery",
            fallback="gmsh CLI fallback",
            action="pip install cadquery",
        ),
        DependencyStatus(
            name="gmsh",
            category="cad-convert",
            optional=True,
            detected=_has_module("gmsh") or _has_bin("gmsh"),
            detector="import gmsh or shutil.which('gmsh')",
            fallback="STEP/IGES 일부 경로 제한",
            action="pip install gmsh 또는 gmsh CLI 설치",
        ),
        DependencyStatus(
            name="meshio",
            category="io",
            optional=True,
            detected=_has_module("meshio"),
            detector="import meshio",
            fallback="일부 포맷 로딩 불가",
            action="pip install meshio",
        ),
        DependencyStatus(
            name="ofpp",
            category="evaluator",
            optional=True,
            detected=_has_module("Ofpp"),
            detector="import Ofpp",
            fallback="내장 parser 우선 사용",
            action="pip install ofpp",
        ),
    ]
