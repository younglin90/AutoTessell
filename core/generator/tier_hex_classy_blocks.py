"""Tier Hex: classy_blocks 기반 구조적 Hex 메시 생성기.

blockMeshDict Python 코드 생성 → blockMesh 실행 → snappyHexMesh 표면 정렬.
단순 형상 (블록 기반)에 적합한 고품질 Hex 메시를 생성한다.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

# numpy 2.x 호환 패치 — classy_blocks가 내부적으로 제거된 numpy 타입 별칭을 사용
# numpy 2.0에서 제거된 모든 타입 별칭을 일괄 복원
_NP2_COMPAT: dict[str, object] = {
    # Boolean
    "bool8":         np.bool_,
    # Integer
    "int0":          np.intp,
    "uint0":         np.uintp,
    "int_":          np.int_,
    # Float
    "float_":        np.float64,
    "longfloat":     np.longdouble,
    # Complex
    "complex_":      np.complex128,
    "singlecomplex": np.complex64,
    "longcomplex":   getattr(np, "clongdouble", np.complex128),
    "cfloat":        np.complex128,
    "cdouble":       np.complex128,
    "clongdouble":   getattr(np, "clongdouble", np.complex128),
    "clongfloat":    getattr(np, "clongdouble", np.complex128),
    # Object / String / Void
    "object0":       object,
    "str0":          np.str_,
    "bytes0":        np.bytes_,
    "void0":         np.void,
    "unicode_":      np.str_,
    "string_":       np.bytes_,
}
for _alias, _repl in _NP2_COMPAT.items():
    if not hasattr(np, _alias):
        setattr(np, _alias, _repl)  # type: ignore[attr-defined]

from core.schemas import MeshStrategy, TierAttempt
from core.utils.errors import format_missing_dependency_message
from core.utils.logging import get_logger
from core.utils.openfoam_utils import run_openfoam

logger = get_logger(__name__)

TIER_NAME = "tier_hex_classy_blocks"


class TierHexClassyBlocksGenerator:
    """classy_blocks 기반 구조적 Hex 메시 생성기.

    BBox 분석 후 blockMeshDict를 자동 생성하고, snappyHexMesh로 표면 정렬한다.
    단순 형상 (특징선 < 10개)에서 고품질 Hex 메시를 생성한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """Hex classy_blocks 파이프라인을 실행한다.

        Args:
            strategy: 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt.
        """
        t_start = time.monotonic()
        logger.info("tier_hex_classy_blocks_start", preprocessed_path=str(preprocessed_path))

        # 필수 라이브러리 검사
        try:
            import classy_blocks  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier_hex_classy_blocks_import_failed",
                error=str(exc),
                hint="classy_blocks 미설치. pip install classy_blocks",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="classy_blocks",
                    fallback="Tet 메시로 전환",
                    action="pip install classy_blocks",
                    detail=str(exc),
                ),
            )

        # 파일 존재 확인
        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            import trimesh as _trimesh

            # STL 로드
            surf: _trimesh.Trimesh = _trimesh.load(
                str(preprocessed_path), force="mesh"
            )  # type: ignore[assignment]

            # BBox 분석
            bounds = surf.bounds  # (3,) min, (3,) max
            bbox_min, bbox_max = bounds[0], bounds[1]
            bbox_center = (bbox_min + bbox_max) / 2
            bbox_size = bbox_max - bbox_min

            logger.info(
                "tier_hex_classy_blocks_geometry_analysis",
                bbox_min=bbox_min.tolist(),
                bbox_max=bbox_max.tolist(),
                bbox_size=bbox_size.tolist(),
            )

            # blockMeshDict 생성
            params = strategy.tier_specific_params
            target_cell_size = strategy.surface_mesh.target_cell_size
            num_divisions = self._estimate_divisions(bbox_size, target_cell_size)

            logger.info(
                "tier_hex_classy_blocks_blockmesh",
                target_cell_size=target_cell_size,
                num_divisions=num_divisions,
            )

            blockmesh_dict_path = self._generate_blockmesh_dict(
                case_dir, bbox_min, bbox_max, num_divisions
            )

            # blockMesh 실행
            self._run_blockmesh(case_dir)

            # snappyHexMesh 실행 (표면 정렬)
            self._run_snappyhexmesh(case_dir, preprocessed_path, strategy)

            elapsed = time.monotonic() - t_start
            logger.info("tier_hex_classy_blocks_success", elapsed=elapsed)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_hex_classy_blocks_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier Hex (classy_blocks) 실행 실패: {exc}",
            )

    def _estimate_divisions(
        self, bbox_size: npt.NDArray[Any], target_cell_size: float
    ) -> tuple[int, int, int]:
        """목표 셀 크기를 기반으로 각 축의 분할 수를 추정한다.

        Args:
            bbox_size: (3,) BBox 크기.
            target_cell_size: 목표 셀 크기.

        Returns:
            (nx, ny, nz) 각 축의 분할 수.
        """
        divisions = np.maximum(np.ceil(bbox_size / target_cell_size), 2).astype(int)
        # 너무 커지지 않도록 제한 (Draft는 ~20, Standard는 ~50, Fine는 ~100)
        max_divisions = 100
        divisions = np.minimum(divisions, max_divisions)
        return tuple(divisions)

    def _generate_blockmesh_dict(
        self,
        case_dir: Path,
        bbox_min: npt.NDArray[Any],
        bbox_max: npt.NDArray[Any],
        num_divisions: tuple[int, int, int],
    ) -> Path:
        """classy_blocks를 사용하여 blockMeshDict.py를 생성한다.

        Args:
            case_dir: OpenFOAM 케이스 디렉터리.
            bbox_min: BBox 최소값 (3,).
            bbox_max: BBox 최대값 (3,).
            num_divisions: 각 축의 분할 수 (3,).

        Returns:
            생성된 blockMeshDict.py 경로.
        """
        try:
            from classy_blocks.construct import construct_mesh
            from classy_blocks.block import Block
            from classy_blocks.edge import Line

            # BBox를 기반으로 단일 블록 생성
            x_min, y_min, z_min = bbox_min
            x_max, y_max, z_max = bbox_max
            nx, ny, nz = num_divisions

            # 8개 코너 정점 정의
            v0 = [x_min, y_min, z_min]
            v1 = [x_max, y_min, z_min]
            v2 = [x_max, y_max, z_min]
            v3 = [x_min, y_max, z_min]
            v4 = [x_min, y_min, z_max]
            v5 = [x_max, y_min, z_max]
            v6 = [x_max, y_max, z_max]
            v7 = [x_min, y_max, z_max]

            # 단일 블록 생성 (직육면체)
            block = Block(
                v0, v1, v2, v3,
                v4, v5, v6, v7,
                [nx, ny, nz],
            )

            # Mesh 구성
            mesh = construct_mesh(
                [block],
                boundary_name_format="boundary_{}",
                face_name_format="face_{}",
            )

            # blockMeshDict.py 생성
            system_dir = case_dir / "system"
            system_dir.mkdir(parents=True, exist_ok=True)

            blockmesh_dict_path = system_dir / "blockMeshDict"
            mesh.write(str(blockmesh_dict_path))

            logger.info("blockmesh_dict_generated", path=str(blockmesh_dict_path))
            return blockmesh_dict_path

        except Exception as exc:
            logger.warning("blockmesh_dict_generation_failed", error=str(exc))
            # Fallback: 간단한 텍스트 blockMeshDict 생성
            return self._generate_simple_blockmesh_dict(
                case_dir, bbox_min, bbox_max, num_divisions
            )

    def _generate_simple_blockmesh_dict(
        self,
        case_dir: Path,
        bbox_min: npt.NDArray[Any],
        bbox_max: npt.NDArray[Any],
        num_divisions: tuple[int, int, int],
    ) -> Path:
        """간단한 텍스트 기반 blockMeshDict를 생성한다 (classy_blocks 미사용).

        Args:
            case_dir: OpenFOAM 케이스 디렉터리.
            bbox_min, bbox_max: BBox 범위.
            num_divisions: 분할 수.

        Returns:
            blockMeshDict 파일 경로.
        """
        x_min, y_min, z_min = bbox_min
        x_max, y_max, z_max = bbox_max
        nx, ny, nz = num_divisions

        # 간단한 blockMeshDict 콘텐츠
        content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      blockMeshDict;
}}

