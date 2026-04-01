"""Tier 1: snappyHexMesh 메쉬 생성기."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from core.generator.openfoam_writer import OpenFOAMWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger
from core.utils.openfoam_utils import OpenFOAMError, run_openfoam

logger = get_logger(__name__)

TIER_NAME = "tier1_snappy"


def generate_block_mesh_dict(strategy: MeshStrategy) -> dict:
    """blockMeshDict 내용을 Python dict로 생성한다.

    도메인 설정에 따라 8개 꼭짓점과 블록 분할 수를 계산한다.

    Args:
        strategy: 메쉬 전략 (domain 설정 포함).

    Returns:
        blockMeshDict 구조를 담은 dict. vertices/blocks 키를 포함한다.
    """
    domain = strategy.domain
    mn = domain.min
    mx = domain.max
    base = domain.base_cell_size

    # 분할 수 계산 (최소 1)
    nx = max(1, int((mx[0] - mn[0]) / base))
    ny = max(1, int((mx[1] - mn[1]) / base))
    nz = max(1, int((mx[2] - mn[2]) / base))

    # 8개 꼭짓점 (아래 4개, 위 4개)
    vertices = [
        [mn[0], mn[1], mn[2]],  # 0
        [mx[0], mn[1], mn[2]],  # 1
        [mx[0], mx[1], mn[2]],  # 2
        [mn[0], mx[1], mn[2]],  # 3
        [mn[0], mn[1], mx[2]],  # 4
        [mx[0], mn[1], mx[2]],  # 5
        [mx[0], mx[1], mx[2]],  # 6
        [mn[0], mx[1], mx[2]],  # 7
    ]

    return {
        "scale": 1,
        "vertices": vertices,
        "blocks": f"hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)",
        "edges": [],
        "boundary": {
            "inlet": {
                "type": "patch",
                "faces": [[0, 4, 7, 3]],
            },
            "outlet": {
                "type": "patch",
                "faces": [[1, 2, 6, 5]],
            },
            "walls": {
                "type": "wall",
                "faces": [
                    [0, 1, 5, 4],
                    [3, 7, 6, 2],
                    [0, 3, 2, 1],
                    [4, 5, 6, 7],
                ],
            },
        },
    }


def generate_snappy_dict(strategy: MeshStrategy) -> dict:
    """snappyHexMeshDict 내용을 Python dict로 생성한다.

    Args:
        strategy: 메쉬 전략 (surface_mesh, boundary_layers, quality_targets 포함).

    Returns:
        snappyHexMeshDict 구조를 담은 dict.
        castellatedMeshControls/snapControls/addLayersControls 키를 포함한다.
    """
    params = strategy.tier_specific_params
    sm = strategy.surface_mesh
    bl = strategy.boundary_layers
    qt = strategy.quality_targets
    domain = strategy.domain

    return {
        "castellatedMesh": True,
        "snap": True,
        "addLayers": bl.enabled,
        "castellatedMeshControls": {
            "maxLocalCells": params.get("snappy_max_local_cells", 1_000_000),
            "maxGlobalCells": params.get("snappy_max_global_cells", 10_000_000),
            "minRefinementCells": params.get("snappy_min_refinement_cells", 10),
            "nCellsBetweenLevels": params.get("snappy_n_cells_between_levels", 3),
            "resolveFeatureAngle": sm.feature_angle,
            "locationInMesh": domain.location_in_mesh,
            "features": [
                {
                    "file": "surface.eMesh",
                    "level": sm.feature_extract_level,
                }
            ],
            "refinementSurfaces": {
                "surface": {
                    "level": params.get("snappy_castellated_level", [1, 2]),
                }
            },
            "refinementRegions": {},
        },
        "snapControls": {
            "nSmoothPatch": params.get("snappy_snap_smooth_patch", 3),
            "tolerance": params.get("snappy_snap_tolerance", 2.0),
            "nSolveIter": params.get("snappy_snap_iterations", 30),
            "nRelaxIter": params.get("snappy_snap_relax_iter", 5),
            "nFeatureSnapIter": params.get("snappy_feature_snap_iter", 10),
            "implicitFeatureSnap": False,
            "explicitFeatureSnap": True,
            "multiRegionFeatureSnap": False,
        },
        "addLayersControls": {
            "relativeSizes": True,
            "layers": {
                "surface": {
                    "nSurfaceLayers": bl.num_layers,
                }
            },
            "firstLayerThickness": bl.first_layer_thickness,
            "expansionRatio": bl.growth_ratio,
            "minThickness": bl.min_thickness_ratio,
            "featureAngle": bl.feature_angle,
            "maxFaceThicknessRatio": 0.5,
            "nGrow": 0,
            "nSmoothSurfaceNormals": 1,
            "nSmoothNormals": 3,
            "nSmoothThickness": 10,
            "nRelaxIter": 5,
            "nLayerIter": 50,
            "nRelaxedIter": 20,
        },
        "meshQualityControls": {
            "maxNonOrtho": qt.max_non_orthogonality,
            "maxBoundarySkewness": 20,
            "maxInternalSkewness": qt.max_skewness,
            "maxConcave": 80,
            "minVol": 1e-30,
            "minArea": -1,
            "minDeterminant": qt.min_determinant,
            "minFaceWeight": 0.05,
        },
        "debug": 0,
        "mergeTolerance": 1e-6,
    }


def _generate_surface_feature_extract_dict(stl_name: str) -> dict:
    """surfaceFeatureExtractDict를 생성한다."""
    return {
        stl_name: {
            "extractionMethod": "extractFromSurface",
            "extractFromSurfaceCoeffs": {
                "includedAngle": 150,
            },
            "subsetFeatures": {
                "nonManifoldEdges": "yes",
                "openEdges": "yes",
            },
            "writeObj": "yes",
        }
    }


class Tier1SnappyGenerator:
    """snappyHexMesh 기반 Hex-dominant 메쉬 생성기.

    3단계 파이프라인: blockMesh → surfaceFeatureExtract → snappyHexMesh
    """

    def __init__(self) -> None:
        self._writer = OpenFOAMWriter()

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """Tier 1 snappyHexMesh 파이프라인을 실행한다.

        Args:
            strategy: 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt.
        """
        t_start = time.monotonic()
        steps = []
        logger.info("tier1_snappy_start", case_dir=str(case_dir))

        try:
            # 케이스 구조 생성
            self._writer.ensure_case_structure(case_dir)

            # STL 복사
            surface_stl = case_dir / "constant" / "triSurface" / "surface.stl"
            if preprocessed_path.exists():
                shutil.copy(str(preprocessed_path), str(surface_stl))
                logger.info("stl_copied", src=str(preprocessed_path), dst=str(surface_stl))

            # Dict 파일 생성
            self._write_dicts(strategy, case_dir)

            # Step 1: blockMesh
            t_step = time.monotonic()
            try:
                run_openfoam("blockMesh", case_dir)
                step_elapsed = time.monotonic() - t_step
                steps.append({"name": "blockMesh", "status": "success", "time": step_elapsed})
                logger.info("blockmesh_success", elapsed=step_elapsed)
            except OpenFOAMError as exc:
                step_elapsed = time.monotonic() - t_step
                steps.append({"name": "blockMesh", "status": "failed", "time": step_elapsed})
                elapsed = time.monotonic() - t_start
                logger.warning("blockmesh_failed", error=str(exc))
                from core.schemas import GeneratorStep
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=elapsed,
                    steps=[GeneratorStep(**s) for s in steps],
                    error_message=f"blockMesh 실패: {exc}",
                )

            # Step 2: surfaceFeatureExtract
            t_step = time.monotonic()
            try:
                run_openfoam("surfaceFeatureExtract", case_dir)
                step_elapsed = time.monotonic() - t_step
                steps.append({"name": "surfaceFeatureExtract", "status": "success", "time": step_elapsed})
                logger.info("surface_feature_extract_success", elapsed=step_elapsed)
            except OpenFOAMError as exc:
                step_elapsed = time.monotonic() - t_step
                steps.append({"name": "surfaceFeatureExtract", "status": "failed", "time": step_elapsed})
                elapsed = time.monotonic() - t_start
                logger.warning("surface_feature_extract_failed", error=str(exc))
                from core.schemas import GeneratorStep
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=elapsed,
                    steps=[GeneratorStep(**s) for s in steps],
                    error_message=f"surfaceFeatureExtract 실패: {exc}",
                )

            # Step 3: snappyHexMesh
            t_step = time.monotonic()
            try:
                run_openfoam("snappyHexMesh", case_dir, args=["-overwrite"])
                step_elapsed = time.monotonic() - t_step
                steps.append({"name": "snappyHexMesh", "status": "success", "time": step_elapsed})
                logger.info("snappy_success", elapsed=step_elapsed)
            except OpenFOAMError as exc:
                step_elapsed = time.monotonic() - t_step
                steps.append({"name": "snappyHexMesh", "status": "failed", "time": step_elapsed})
                elapsed = time.monotonic() - t_start
                logger.warning("snappy_failed", error=str(exc))
                from core.schemas import GeneratorStep
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=elapsed,
                    steps=[GeneratorStep(**s) for s in steps],
                    error_message=f"snappyHexMesh 실패: {exc}",
                )

            elapsed = time.monotonic() - t_start
            from core.schemas import GeneratorStep
            logger.info("tier1_snappy_success", elapsed=elapsed)
            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
                steps=[GeneratorStep(**s) for s in steps],
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier1_snappy_unexpected_error", error=str(exc))
            from core.schemas import GeneratorStep
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                steps=[GeneratorStep(**s) for s in steps],
                error_message=f"Tier 1 예상치 못한 오류: {exc}",
            )

    def _write_dicts(self, strategy: MeshStrategy, case_dir: Path) -> None:
        """모든 필요한 Dict 파일을 작성한다."""
        system_dir = case_dir / "system"

        # controlDict
        self._writer.write_control_dict(case_dir, application="snappyHexMesh")

        # fvSchemes, fvSolution
        self._writer.write_fv_schemes(case_dir)
        self._writer.write_fv_solution(case_dir)

        # blockMeshDict
        bmd = generate_block_mesh_dict(strategy)
        bmd_path = system_dir / "blockMeshDict"
        bmd_path.write_text(self._render_block_mesh_dict(bmd))
        logger.info("wrote_block_mesh_dict", path=str(bmd_path))

        # snappyHexMeshDict
        snappy = generate_snappy_dict(strategy)
        snappy_path = system_dir / "snappyHexMeshDict"
        self._writer.write_foam_dict(
            snappy_path, snappy,
            location="system", object_name="snappyHexMeshDict"
        )

        # surfaceFeatureExtractDict
        sfe_dict = _generate_surface_feature_extract_dict("surface.stl")
        sfe_path = system_dir / "surfaceFeatureExtractDict"
        self._writer.write_foam_dict(
            sfe_path, sfe_dict,
            location="system", object_name="surfaceFeatureExtractDict"
        )

    def _render_block_mesh_dict(self, bmd: dict) -> str:
        """blockMeshDict를 OpenFOAM 형식 문자열로 렌더링한다."""
        from core.generator.openfoam_writer import _foam_header
        header = _foam_header(
            foam_class="dictionary",
            location="system",
            object_name="blockMeshDict",
        )
        lines = [header]
        lines.append(f"scale    {bmd['scale']};\n")

        lines.append("vertices")
        lines.append("(")
        for v in bmd["vertices"]:
            lines.append(f"    ({v[0]} {v[1]} {v[2]})")
        lines.append(");\n")

        lines.append("blocks")
        lines.append("(")
        lines.append(f"    {bmd['blocks']}")
        lines.append(");\n")

        lines.append("edges\n(\n);\n")

        lines.append("boundary")
        lines.append("(")
        for patch_name, patch_data in bmd["boundary"].items():
            lines.append(f"    {patch_name}")
            lines.append("    {")
            lines.append(f"        type {patch_data['type']};")
            lines.append("        faces")
            lines.append("        (")
            for face in patch_data["faces"]:
                lines.append(f"            ({' '.join(str(i) for i in face)})")
            lines.append("        );")
            lines.append("    }")
        lines.append(");\n")

        lines.append("// ************************************************************************* //")
        return "\n".join(lines)