convertToMeters 1.0;

vertices
(
    ({x_min} {y_min} {z_min})
    ({x_max} {y_min} {z_min})
    ({x_max} {y_max} {z_min})
    ({x_min} {y_max} {z_min})
    ({x_min} {y_min} {z_max})
    ({x_max} {y_min} {z_max})
    ({x_max} {y_max} {z_max})
    ({x_min} {y_max} {z_max})
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    minX
    {{
        type wall;
        faces
        (
            (0 4 7 3)
        );
    }}
    maxX
    {{
        type wall;
        faces
        (
            (1 2 6 5)
        );
    }}
    minY
    {{
        type wall;
        faces
        (
            (0 1 5 4)
        );
    }}
    maxY
    {{
        type wall;
        faces
        (
            (3 7 6 2)
        );
    }}
    minZ
    {{
        type wall;
        faces
        (
            (0 3 2 1)
        );
    }}
    maxZ
    {{
        type wall;
        faces
        (
            (4 5 6 7)
        );
    }}
);

mergePatchPairs
(
);
"""

        system_dir = case_dir / "system"
        system_dir.mkdir(parents=True, exist_ok=True)
        blockmesh_dict_path = system_dir / "blockMeshDict"

        blockmesh_dict_path.write_text(content)
        logger.info("simple_blockmesh_dict_generated", path=str(blockmesh_dict_path))

        return blockmesh_dict_path

    def _run_blockmesh(self, case_dir: Path) -> None:
        """blockMesh를 실행한다.

        Args:
            case_dir: OpenFOAM 케이스 디렉터리.
        """
        # OpenFOAM은 controlDict 없이 blockMesh를 실행하면 에러
        system_dir = case_dir / "system"
        system_dir.mkdir(parents=True, exist_ok=True)
        control_dict = system_dir / "controlDict"
        if not control_dict.exists():
            control_dict.write_text(
                'FoamFile { version 2.0; format ascii; class dictionary; '
                'location "system"; object controlDict; }\n'
                'application blockMesh;\nstartFrom startTime;\nstartTime 0;\n'
                'stopAt endTime;\nendTime 1;\ndeltaT 1;\n'
                'writeControl timeStep;\nwriteInterval 1;\n'
            )

        try:
            logger.info("blockmesh_running", case_dir=str(case_dir))
            run_openfoam("blockMesh", case_dir)
            logger.info("blockmesh_success")
        except Exception as exc:
            logger.warning("blockmesh_failed", error=str(exc))
            raise RuntimeError(f"blockMesh 실행 실패: {exc}")

    def _run_snappyhexmesh(
        self,
        case_dir: Path,
        stl_path: Path,
        strategy: MeshStrategy,
    ) -> None:
        """snappyHexMesh를 실행하여 표면을 정렬한다.

        Args:
            case_dir: OpenFOAM 케이스 디렉터리.
            stl_path: 표면 STL 파일 경로.
            strategy: 메쉬 전략.
        """
        try:
            # triSurface 디렉터리에 STL 복사
            tri_surface_dir = case_dir / "constant" / "triSurface"
            tri_surface_dir.mkdir(parents=True, exist_ok=True)

            surf_name = "surface.stl"
            shutil.copy(str(stl_path), str(tri_surface_dir / surf_name))
            logger.info("stl_copied_to_trisurface", path=str(tri_surface_dir / surf_name))

            # snappyHexMeshDict 생성
            self._generate_snappyhexmesh_dict(case_dir, surf_name, strategy)

            # snappyHexMesh 실행
            logger.info("snappyhexmesh_running", case_dir=str(case_dir))
            run_openfoam("snappyHexMesh", case_dir, args=["-overwrite"])
            logger.info("snappyhexmesh_success")

        except Exception as exc:
            logger.warning("snappyhexmesh_failed", error=str(exc))
            # snappyHexMesh 실패해도 blockMesh 결과는 사용 가능

    def _generate_snappyhexmesh_dict(
        self,
        case_dir: Path,
        stl_name: str,
        strategy: MeshStrategy,
    ) -> Path:
        """snappyHexMeshDict를 생성한다.

        Args:
            case_dir: OpenFOAM 케이스 디렉터리.
            stl_name: triSurface의 STL 파일 이름.
            strategy: 메쉬 전략.

        Returns:
            생성된 snappyHexMeshDict 경로.
        """
        # 기본 snappyHexMeshDict (최소 설정)
        content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      snappyHexMeshDict;
}}

castellatedMesh true;
snap            true;
addLayers       false;

geometry
{{
    surface.stl
    {{
        type triSurfaceMesh;
        file "{stl_name}";
    }}
}};

castellatedMeshControls
{{
    maxLocalCells 100000;
    maxGlobalCells 200000;
    minRefinementCells 0;
    nCellsBetweenLevels 3;

    features
    (
    );

    refinementSurfaces
    {{
        "surface.stl"
        {{
            level (1 1);
            patchType wall;
        }}
    }};

    resolveFeatureAngle 30;

    refinementRegions
    (
    );

    locationInMesh (0 0 0);
}};

snapControls
{{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 5;
}};

addLayersControls
{{
    relativeSizes true;
    layers
    (
    );
    expansionRatio 1.0;
    finalLayerThickness 0.3;
    minThickness 0.1;
}};

meshQualityControls
{{
    maxNonOrtho 65;
    maxBoundarySkewness 20;
    maxInternalSkewness 15;
    maxConcave 80;
    minFlatness 0.5;
    minVol 1e-13;
    minArea -1;
    minTwist 0.05;
    minDeterminant 0.001;
    minFaceWeight 0.05;
    minVolRatio 0.1;
    minTriangleTwist -1;
    nSmoothScale 4;
    errorReduction 0.75;
}};

writeFlags
(
);

mergeTolerance 1e-6;
"""

        system_dir = case_dir / "system"
        system_dir.mkdir(parents=True, exist_ok=True)
        snappy_dict_path = system_dir / "snappyHexMeshDict"

        snappy_dict_path.write_text(content)
        logger.info("snappyhexmesh_dict_generated", path=str(snappy_dict_path))

        return snappy_dict_path
