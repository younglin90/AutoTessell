"""Generator 모듈 테스트 — 외부 도구(OpenFOAM/Netgen/TetWild) 없이 통과."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    ExecutionSummary,
    GeneratorLog,
    MeshStrategy,
    QualityLevel,
    QualityTargets,
    SurfaceMeshConfig,
    TierAttempt,
)

# ---------------------------------------------------------------------------
# 공용 픽스처
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def mesh_strategy() -> MeshStrategy:
    """기본 MeshStrategy 픽스처."""
    return MeshStrategy(
        strategy_version=1,
        iteration=1,
        selected_tier="tier1_snappy",
        fallback_tiers=["tier15_cfmesh", "tier2_tetwild"],
        flow_type="external",
        domain=DomainConfig(
            type="box",
            min=[-1.0, -1.0, -1.0],
            max=[1.0, 1.0, 1.0],
            base_cell_size=0.1,
            location_in_mesh=[0.0, 0.0, 0.0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="preprocessed.stl",
            target_cell_size=0.05,
            min_cell_size=0.01,
            feature_angle=150.0,
            feature_extract_level=1,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=True,
            num_layers=3,
            first_layer_thickness=0.001,
            growth_ratio=1.2,
            max_total_thickness=0.01,
            min_thickness_ratio=0.1,
            feature_angle=130.0,
        ),
        quality_targets=QualityTargets(
            max_non_orthogonality=65.0,
            max_skewness=4.0,
            max_aspect_ratio=100.0,
            min_determinant=0.001,
            target_y_plus=1.0,
        ),
        tier_specific_params={
            "snappy_castellated_level": [1, 2],
            "snappy_snap_tolerance": 2.0,
            "snappy_snap_iterations": 30,
        },
    )


@pytest.fixture()
def dummy_stl(tmp_path: Path) -> Path:
    """더미 STL 파일."""
    stl_file = tmp_path / "dummy.stl"
    stl_file.write_text("solid dummy\nendsolid dummy\n")
    return stl_file


# ---------------------------------------------------------------------------
# OpenFOAMWriter 테스트
# ---------------------------------------------------------------------------


class TestOpenFOAMWriter:
    def test_openfoam_writer_creates_dirs(self, tmp_path: Path) -> None:
        """ensure_case_structure → 필수 디렉터리 생성 확인."""
        from core.generator.openfoam_writer import OpenFOAMWriter

        writer = OpenFOAMWriter()
        writer.ensure_case_structure(tmp_path)

        assert (tmp_path / "constant" / "polyMesh").is_dir()
        assert (tmp_path / "constant" / "triSurface").is_dir()
        assert (tmp_path / "system").is_dir()

    def test_openfoam_writer_control_dict(self, tmp_path: Path) -> None:
        """write_control_dict → system/controlDict 파일 생성 확인."""
        from core.generator.openfoam_writer import OpenFOAMWriter

        writer = OpenFOAMWriter()
        writer.ensure_case_structure(tmp_path)
        writer.write_control_dict(tmp_path, application="simpleFoam")

        control_dict = tmp_path / "system" / "controlDict"
        assert control_dict.exists()
        content = control_dict.read_text()
        assert "simpleFoam" in content
        assert "FoamFile" in content

    def test_openfoam_writer_fv_schemes(self, tmp_path: Path) -> None:
        """write_fv_schemes → system/fvSchemes 파일 생성 확인."""
        from core.generator.openfoam_writer import OpenFOAMWriter

        writer = OpenFOAMWriter()
        writer.ensure_case_structure(tmp_path)
        writer.write_fv_schemes(tmp_path)

        fv_schemes = tmp_path / "system" / "fvSchemes"
        assert fv_schemes.exists()
        content = fv_schemes.read_text()
        assert "ddtSchemes" in content
        assert "gradSchemes" in content

    def test_openfoam_writer_fv_solution(self, tmp_path: Path) -> None:
        """write_fv_solution → system/fvSolution 파일 생성 확인."""
        from core.generator.openfoam_writer import OpenFOAMWriter

        writer = OpenFOAMWriter()
        writer.ensure_case_structure(tmp_path)
        writer.write_fv_solution(tmp_path)

        fv_solution = tmp_path / "system" / "fvSolution"
        assert fv_solution.exists()
        content = fv_solution.read_text()
        assert "solvers" in content
        assert "SIMPLE" in content


# ---------------------------------------------------------------------------
# Dict 생성 테스트
# ---------------------------------------------------------------------------


class TestDictGeneration:
    def test_block_mesh_dict_keys(self, mesh_strategy: MeshStrategy) -> None:
        """generate_block_mesh_dict → vertices/blocks 키 포함 확인."""
        from core.generator.tier1_snappy import generate_block_mesh_dict

        bmd = generate_block_mesh_dict(mesh_strategy)

        assert "vertices" in bmd
        assert "blocks" in bmd
        assert len(bmd["vertices"]) == 8  # 8 꼭짓점
        assert isinstance(bmd["blocks"], str)
        assert "hex" in bmd["blocks"]

    def test_block_mesh_dict_cell_count(self, mesh_strategy: MeshStrategy) -> None:
        """generate_block_mesh_dict → base_cell_size 기반 분할 수 계산 확인."""
        from core.generator.tier1_snappy import generate_block_mesh_dict

        bmd = generate_block_mesh_dict(mesh_strategy)
        # domain: [-1,1]^3, base_cell_size=0.1 → 20x20x20
        assert "(20 20 20)" in bmd["blocks"]

    def test_snappy_dict_keys(self, mesh_strategy: MeshStrategy) -> None:
        """generate_snappy_dict → castellatedMeshControls/snapControls/addLayersControls 키 포함 확인."""
        from core.generator.tier1_snappy import generate_snappy_dict

        snappy = generate_snappy_dict(mesh_strategy)

        assert "castellatedMeshControls" in snappy
        assert "snapControls" in snappy
        assert "addLayersControls" in snappy
        assert "meshQualityControls" in snappy

    def test_snappy_dict_castellated_controls(self, mesh_strategy: MeshStrategy) -> None:
        """castellatedMeshControls 세부 키 확인."""
        from core.generator.tier1_snappy import generate_snappy_dict

        snappy = generate_snappy_dict(mesh_strategy)
        cc = snappy["castellatedMeshControls"]

        assert "maxLocalCells" in cc
        assert "maxGlobalCells" in cc
        assert "locationInMesh" in cc
        assert "features" in cc
        assert "refinementSurfaces" in cc

    def test_snappy_dict_snap_controls(self, mesh_strategy: MeshStrategy) -> None:
        """snapControls 세부 키 확인."""
        from core.generator.tier1_snappy import generate_snappy_dict

        snappy = generate_snappy_dict(mesh_strategy)
        sc = snappy["snapControls"]

        assert "tolerance" in sc
        assert "nSolveIter" in sc
        # strategy의 tier_specific_params 값 반영 확인
        assert sc["tolerance"] == 2.0
        assert sc["nSolveIter"] == 30

    def test_snappy_geometry_name_is_safe_word(self, mesh_strategy: MeshStrategy) -> None:
        """geometry.name은 OpenFOAM word 제약을 만족하는 고정 식별자여야 한다."""
        from core.generator.tier1_snappy import generate_snappy_dict

        mesh_strategy.surface_mesh.input_file = "/tmp/foo/bar/preprocessed.stl"
        snappy = generate_snappy_dict(mesh_strategy)
        geom = snappy["geometry"]["surface.stl"]
        assert geom["name"] == "surface"

    def test_cfmesh_dict_keys(self, mesh_strategy: MeshStrategy) -> None:
        """generate_cfmesh_dict → surfaceFile/maxCellSize 키 포함 확인."""
        from core.generator.tier15_cfmesh import generate_cfmesh_dict

        cf = generate_cfmesh_dict(mesh_strategy)

        assert "surfaceFile" in cf
        assert "maxCellSize" in cf
        assert "minCellSize" in cf
        assert "boundaryCellSize" in cf

    def test_cfmesh_dict_surface_file(self, mesh_strategy: MeshStrategy) -> None:
        """generate_cfmesh_dict → surfaceFile 경로 확인."""
        from core.generator.tier15_cfmesh import generate_cfmesh_dict

        cf = generate_cfmesh_dict(mesh_strategy)
        assert "surface.stl" in cf["surfaceFile"]

    def test_cfmesh_dict_boundary_layers(self, mesh_strategy: MeshStrategy) -> None:
        """boundary_layers.enabled=True → boundaryLayers 키 생성 확인."""
        from core.generator.tier15_cfmesh import generate_cfmesh_dict

        cf = generate_cfmesh_dict(mesh_strategy)
        assert "boundaryLayers" in cf
        bl = cf["boundaryLayers"]
        assert bl["nLayers"] == 3
        assert bl["thicknessRatio"] == 1.2

    def test_cfmesh_dict_no_boundary_layers(self, mesh_strategy: MeshStrategy) -> None:
        """boundary_layers.enabled=False → boundaryLayers 키 없음 확인."""
        from core.generator.tier15_cfmesh import generate_cfmesh_dict

        mesh_strategy.boundary_layers.enabled = False
        cf = generate_cfmesh_dict(mesh_strategy)
        assert "boundaryLayers" not in cf

    def test_cfmesh_max_cell_size_override(self, mesh_strategy: MeshStrategy) -> None:
        """tier_specific_params.cfmesh_max_cell_size 우선 적용 확인."""
        from core.generator.tier15_cfmesh import generate_cfmesh_dict

        mesh_strategy.tier_specific_params["cfmesh_max_cell_size"] = 0.5
        cf = generate_cfmesh_dict(mesh_strategy)
        assert cf["maxCellSize"] == 0.5

    def test_cfmesh_max_cell_size_default(self, mesh_strategy: MeshStrategy) -> None:
        """cfmesh_max_cell_size 미지정 → target_cell_size * 4 확인."""
        from core.generator.tier15_cfmesh import generate_cfmesh_dict

        mesh_strategy.tier_specific_params.pop("cfmesh_max_cell_size", None)
        cf = generate_cfmesh_dict(mesh_strategy)
        expected = mesh_strategy.surface_mesh.target_cell_size * 4
        assert cf["maxCellSize"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Tier graceful fail 테스트
# ---------------------------------------------------------------------------


class TestTierGracefulFail:
    def test_tier0_fails_gracefully(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """Tier0 모듈(auto_tessell_core/tessell_mesh) 모두 없으면 실패 반환."""
        from core.generator.tier0_core import Tier0CoreGenerator

        generator = Tier0CoreGenerator()
        # Tier0 C++ 모듈이 모두 없는 환경에서 실행
        with patch.dict("sys.modules", {"auto_tessell_core": None, "tessell_mesh": None}):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier0_core"
        assert attempt.error_message is not None
        assert len(attempt.error_message) > 0
        assert attempt.time_seconds >= 0.0

    def test_tier05_fails_gracefully(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """netgen 없음 → TierAttempt(status='failed') 반환."""
        from core.generator.tier05_netgen import Tier05NetgenGenerator

        generator = Tier05NetgenGenerator()
        with patch.dict("sys.modules", {"netgen": None, "netgen.meshing": None, "netgen.occ": None}):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier05_netgen"
        assert attempt.error_message is not None
        assert attempt.time_seconds >= 0.0

    def test_tier1_fails_gracefully(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """OpenFOAM 없음 → blockMesh 실패 → TierAttempt(status='failed') 반환."""
        from core.generator.tier1_snappy import Tier1SnappyGenerator
        from core.utils.openfoam_utils import OpenFOAMError

        generator = Tier1SnappyGenerator()
        # run_openfoam를 OpenFOAMError를 발생시키는 mock으로 패치
        with patch(
            "core.generator.tier1_snappy.run_openfoam",
            side_effect=OpenFOAMError("blockMesh", 1, "", "blockMesh not found"),
        ):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier1_snappy"
        assert attempt.error_message is not None
        assert "blockMesh" in attempt.error_message

    def test_tier15_fails_gracefully(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """OpenFOAM 없음 → cartesianMesh 실패 → TierAttempt(status='failed') 반환."""
        from core.generator.tier15_cfmesh import Tier15CfMeshGenerator
        from core.utils.openfoam_utils import OpenFOAMError

        generator = Tier15CfMeshGenerator()
        with patch(
            "core.generator.tier15_cfmesh.run_openfoam",
            side_effect=OpenFOAMError("cartesianMesh", 1, "", "cartesianMesh not found"),
        ):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier15_cfmesh"
        assert attempt.error_message is not None

    def test_tier2_fails_gracefully(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """pytetwild 없음 → TierAttempt(status='failed') 반환."""
        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        generator = Tier2TetWildGenerator()
        with patch.dict("sys.modules", {"pytetwild": None}):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier2_tetwild"
        assert attempt.error_message is not None
        assert attempt.time_seconds >= 0.0

    def test_tier_meshpy_fails_gracefully(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """meshpy 없음 → TierAttempt(status='failed') 반환."""
        meshpy = pytest.importorskip("meshpy", reason="meshpy 미설치 — 스킵")
        _ = meshpy  # silence unused import warning

        from core.generator.tier_meshpy import TierMeshPyGenerator

        generator = TierMeshPyGenerator()
        with patch.dict("sys.modules", {"meshpy": None, "meshpy.tet": None}):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier_meshpy"
        assert attempt.error_message is not None
        assert attempt.time_seconds >= 0.0

    def test_tier_meshpy_import_skip(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """meshpy 미설치 환경에서 import 실패 → graceful fail."""
        from core.generator.tier_meshpy import TierMeshPyGenerator

        generator = TierMeshPyGenerator()
        with patch.dict("sys.modules", {"meshpy": None, "meshpy.tet": None}):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier_meshpy"
        assert "meshpy" in (attempt.error_message or "").lower()

    def test_tier_classy_blocks_no_openfoam(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """OpenFOAM(blockMesh) 없음 → TierAttempt(status='failed') 반환."""
        try:
            import classy_blocks as _classy_blocks
            _ = _classy_blocks
        except (ImportError, AttributeError):
            pytest.skip("classy_blocks 미설치 또는 호환 불가 — 스킵")

        from core.generator.tier_classy_blocks import TierClassyBlocksGenerator

        generator = TierClassyBlocksGenerator()
        with patch("shutil.which", return_value=None):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier_classy_blocks"
        assert attempt.error_message is not None

    def test_tier_classy_blocks_import_skip(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """classy_blocks 미설치 환경에서 import 실패 → graceful fail."""
        from core.generator.tier_classy_blocks import TierClassyBlocksGenerator

        generator = TierClassyBlocksGenerator()
        with patch.dict("sys.modules", {"classy_blocks": None}):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier_classy_blocks"
        assert "classy_blocks" in (attempt.error_message or "").lower()

    def test_tier_jigsaw_import_skip(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """jigsawpy 미설치 환경에서 import 실패 → graceful fail."""
        from core.generator.tier_jigsaw import TierJigsawGenerator

        generator = TierJigsawGenerator()
        with patch.dict("sys.modules", {"jigsawpy": None}):
            attempt = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier_jigsaw"
        assert "jigsawpy" in (attempt.error_message or "").lower()

    def test_tier_jigsaw_missing_file(
        self, mesh_strategy: MeshStrategy, tmp_path: Path
    ) -> None:
        """입력 파일 없음 → TierAttempt(status='failed') 반환."""
        pytest.importorskip("jigsawpy", reason="jigsawpy 미설치 — 스킵")

        from core.generator.tier_jigsaw import TierJigsawGenerator

        generator = TierJigsawGenerator()
        nonexistent = tmp_path / "no_such_file.stl"
        attempt = generator.run(mesh_strategy, nonexistent, tmp_path)

        assert attempt.status == "failed"
        assert attempt.tier == "tier_jigsaw"
        assert attempt.error_message is not None


# ---------------------------------------------------------------------------
# 파이프라인 테스트
# ---------------------------------------------------------------------------


class TestPipeline:
    def _make_failing_tier_run(self, tier_name: str, error_msg: str):
        """특정 Tier가 항상 실패하는 mock run 함수를 반환한다."""
        def _run(strategy, preprocessed_path, case_dir):
            return TierAttempt(
                tier=tier_name,
                status="failed",
                time_seconds=0.01,
                error_message=error_msg,
            )
        return _run

    def test_pipeline_all_fail_returns_log(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """모든 Tier 실패해도 GeneratorLog 반환 (전체 프로세스 중단 금지)."""
        from core.generator.pipeline import MeshGenerator

        generator = MeshGenerator()

        # 모든 Tier를 실패로 mock
        with patch("core.generator.pipeline._run_tier") as mock_run:
            mock_run.side_effect = lambda tier, strategy, path, case: TierAttempt(
                tier=tier,
                status="failed",
                time_seconds=0.01,
                error_message=f"{tier} mock fail",
            )
            log = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert isinstance(log, GeneratorLog)
        assert log.execution_summary is not None
        assert log.execution_summary.total_time_seconds >= 0.0

    def test_pipeline_fallback_order(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """selected_tier 실패 → fallback_tiers 순서대로 시도 확인."""
        from core.generator.pipeline import MeshGenerator, _resolve_tier

        generator = MeshGenerator()
        called_tiers: list[str] = []

        def mock_run_tier(tier, strategy, path, case):
            called_tiers.append(tier)
            return TierAttempt(
                tier=tier,
                status="failed",
                time_seconds=0.01,
                error_message=f"{tier} mock fail",
            )

        with patch("core.generator.pipeline._run_tier", side_effect=mock_run_tier):
            log = generator.run(mesh_strategy, dummy_stl, tmp_path)

        # 호출 순서 확인
        expected_sequence = [
            _resolve_tier("tier1_snappy"),
            _resolve_tier("tier15_cfmesh"),
            _resolve_tier("tier2_tetwild"),
        ]
        assert called_tiers == expected_sequence

    def test_pipeline_stops_on_success(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """첫 Tier 성공 시 이후 Tier는 시도하지 않음 확인."""
        from core.generator.pipeline import MeshGenerator

        generator = MeshGenerator()
        called_tiers: list[str] = []

        def mock_run_tier(tier, strategy, path, case):
            called_tiers.append(tier)
            # 첫 번째(selected_tier)만 성공
            if tier == "tier1_snappy":
                return TierAttempt(
                    tier=tier,
                    status="success",
                    time_seconds=0.01,
                )
            return TierAttempt(
                tier=tier,
                status="failed",
                time_seconds=0.01,
                error_message="should not reach",
            )

        with patch("core.generator.pipeline._run_tier", side_effect=mock_run_tier):
            log = generator.run(mesh_strategy, dummy_stl, tmp_path)

        # selected_tier만 호출되어야 함
        assert called_tiers == ["tier1_snappy"]
        assert log.execution_summary.tiers_attempted[0].status == "success"

    def test_pipeline_fallback_succeeds(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """selected_tier 실패 → 첫 fallback 성공 → 나머지는 시도 안 함 확인."""
        from core.generator.pipeline import MeshGenerator

        generator = MeshGenerator()
        called_tiers: list[str] = []

        def mock_run_tier(tier, strategy, path, case):
            called_tiers.append(tier)
            if tier == "tier15_cfmesh":
                return TierAttempt(tier=tier, status="success", time_seconds=0.01)
            return TierAttempt(
                tier=tier, status="failed", time_seconds=0.01, error_message="mock fail"
            )

        with patch("core.generator.pipeline._run_tier", side_effect=mock_run_tier):
            log = generator.run(mesh_strategy, dummy_stl, tmp_path)

        assert "tier1_snappy" in called_tiers
        assert "tier15_cfmesh" in called_tiers
        assert "tier2_tetwild" not in called_tiers
        # 성공한 attempt 확인
        success_attempts = [a for a in log.execution_summary.tiers_attempted if a.status == "success"]
        assert len(success_attempts) == 1
        assert success_attempts[0].tier == "tier15_cfmesh"

    def test_pipeline_tiers_attempted_recorded(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """실행된 모든 Tier가 tiers_attempted에 기록되는지 확인."""
        from core.generator.pipeline import MeshGenerator

        generator = MeshGenerator()

        with patch("core.generator.pipeline._run_tier") as mock_run:
            mock_run.side_effect = lambda tier, strategy, path, case: TierAttempt(
                tier=tier,
                status="failed",
                time_seconds=0.01,
                error_message="mock fail",
            )
            log = generator.run(mesh_strategy, dummy_stl, tmp_path)

        attempted = log.execution_summary.tiers_attempted
        # selected_tier + 2 fallbacks = 3
        assert len(attempted) == 3
        assert attempted[0].tier == "tier1_snappy"
        assert attempted[1].tier == "tier15_cfmesh"
        assert attempted[2].tier == "tier2_tetwild"

    def test_pipeline_work_dir_cleaned_between_tiers(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """Tier 시도 전 work_dir 초기화 호출 확인."""
        from core.generator import pipeline

        call_count = 0
        original_clean = pipeline._clean_work_dir

        def mock_clean(case_dir):
            nonlocal call_count
            call_count += 1
            original_clean(case_dir)

        with patch("core.generator.pipeline._clean_work_dir", side_effect=mock_clean):
            with patch("core.generator.pipeline._run_tier") as mock_run:
                mock_run.side_effect = lambda tier, strategy, path, case: TierAttempt(
                    tier=tier,
                    status="failed",
                    time_seconds=0.01,
                    error_message="mock fail",
                )
                pipeline.MeshGenerator().run(mesh_strategy, dummy_stl, tmp_path)

        # 3개 Tier 시도 → 3번 clean 호출
        assert call_count == 3


# ---------------------------------------------------------------------------
# GeneratorLog 스키마 테스트
# ---------------------------------------------------------------------------


class TestGeneratorLogSchema:
    def test_generator_log_schema(self) -> None:
        """GeneratorLog Pydantic 검증 — 유효한 데이터로 생성 성공 확인."""
        log = GeneratorLog(
            execution_summary=ExecutionSummary(
                selected_tier="tier1_snappy",
                tiers_attempted=[
                    TierAttempt(
                        tier="tier1_snappy",
                        status="success",
                        time_seconds=142.5,
                    )
                ],
                output_dir="case/constant/polyMesh",
                total_time_seconds=142.5,
            )
        )

        assert log.execution_summary.selected_tier == "tier1_snappy"
        assert len(log.execution_summary.tiers_attempted) == 1
        assert log.execution_summary.tiers_attempted[0].status == "success"
        assert log.execution_summary.total_time_seconds == pytest.approx(142.5)

    def test_generator_log_json_roundtrip(self) -> None:
        """GeneratorLog JSON 직렬화/역직렬화 확인."""
        log = GeneratorLog(
            execution_summary=ExecutionSummary(
                selected_tier="tier0_core",
                tiers_attempted=[
                    TierAttempt(
                        tier="tier0_core",
                        status="failed",
                        time_seconds=0.5,
                        error_message="ImportError: no module named auto_tessell_core",
                    ),
                    TierAttempt(
                        tier="tier05_netgen",
                        status="failed",
                        time_seconds=0.1,
                        error_message="ImportError: no module named netgen",
                    ),
                ],
                output_dir="./case/constant/polyMesh",
                total_time_seconds=0.6,
            )
        )

        json_str = log.model_dump_json(indent=2)
        restored = GeneratorLog.model_validate_json(json_str)

        assert restored.execution_summary.selected_tier == "tier0_core"
        assert len(restored.execution_summary.tiers_attempted) == 2
        assert restored.execution_summary.tiers_attempted[0].status == "failed"
        assert restored.execution_summary.tiers_attempted[1].tier == "tier05_netgen"

    def test_generator_log_from_fixture(self) -> None:
        """fixtures/mesh_strategy.json 로드 및 MeshStrategy 검증."""
        strategy_path = FIXTURES_DIR / "mesh_strategy.json"
        assert strategy_path.exists(), f"픽스처 파일 없음: {strategy_path}"

        strategy = MeshStrategy.model_validate_json(strategy_path.read_text())
        assert strategy.selected_tier == "tier1_snappy"
        assert "tier15_cfmesh" in strategy.fallback_tiers
        assert strategy.domain.base_cell_size == pytest.approx(0.1)

    def test_tier_attempt_schema_validation(self) -> None:
        """TierAttempt Pydantic 필드 검증."""
        # 필수 필드 누락 시 ValidationError
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TierAttempt(status="success", time_seconds=1.0)  # tier 필드 누락

    def test_generator_log_no_attempts(self) -> None:
        """tiers_attempted가 빈 리스트인 경우도 유효."""
        log = GeneratorLog(
            execution_summary=ExecutionSummary(
                selected_tier="tier1_snappy",
                tiers_attempted=[],
                output_dir="",
                total_time_seconds=0.0,
            )
        )
        assert log.execution_summary.tiers_attempted == []


# ---------------------------------------------------------------------------
# OpenFOAMError 테스트
# ---------------------------------------------------------------------------


class TestOpenFOAMError:
    def test_openfoam_error_attributes(self) -> None:
        """OpenFOAMError 속성 확인."""
        from core.utils.openfoam_utils import OpenFOAMError

        err = OpenFOAMError(
            utility="blockMesh",
            returncode=1,
            stdout="",
            stderr="command not found: blockMesh",
        )

        assert err.utility == "blockMesh"
        assert err.returncode == 1
        assert "blockMesh" in str(err)

    def test_openfoam_error_is_runtime_error(self) -> None:
        """OpenFOAMError가 RuntimeError 상속 확인."""
        from core.utils.openfoam_utils import OpenFOAMError

        err = OpenFOAMError("blockMesh", 127, "", "not found")
        assert isinstance(err, RuntimeError)

    def test_run_openfoam_raises_when_not_installed(self, tmp_path: Path) -> None:
        """OpenFOAM 미설치 → OpenFOAMError 발생 확인 (bash 실행 실패 시뮬레이션)."""
        from core.utils.openfoam_utils import OpenFOAMError, run_openfoam

        # 존재하지 않는 OPENFOAM_DIR을 설정하여 source 실패 유도
        import os
        with patch.dict(os.environ, {"OPENFOAM_DIR": "/nonexistent/openfoam"}):
            # bashrc 없으면 FileNotFoundError, 실행 실패하면 OpenFOAMError
            with pytest.raises((OpenFOAMError, FileNotFoundError)):
                run_openfoam("blockMesh_NONEXISTENT_CMD_XYZ", tmp_path)


# ---------------------------------------------------------------------------
# quality_level 기반 Tier 순서 테스트
# ---------------------------------------------------------------------------


def _make_strategy_with_quality(quality: QualityLevel, selected_tier: str = "auto") -> MeshStrategy:
    """테스트용 MeshStrategy 생성 헬퍼."""
    return MeshStrategy(
        strategy_version=2,
        iteration=1,
        quality_level=quality,
        selected_tier=selected_tier,
        fallback_tiers=[],
        flow_type="external",
        domain=DomainConfig(
            type="box",
            min=[-1.0, -1.0, -1.0],
            max=[1.0, 1.0, 1.0],
            base_cell_size=0.1,
            location_in_mesh=[0.0, 0.0, 0.0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="preprocessed.stl",
            target_cell_size=0.05,
            min_cell_size=0.01,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False,
            num_layers=0,
            first_layer_thickness=0.001,
            growth_ratio=1.2,
            max_total_thickness=0.01,
            min_thickness_ratio=0.1,
        ),
    )


class TestTierOrderByQualityLevel:
    """quality_level 기반 Tier 실행 순서 테스트."""

    def test_draft_tier_order(self) -> None:
        """draft → TetWild coarse 우선, JIGSAW fallback, Netgen 순."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.DRAFT)
        order = gen._get_tier_order(strategy)

        assert order[0] == "tier2_tetwild", "Draft: TetWild이 첫 번째여야 합니다"
        assert order[1] == "tier_jigsaw", "Draft: JIGSAW가 두 번째 fallback이어야 합니다"
        assert "tier05_netgen" in order

    def test_standard_tier_order(self) -> None:
        """standard → Netgen 우선, MeshPy fallback, cfMesh, TetWild 순."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.STANDARD)
        order = gen._get_tier_order(strategy)

        assert order[0] == "tier05_netgen", "Standard: Netgen이 첫 번째여야 합니다"
        assert "tier_meshpy" in order, "Standard: MeshPy가 fallback에 있어야 합니다"
        assert "tier15_cfmesh" in order
        assert "tier2_tetwild" in order
        # MeshPy는 Netgen 바로 다음 (인덱스 1)
        assert order[1] == "tier_meshpy"

    def test_fine_tier_order(self) -> None:
        """fine → classy_blocks → cfMesh → snappy → Netgen → TetWild 순."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.FINE)
        with patch("core.generator.pipeline.get_openfoam_label_size", return_value=64):
            order = gen._get_tier_order(strategy)

        assert order[0] == "tier_classy_blocks", "Fine: classy_blocks가 첫 번째(구조 Hex)"
        assert order[1] == "tier15_cfmesh"
        assert order[2] == "tier1_snappy"
        assert order[3] == "tier05_netgen"
        assert order[4] == "tier2_tetwild"

    def test_fine_tier_order_demotes_snappy_on_int32(self) -> None:
        """fine + label=32에서는 snappy 우선도를 낮춰 뒤로 미룬다."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.FINE)
        with patch("core.generator.pipeline.get_openfoam_label_size", return_value=32):
            order = gen._get_tier_order(strategy)

        assert order == [
            "tier_classy_blocks",
            "tier15_cfmesh",
            "tier05_netgen",
            "tier2_tetwild",
            "tier1_snappy",
        ]

    def test_explicit_tier_overrides_quality_level(self) -> None:
        """selected_tier가 명시적으로 지정되면 quality_level 기반 순서 무시."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        # draft quality이지만 selected_tier를 snappy로 명시
        strategy = _make_strategy_with_quality(QualityLevel.DRAFT, selected_tier="tier1_snappy")
        strategy.fallback_tiers = ["tier15_cfmesh"]
        order = gen._get_tier_order(strategy)

        assert order[0] == "tier1_snappy", "명시적 selected_tier가 우선되어야 합니다"
        assert order[1] == "tier15_cfmesh"

    def test_explicit_tier_alias_overrides_quality_level(self) -> None:
        """별칭(snappy)으로 지정해도 명시적 모드로 인식."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.FINE, selected_tier="netgen")
        order = gen._get_tier_order(strategy)

        assert order[0] == "tier05_netgen", "별칭 지정 시 해당 Tier가 첫 번째여야 합니다"

    def test_quality_level_in_generator_log(
        self, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """GeneratorLog.execution_summary.quality_level이 올바르게 기록되는지 확인."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.DRAFT)

        with patch("core.generator.pipeline._run_tier") as mock_run:
            mock_run.side_effect = lambda tier, strategy, path, case: TierAttempt(
                tier=tier,
                status="failed",
                time_seconds=0.01,
                error_message="mock fail",
            )
            log = gen.run(strategy, dummy_stl, tmp_path)

        assert log.execution_summary.quality_level == "draft"

    def test_quality_level_standard_in_log(
        self, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """standard quality_level이 GeneratorLog에 기록되는지 확인."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.STANDARD)

        with patch("core.generator.pipeline._run_tier") as mock_run:
            mock_run.return_value = TierAttempt(
                tier="tier05_netgen",
                status="success",
                time_seconds=0.01,
            )
            log = gen.run(strategy, dummy_stl, tmp_path)

        assert log.execution_summary.quality_level == "standard"

    def test_draft_uses_large_epsilon(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """Draft 모드 → TetWild epsilon=0.02, stop_energy=20.0 사용 확인."""
        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        mesh_strategy.quality_level = QualityLevel.DRAFT
        # tier_specific_params에 epsilon/stop_energy 없음 → 기본값 사용
        mesh_strategy.tier_specific_params.pop("tetwild_epsilon", None)
        mesh_strategy.tier_specific_params.pop("tetwild_stop_energy", None)

        gen = Tier2TetWildGenerator()

        captured_kwargs: dict = {}

        def mock_tetrahedralize(vertices, faces, **kwargs):
            captured_kwargs.update(kwargs)
            raise RuntimeError("mock stop after capture")

        import trimesh as _trimesh

        mock_surf = MagicMock()
        mock_surf.vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        mock_surf.faces = [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]

        with patch.dict("sys.modules", {}):
            import sys
            mock_pytetwild = MagicMock()
            mock_pytetwild.tetrahedralize = mock_tetrahedralize
            with patch.dict(sys.modules, {"pytetwild": mock_pytetwild}):
                with patch("trimesh.load", return_value=mock_surf):
                    attempt = gen.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        # stop_energy=20.0이 Draft 기본값으로 사용되었는지 확인
        assert captured_kwargs.get("stop_energy") == pytest.approx(20.0)

    def test_standard_uses_standard_epsilon(
        self, mesh_strategy: MeshStrategy, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """Standard 모드 → TetWild stop_energy=10.0 (기본값) 사용 확인."""
        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        mesh_strategy.quality_level = QualityLevel.STANDARD
        mesh_strategy.tier_specific_params.pop("tetwild_stop_energy", None)

        gen = Tier2TetWildGenerator()
        captured_kwargs: dict = {}

        def mock_tetrahedralize(vertices, faces, **kwargs):
            captured_kwargs.update(kwargs)
            raise RuntimeError("mock stop after capture")

        mock_surf = MagicMock()
        mock_surf.vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        mock_surf.faces = [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]

        import sys
        mock_pytetwild = MagicMock()
        mock_pytetwild.tetrahedralize = mock_tetrahedralize
        with patch.dict(sys.modules, {"pytetwild": mock_pytetwild}):
            with patch("trimesh.load", return_value=mock_surf):
                attempt = gen.run(mesh_strategy, dummy_stl, tmp_path)

        assert attempt.status == "failed"
        assert captured_kwargs.get("stop_energy") == pytest.approx(10.0)

    def test_draft_pipeline_starts_with_tetwild(
        self, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """Draft pipeline → TetWild이 첫 번째로 실행되는지 확인."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.DRAFT)
        called_tiers: list[str] = []

        def mock_run_tier(tier, strat, path, case):
            called_tiers.append(tier)
            return TierAttempt(tier=tier, status="failed", time_seconds=0.01,
                               error_message="mock")

        with patch("core.generator.pipeline._run_tier", side_effect=mock_run_tier):
            gen.run(strategy, dummy_stl, tmp_path)

        assert called_tiers[0] == "tier2_tetwild"

    def test_fine_pipeline_starts_with_classy_blocks(
        self, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """Fine pipeline → classy_blocks가 첫 번째 (구조 Hex 우선)."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.FINE)
        called_tiers: list[str] = []

        def mock_run_tier(tier, strat, path, case):
            called_tiers.append(tier)
            return TierAttempt(tier=tier, status="failed", time_seconds=0.01,
                               error_message="mock")

        with patch("core.generator.pipeline._run_tier", side_effect=mock_run_tier):
            gen.run(strategy, dummy_stl, tmp_path)

        assert called_tiers[0] == "tier_classy_blocks"
        assert called_tiers[1] == "tier15_cfmesh"


# ---------------------------------------------------------------------------
# 새 Tier 등록 / 별칭 테스트
# ---------------------------------------------------------------------------


class TestNewTierRegistry:
    """v0.3에서 추가된 MeshPy / classy_blocks / JIGSAW Tier 등록 확인."""

    def test_meshpy_in_registry(self) -> None:
        """tier_meshpy가 _TIER_REGISTRY에 등록되어 있어야 한다."""
        from core.generator.pipeline import _TIER_REGISTRY

        assert "tier_meshpy" in _TIER_REGISTRY

    def test_classy_blocks_in_registry(self) -> None:
        """tier_classy_blocks가 _TIER_REGISTRY에 등록되어 있어야 한다."""
        from core.generator.pipeline import _TIER_REGISTRY

        assert "tier_classy_blocks" in _TIER_REGISTRY

    def test_jigsaw_in_registry(self) -> None:
        """tier_jigsaw가 _TIER_REGISTRY에 등록되어 있어야 한다."""
        from core.generator.pipeline import _TIER_REGISTRY

        assert "tier_jigsaw" in _TIER_REGISTRY

    def test_meshpy_alias(self) -> None:
        """'meshpy' 별칭 → tier_meshpy 해석 확인."""
        from core.generator.pipeline import _resolve_tier

        assert _resolve_tier("meshpy") == "tier_meshpy"

    def test_classy_blocks_alias(self) -> None:
        """'classy_blocks' 별칭 → tier_classy_blocks 해석 확인."""
        from core.generator.pipeline import _resolve_tier

        assert _resolve_tier("classy_blocks") == "tier_classy_blocks"

    def test_jigsaw_alias(self) -> None:
        """'jigsaw' 별칭 → tier_jigsaw 해석 확인."""
        from core.generator.pipeline import _resolve_tier

        assert _resolve_tier("jigsaw") == "tier_jigsaw"

    def test_standard_has_meshpy_in_fallback(self) -> None:
        """Standard auto 모드 → tier_meshpy가 Netgen 바로 다음 fallback."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.STANDARD)
        order = gen._get_tier_order(strategy)

        netgen_idx = order.index("tier05_netgen")
        meshpy_idx = order.index("tier_meshpy")
        assert meshpy_idx == netgen_idx + 1, "MeshPy는 Netgen 바로 다음이어야 합니다"

    def test_draft_has_jigsaw_after_tetwild(self) -> None:
        """Draft auto 모드 → tier_jigsaw가 TetWild 바로 다음 fallback."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.DRAFT)
        order = gen._get_tier_order(strategy)

        tetwild_idx = order.index("tier2_tetwild")
        jigsaw_idx = order.index("tier_jigsaw")
        assert jigsaw_idx == tetwild_idx + 1, "JIGSAW는 TetWild 바로 다음이어야 합니다"

    def test_fine_has_classy_blocks_first(self) -> None:
        """Fine auto 모드 → tier_classy_blocks가 첫 번째."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.FINE)
        order = gen._get_tier_order(strategy)

        assert order[0] == "tier_classy_blocks"

    def test_pipeline_runs_meshpy_as_fallback(
        self, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """Standard pipeline: Netgen 실패 시 tier_meshpy가 실행됨."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.STANDARD)
        called_tiers: list[str] = []

        def mock_run_tier(tier, strat, path, case):
            called_tiers.append(tier)
            if tier == "tier05_netgen":
                return TierAttempt(tier=tier, status="failed", time_seconds=0.01,
                                   error_message="netgen mock fail")
            # meshpy succeeds
            return TierAttempt(tier=tier, status="success", time_seconds=0.01)

        with patch("core.generator.pipeline._run_tier", side_effect=mock_run_tier):
            log = gen.run(strategy, dummy_stl, tmp_path)

        assert "tier05_netgen" in called_tiers
        assert "tier_meshpy" in called_tiers
        success_attempts = [a for a in log.execution_summary.tiers_attempted
                            if a.status == "success"]
        assert len(success_attempts) == 1
        assert success_attempts[0].tier == "tier_meshpy"

    def test_pipeline_runs_jigsaw_as_draft_fallback(
        self, tmp_path: Path, dummy_stl: Path
    ) -> None:
        """Draft pipeline: TetWild 실패 시 tier_jigsaw가 실행됨."""
        from core.generator.pipeline import MeshGenerator

        gen = MeshGenerator()
        strategy = _make_strategy_with_quality(QualityLevel.DRAFT)
        called_tiers: list[str] = []

        def mock_run_tier(tier, strat, path, case):
            called_tiers.append(tier)
            if tier == "tier2_tetwild":
                return TierAttempt(tier=tier, status="failed", time_seconds=0.01,
                                   error_message="tetwild mock fail")
            return TierAttempt(tier=tier, status="success", time_seconds=0.01)

        with patch("core.generator.pipeline._run_tier", side_effect=mock_run_tier):
            log = gen.run(strategy, dummy_stl, tmp_path)

        assert "tier2_tetwild" in called_tiers
        assert "tier_jigsaw" in called_tiers
        success_attempts = [a for a in log.execution_summary.tiers_attempted
                            if a.status == "success"]
        assert len(success_attempts) == 1
        assert success_attempts[0].tier == "tier_jigsaw"


# ---------------------------------------------------------------------------
# PolyMeshWriter tests
# ---------------------------------------------------------------------------

import numpy as np


class TestPolyMeshWriter:
    """Unit tests for the standalone OpenFOAM polyMesh writer."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _single_tet_mesh():
        """A single tetrahedron: 4 vertices, 1 cell, 4 boundary faces."""
        vertices = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=float)
        tets = np.array([[0, 1, 2, 3]], dtype=int)
        return vertices, tets

    @staticmethod
    def _two_tet_mesh():
        """Two tets sharing one face.

        Vertices 0-3 form tet-0.  We add vertex 4 and build tet-1 = (1,2,3,4)
        which shares face (1,2,3) with tet-0.
        """
        vertices = np.array([
            [0.0, 0.0, 0.0],  # 0
            [1.0, 0.0, 0.0],  # 1
            [0.0, 1.0, 0.0],  # 2
            [0.0, 0.0, 1.0],  # 3
            [1.0, 1.0, 1.0],  # 4
        ], dtype=float)
        tets = np.array([
            [0, 1, 2, 3],
            [1, 2, 3, 4],
        ], dtype=int)
        return vertices, tets

    # ------------------------------------------------------------------
    # file creation
    # ------------------------------------------------------------------

    def test_polymesh_writer_creates_files(self, tmp_path: Path) -> None:
        """PolyMeshWriter creates all five required polyMesh files."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._single_tet_mesh()
        writer = PolyMeshWriter()
        writer.write(vertices, tets, tmp_path)

        poly_dir = tmp_path / "constant" / "polyMesh"
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            assert (poly_dir / name).exists(), f"missing: {name}"

    def test_polymesh_writer_files_have_foam_header(self, tmp_path: Path) -> None:
        """Every polyMesh file starts with a FoamFile header."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._single_tet_mesh()
        PolyMeshWriter().write(vertices, tets, tmp_path)

        poly_dir = tmp_path / "constant" / "polyMesh"
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            content = (poly_dir / name).read_text()
            assert "FoamFile" in content, f"{name}: missing FoamFile header"

    # ------------------------------------------------------------------
    # single tet topology
    # ------------------------------------------------------------------

    def test_polymesh_writer_single_tet(self, tmp_path: Path) -> None:
        """Single tet → 4 boundary faces, 0 internal faces."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._single_tet_mesh()
        stats = PolyMeshWriter().write(vertices, tets, tmp_path)

        assert stats["num_cells"] == 1
        assert stats["num_points"] == 4
        assert stats["num_internal_faces"] == 0
        assert stats["num_faces"] == 4

    def test_polymesh_writer_single_tet_neighbour_is_empty(self, tmp_path: Path) -> None:
        """Single tet has no internal faces → neighbour list is empty (count = 0)."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._single_tet_mesh()
        PolyMeshWriter().write(vertices, tets, tmp_path)

        content = (tmp_path / "constant" / "polyMesh" / "neighbour").read_text()
        # The count line should be "0"
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        # Find the line after the FoamFile block that is just a number
        in_foam = False
        count_line = None
        for ln in lines:
            if "FoamFile" in ln:
                in_foam = True
            if in_foam and ln == "}":
                in_foam = False
                continue
            if not in_foam and ln.lstrip("-").isdigit():
                count_line = ln
                break
        assert count_line == "0", f"expected count=0, got: {count_line!r}"

    def test_polymesh_writer_single_tet_boundary_nfaces(self, tmp_path: Path) -> None:
        """Single tet boundary file reports nFaces = 4."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._single_tet_mesh()
        PolyMeshWriter().write(vertices, tets, tmp_path)

        content = (tmp_path / "constant" / "polyMesh" / "boundary").read_text()
        assert "nFaces 4" in content

    def test_polymesh_writer_single_tet_start_face_zero(self, tmp_path: Path) -> None:
        """Single tet: all faces are boundary → startFace = 0."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._single_tet_mesh()
        PolyMeshWriter().write(vertices, tets, tmp_path)

        content = (tmp_path / "constant" / "polyMesh" / "boundary").read_text()
        assert "startFace 0" in content

    # ------------------------------------------------------------------
    # two-tet topology
    # ------------------------------------------------------------------

    def test_polymesh_writer_two_tets(self, tmp_path: Path) -> None:
        """Two tets sharing a face → exactly 1 internal face."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._two_tet_mesh()
        stats = PolyMeshWriter().write(vertices, tets, tmp_path)

        assert stats["num_cells"] == 2
        assert stats["num_points"] == 5
        assert stats["num_internal_faces"] == 1
        # 2 tets × 4 faces = 8 half-faces; 1 shared → 7 total faces
        assert stats["num_faces"] == 7

    def test_polymesh_writer_two_tets_neighbour_entry(self, tmp_path: Path) -> None:
        """Two tets → neighbour file has exactly 1 entry."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._two_tet_mesh()
        PolyMeshWriter().write(vertices, tets, tmp_path)

        content = (tmp_path / "constant" / "polyMesh" / "neighbour").read_text()
        # Parse entries between '(' and ')'
        inside = False
        entries = []
        for ln in content.splitlines():
            stripped = ln.strip()
            if stripped == "(":
                inside = True
                continue
            if stripped == ")":
                break
            if inside and stripped.lstrip("-").isdigit():
                entries.append(int(stripped))

        assert len(entries) == 1

    def test_polymesh_writer_two_tets_owner_less_than_neighbour(self, tmp_path: Path) -> None:
        """For all internal faces, owner < neighbour."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._two_tet_mesh()
        PolyMeshWriter().write(vertices, tets, tmp_path)

        poly_dir = tmp_path / "constant" / "polyMesh"

        def parse_labels(path: Path) -> list[int]:
            inside = False
            result = []
            for ln in path.read_text().splitlines():
                s = ln.strip()
                if s == "(":
                    inside = True
                    continue
                if s == ")":
                    break
                if inside and s.lstrip("-").isdigit():
                    result.append(int(s))
            return result

        stats_dict = PolyMeshWriter().write(vertices, tets, tmp_path)
        n_internal = stats_dict["num_internal_faces"]

        owners = parse_labels(poly_dir / "owner")
        neighbours = parse_labels(poly_dir / "neighbour")

        for i, (o, n) in enumerate(zip(owners[:n_internal], neighbours)):
            assert o < n, f"face {i}: owner {o} >= neighbour {n}"

    def test_polymesh_writer_two_tets_boundary_start_face(self, tmp_path: Path) -> None:
        """Two tets: boundary startFace equals number of internal faces."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._two_tet_mesh()
        stats = PolyMeshWriter().write(vertices, tets, tmp_path)

        content = (tmp_path / "constant" / "polyMesh" / "boundary").read_text()
        n_internal = stats["num_internal_faces"]
        assert f"startFace {n_internal}" in content

    # ------------------------------------------------------------------
    # points file content
    # ------------------------------------------------------------------

    def test_polymesh_writer_points_content(self, tmp_path: Path) -> None:
        """points file contains correct coordinate values."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._single_tet_mesh()
        PolyMeshWriter().write(vertices, tets, tmp_path)

        content = (tmp_path / "constant" / "polyMesh" / "points").read_text()
        # Origin should appear
        assert "(0 0 0)" in content or "(0.0 0.0 0.0)" in content or "(0 0 0)" in content

    # ------------------------------------------------------------------
    # return value
    # ------------------------------------------------------------------

    def test_polymesh_writer_returns_stats_dict(self, tmp_path: Path) -> None:
        """write() returns dict with expected keys."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices, tets = self._single_tet_mesh()
        stats = PolyMeshWriter().write(vertices, tets, tmp_path)

        for key in ("num_cells", "num_points", "num_faces", "num_internal_faces"):
            assert key in stats, f"missing key: {key}"

    # ------------------------------------------------------------------
    # sphere (real pytetwild)
    # ------------------------------------------------------------------

    @pytest.mark.skipif(
        not (Path("tests/benchmarks/sphere.stl")).exists(),
        reason="sphere.stl not found",
    )
    def test_polymesh_writer_sphere(self, tmp_path: Path) -> None:
        pytest.importorskip("pytetwild", reason="pytetwild not installed")
        """Real sphere tetrahedralization → sane polyMesh statistics."""
        import trimesh
        import pytetwild
        from core.generator.polymesh_writer import PolyMeshWriter

        sphere_path = Path("tests/benchmarks/sphere.stl")
        surf = trimesh.load(str(sphere_path))
        tet_v, tet_f = pytetwild.tetrahedralize(
            surf.vertices,
            surf.faces,
            stop_energy=100.0,  # very coarse for speed
        )

        stats = PolyMeshWriter().write(tet_v, tet_f, tmp_path)

        assert stats["num_cells"] > 0
        assert stats["num_points"] > 0
        assert stats["num_internal_faces"] > 0
        assert stats["num_faces"] > stats["num_internal_faces"]

        poly_dir = tmp_path / "constant" / "polyMesh"
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            assert (poly_dir / name).exists()


# ---------------------------------------------------------------------------
# TetWild tier integration test (uses PolyMeshWriter)
# ---------------------------------------------------------------------------


class TestTetWildPolyMeshIntegration:
    """Integration tests confirming TetWild tier produces a valid polyMesh."""

    @pytest.fixture()
    def tetwild_strategy(self) -> MeshStrategy:
        return MeshStrategy(
            strategy_version=2,
            iteration=1,
            selected_tier="tier2_tetwild",
            fallback_tiers=[],
            flow_type="external",
            quality_level=QualityLevel.DRAFT,
            domain=DomainConfig(
                type="box",
                min=[-1.0, -1.0, -1.0],
                max=[1.0, 1.0, 1.0],
                base_cell_size=0.1,
                location_in_mesh=[0.0, 0.0, 0.0],
            ),
            surface_mesh=SurfaceMeshConfig(
                input_file="sphere.stl",
                target_cell_size=0.05,
                min_cell_size=0.01,
            ),
            boundary_layers=BoundaryLayerConfig(
                enabled=False,
                num_layers=0,
                first_layer_thickness=0.001,
                growth_ratio=1.2,
                max_total_thickness=0.01,
                min_thickness_ratio=0.1,
            ),
            tier_specific_params={
                "tetwild_stop_energy": 100.0,  # coarse — fast for CI
            },
        )

    def test_tetwild_tier_uses_polymesh_writer_on_success(
        self,
        tetwild_strategy: MeshStrategy,
        tmp_path: Path,
    ) -> None:
        """Mocked pytetwild run → PolyMeshWriter is called, polyMesh files written."""
        import sys
        from core.generator.tier2_tetwild import Tier2TetWildGenerator
        from unittest.mock import MagicMock, patch

        # Small cube surface mesh
        vert = np.array([
            [0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.],
        ], dtype=float)
        faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=int)

        mock_surf = MagicMock()
        mock_surf.vertices = vert
        mock_surf.faces = faces

        # pytetwild returns a single tet
        tet_verts = vert.copy()
        tet_cells = np.array([[0, 1, 2, 3]], dtype=int)

        mock_pytetwild = MagicMock()
        mock_pytetwild.tetrahedralize.return_value = (tet_verts, tet_cells)

        stl_path = tmp_path / "sphere.stl"
        stl_path.write_text("solid dummy\nendsolid dummy\n")

        with patch.dict(sys.modules, {"pytetwild": mock_pytetwild}):
            with patch("trimesh.load", return_value=mock_surf):
                gen = Tier2TetWildGenerator()
                attempt = gen.run(tetwild_strategy, stl_path, tmp_path)

        assert attempt.status == "success"
        poly_dir = tmp_path / "constant" / "polyMesh"
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            assert (poly_dir / name).exists(), f"missing polyMesh file: {name}"

    @pytest.mark.skipif(
        not Path("tests/benchmarks/sphere.stl").exists(),
        reason="sphere.stl not found",
    )
    def test_tetwild_tier_produces_polymesh_real(
        self,
        tetwild_strategy: MeshStrategy,
        tmp_path: Path,
    ) -> None:
        """Real pytetwild on sphere.stl → polyMesh directory with all files."""
        try:
            import pytetwild  # noqa: F401
        except ImportError:
            pytest.skip("pytetwild not installed")

        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        sphere_path = Path("tests/benchmarks/sphere.stl")
        gen = Tier2TetWildGenerator()
        attempt = gen.run(tetwild_strategy, sphere_path, tmp_path)

        assert attempt.status == "success", f"tier failed: {attempt.error_message}"

        poly_dir = tmp_path / "constant" / "polyMesh"
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            assert (poly_dir / name).exists(), f"missing: {name}"


# ---------------------------------------------------------------------------
# Netgen tier — PolyMeshWriter fallback tests
# ---------------------------------------------------------------------------


class TestNetgenPolyMeshFallback:
    """Tests for the gmshToFoam → PolyMeshWriter fallback path in Tier 0.5."""

    @pytest.fixture()
    def netgen_strategy(self) -> MeshStrategy:
        return MeshStrategy(
            strategy_version=2,
            iteration=1,
            selected_tier="tier05_netgen",
            fallback_tiers=[],
            flow_type="external",
            quality_level=QualityLevel.STANDARD,
            domain=DomainConfig(
                type="box",
                min=[-1.0, -1.0, -1.0],
                max=[1.0, 1.0, 1.0],
                base_cell_size=0.1,
                location_in_mesh=[0.0, 0.0, 0.0],
            ),
            surface_mesh=SurfaceMeshConfig(
                input_file="sphere.stl",
                target_cell_size=0.05,
                min_cell_size=0.01,
            ),
            boundary_layers=BoundaryLayerConfig(
                enabled=False,
                num_layers=0,
                first_layer_thickness=0.001,
                growth_ratio=1.2,
                max_total_thickness=0.01,
                min_thickness_ratio=0.1,
            ),
            tier_specific_params={
                "netgen_grading": 0.3,
                "netgen_curvaturesafety": 2.0,
                "netgen_segmentsperedge": 1.0,
            },
        )

    def test_netgen_fallback_to_polymesh_writer(
        self,
        netgen_strategy: MeshStrategy,
        tmp_path: Path,
    ) -> None:
        """gmshToFoam raises FileNotFoundError → PolyMeshWriter is used and
        polyMesh files are created."""
        import sys
        from unittest.mock import MagicMock, patch

        stl_path = tmp_path / "sphere.stl"
        stl_path.write_text("solid dummy\nendsolid dummy\n")

        # Minimal tet mesh data (4 vertices, 1 tetrahedron)
        tet_verts = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=float)
        tet_cells = np.array([[0, 1, 2, 3]], dtype=int)

        # Mock netgen geometry and mesh objects
        mock_mesh = MagicMock()

        def fake_export(path, fmt):
            """Write a minimal Gmsh2 .msh file that meshio can parse."""
            Path(path).write_text(
                "$MeshFormat\n2.2 0 8\n$EndMeshFormat\n"
                "$Nodes\n4\n"
                "1 0.0 0.0 0.0\n"
                "2 1.0 0.0 0.0\n"
                "3 0.0 1.0 0.0\n"
                "4 0.0 0.0 1.0\n"
                "$EndNodes\n"
                "$Elements\n1\n"
                "1 4 0 0 1 2 3 4\n"
                "$EndElements\n"
            )

        mock_mesh.Export = fake_export
        mock_geo = MagicMock()
        mock_geo.GenerateMesh.return_value = mock_mesh

        mock_nm = MagicMock()
        mock_nm.STLGeometry.return_value = mock_geo

        mock_occ = MagicMock()

        mock_stl_mod = MagicMock()
        mock_stl_mod.STLGeometry.return_value = mock_geo

        mock_netgen = MagicMock()
        mock_netgen.meshing = mock_nm
        mock_netgen.stl = mock_stl_mod

        with patch.dict(sys.modules, {
            "netgen": mock_netgen,
            "netgen.meshing": mock_nm,
            "netgen.stl": mock_stl_mod,
            "netgen.occ": mock_occ,
        }):
            # Make run_openfoam raise FileNotFoundError to trigger the fallback
            with patch(
                "core.generator.tier05_netgen.run_openfoam",
                side_effect=FileNotFoundError("gmshToFoam: command not found"),
            ):
                from core.generator.tier05_netgen import Tier05NetgenGenerator
                gen = Tier05NetgenGenerator()
                attempt = gen.run(netgen_strategy, stl_path, tmp_path)

        assert attempt.status == "success", (
            f"Expected success via PolyMeshWriter fallback, got: {attempt.error_message}"
        )
        poly_dir = tmp_path / "constant" / "polyMesh"
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            assert (poly_dir / name).exists(), f"missing polyMesh file: {name}"

    @pytest.mark.skipif(
        not Path("tests/benchmarks/sphere.stl").exists(),
        reason="sphere.stl not found",
    )
    def test_netgen_real_sphere_stl(
        self,
        netgen_strategy: MeshStrategy,
        tmp_path: Path,
    ) -> None:
        """Real Netgen on sphere.stl with PolyMeshWriter fallback (no OpenFOAM required)."""
        try:
            import netgen.meshing as _nm  # noqa: F401
            if not hasattr(_nm, "STLGeometry"):
                pytest.skip("netgen.meshing.STLGeometry not available in this build")
        except ImportError:
            pytest.skip("netgen not installed")

        sphere_path = Path("tests/benchmarks/sphere.stl")
        from core.generator.tier05_netgen import Tier05NetgenGenerator

        gen = Tier05NetgenGenerator()
        # Force the PolyMeshWriter path by making run_openfoam raise FileNotFoundError
        with patch(
            "core.generator.tier05_netgen.run_openfoam",
            side_effect=FileNotFoundError("gmshToFoam: command not found"),
        ):
            attempt = gen.run(netgen_strategy, sphere_path, tmp_path)

        assert attempt.status == "success", f"tier failed: {attempt.error_message}"

        poly_dir = tmp_path / "constant" / "polyMesh"
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            assert (poly_dir / name).exists(), f"missing polyMesh file after fallback: {name}"


# ---------------------------------------------------------------------------
# Face winding-order correctness tests
# ---------------------------------------------------------------------------

import shutil

HAS_OPENFOAM = bool(
    shutil.which("checkMesh")
    or Path("/opt/openfoam13/etc/bashrc").exists()
    or Path("/opt/openfoam12/etc/bashrc").exists()
    or Path("/opt/openfoam11/etc/bashrc").exists()
)


def _parse_faces_file(poly_dir: Path) -> list[list[int]]:
    """Parse the OpenFOAM faces file and return a list of vertex-index lists."""
    faces: list[list[int]] = []
    inside = False
    for ln in (poly_dir / "faces").read_text().splitlines():
        stripped = ln.strip()
        if stripped == "(":
            inside = True
            continue
        if stripped == ")" and inside:
            break
        if inside and stripped.startswith("3("):
            # format: 3(a b c)
            nums = stripped[2:-1].split()
            faces.append([int(x) for x in nums])
    return faces


def _parse_labels_file(path: Path) -> list[int]:
    """Parse an OpenFOAM labelList file (owner / neighbour)."""
    result: list[int] = []
    inside = False
    for ln in path.read_text().splitlines():
        s = ln.strip()
        if s == "(":
            inside = True
            continue
        if s == ")" and inside:
            break
        if inside and s.lstrip("-").isdigit():
            result.append(int(s))
    return result


class TestFaceWindingOrder:
    """Verify that internal face normals point from owner to neighbour."""

    @staticmethod
    def _face_normal(verts: np.ndarray, face: list[int]) -> np.ndarray:
        """Right-hand-rule normal for a triangular face."""
        v0, v1, v2 = verts[face[0]], verts[face[1]], verts[face[2]]
        n = np.cross(v1 - v0, v2 - v0)
        return n  # unnormalized is fine for dot-product sign check

    @staticmethod
    def _cell_center(verts: np.ndarray, tet: list[int]) -> np.ndarray:
        return verts[tet].mean(axis=0)

    def test_two_tet_internal_face_normal_direction(self, tmp_path: Path) -> None:
        """For the two-tet mesh the internal face normal must point from
        owner cell center toward neighbour cell center (positive dot product)."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ], dtype=float)
        tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=int)

        stats = PolyMeshWriter().write(vertices, tets, tmp_path)
        n_internal = stats["num_internal_faces"]

        poly_dir = tmp_path / "constant" / "polyMesh"
        faces = _parse_faces_file(poly_dir)
        owners = _parse_labels_file(poly_dir / "owner")
        neighbours = _parse_labels_file(poly_dir / "neighbour")

        for i in range(n_internal):
            face = faces[i]
            own_center = self._cell_center(vertices, list(tets[owners[i]]))
            nbr_center = self._cell_center(vertices, list(tets[neighbours[i]]))
            face_center = vertices[face].mean(axis=0)
            normal = self._face_normal(vertices, face)

            # Vector from face_center toward neighbour
            to_nbr = nbr_center - face_center
            dot = float(np.dot(normal, to_nbr))
            assert dot > 0, (
                f"Internal face {i}: normal points away from neighbour "
                f"(dot={dot:.6g}). owner={owners[i]}, nbr={neighbours[i]}, "
                f"face verts={face}"
            )

    def test_two_tet_boundary_face_normal_outward(self, tmp_path: Path) -> None:
        """For boundary faces the normal must point away from the owner cell center."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ], dtype=float)
        tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=int)

        stats = PolyMeshWriter().write(vertices, tets, tmp_path)
        n_internal = stats["num_internal_faces"]
        n_faces = stats["num_faces"]

        poly_dir = tmp_path / "constant" / "polyMesh"
        faces = _parse_faces_file(poly_dir)
        owners = _parse_labels_file(poly_dir / "owner")

        for i in range(n_internal, n_faces):
            face = faces[i]
            own_center = self._cell_center(vertices, list(tets[owners[i]]))
            face_center = vertices[face].mean(axis=0)
            normal = self._face_normal(vertices, face)

            # Vector from cell center toward face center (outward direction)
            outward = face_center - own_center
            dot = float(np.dot(normal, outward))
            assert dot > 0, (
                f"Boundary face {i}: normal points inward "
                f"(dot={dot:.6g}). owner={owners[i]}, face verts={face}"
            )

    def test_negative_volume_tet_faces_outward(self, tmp_path: Path) -> None:
        """A tet with negative volume (swapped vertices) must be normalised so
        its four boundary faces still point outward after writing."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=float)
        # Swap v0 and v1 to create a negatively-oriented tet
        tets = np.array([[1, 0, 2, 3]], dtype=int)

        # Confirm it is indeed negative
        a, b, c, d = vertices[[1, 0, 2, 3]]
        vol = np.dot(b - a, np.cross(c - a, d - a))
        assert vol < 0, "test tet should have negative volume before fixing"

        stats = PolyMeshWriter().write(vertices, tets, tmp_path)
        assert stats["num_internal_faces"] == 0

        poly_dir = tmp_path / "constant" / "polyMesh"
        faces = _parse_faces_file(poly_dir)
        owners = _parse_labels_file(poly_dir / "owner")

        cell_center = vertices.mean(axis=0)
        for i, face in enumerate(faces):
            face_center = vertices[face].mean(axis=0)
            normal = self._face_normal(vertices, face)
            outward = face_center - cell_center
            dot = float(np.dot(normal, outward))
            assert dot > 0, (
                f"Negative-tet face {i} still points inward after normalisation "
                f"(dot={dot:.6g}), verts={face}"
            )

    def test_single_tet_all_boundary_faces_outward(self, tmp_path: Path) -> None:
        """All four faces of a single tet must have outward normals."""
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=float)
        tets = np.array([[0, 1, 2, 3]], dtype=int)

        stats = PolyMeshWriter().write(vertices, tets, tmp_path)
        assert stats["num_internal_faces"] == 0

        poly_dir = tmp_path / "constant" / "polyMesh"
        faces = _parse_faces_file(poly_dir)
        owners = _parse_labels_file(poly_dir / "owner")

        cell_center = vertices.mean(axis=0)
        for i, face in enumerate(faces):
            face_center = vertices[face].mean(axis=0)
            normal = self._face_normal(vertices, face)
            outward = face_center - cell_center
            dot = float(np.dot(normal, outward))
            assert dot > 0, (
                f"Face {i} of single tet points inward (dot={dot:.6g}), "
                f"verts={face}"
            )

    def test_normalize_tet_winding_helper(self) -> None:
        """_normalize_tet_winding fixes negative-volume tets and leaves positive
        ones unchanged."""
        from core.generator.polymesh_writer import _normalize_tet_winding

        vertices = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ], dtype=float)

        def signed_vol(v, tet):
            a, b, c, d = v[tet[0]], v[tet[1]], v[tet[2]], v[tet[3]]
            return np.dot(b - a, np.cross(c - a, d - a))

        # tet 0: positive volume
        # tet 1: negative volume (swapped v0, v1)
        tets = np.array([[0, 1, 2, 3], [1, 0, 2, 4]], dtype=int)
        assert signed_vol(vertices, tets[0]) > 0
        assert signed_vol(vertices, tets[1]) < 0

        fixed = _normalize_tet_winding(vertices, tets)

        assert signed_vol(vertices, fixed[0]) > 0, "positive tet should remain positive"
        assert signed_vol(vertices, fixed[1]) > 0, "negative tet should become positive"

    def test_mixed_orientation_tets_all_faces_outward(self, tmp_path: Path) -> None:
        """A mesh with both positive and negative tets should produce all
        outward face normals after normalization.

        Geometry: tet0=(0,1,2,3) positive, tet1=(1,2,4,3) negative (vol<0).
        Both share face {1,2,3} and their centroids are on opposite sides of
        that face, so this is a geometrically valid mesh pair.
        """
        from core.generator.polymesh_writer import PolyMeshWriter

        vertices = np.array([
            [0.0, 0.0, 0.0],  # 0
            [1.0, 0.0, 0.0],  # 1
            [0.0, 1.0, 0.0],  # 2
            [0.0, 0.0, 1.0],  # 3
            [1.0, 1.0, 1.0],  # 4
        ], dtype=float)
        # tet 0 positive, tet 1 negative (confirmed vol < 0 before normalisation)
        tets = np.array([
            [0, 1, 2, 3],   # positive
            [1, 2, 4, 3],   # negative
        ], dtype=int)

        stats = PolyMeshWriter().write(vertices, tets, tmp_path)
        n_internal = stats["num_internal_faces"]
        n_faces = stats["num_faces"]

        poly_dir = tmp_path / "constant" / "polyMesh"
        faces = _parse_faces_file(poly_dir)
        owners = _parse_labels_file(poly_dir / "owner")
        neighbours = _parse_labels_file(poly_dir / "neighbour")

        # Normalised tets
        from core.generator.polymesh_writer import _normalize_tet_winding
        norm_tets = _normalize_tet_winding(vertices, tets)

        # Internal faces: normal must point toward neighbour
        for i in range(n_internal):
            face = faces[i]
            own_center = vertices[norm_tets[owners[i]]].mean(axis=0)
            nbr_center = vertices[norm_tets[neighbours[i]]].mean(axis=0)
            face_center = vertices[face].mean(axis=0)
            normal = self._face_normal(vertices, face)
            dot = float(np.dot(normal, nbr_center - face_center))
            assert dot > 0, (
                f"Internal face {i}: normal wrong after mixed-orientation fix "
                f"(dot={dot:.6g})"
            )

        # Boundary faces: normal must point outward from owner
        for i in range(n_internal, n_faces):
            face = faces[i]
            own_center = vertices[norm_tets[owners[i]]].mean(axis=0)
            face_center = vertices[face].mean(axis=0)
            normal = self._face_normal(vertices, face)
            dot = float(np.dot(normal, face_center - own_center))
            assert dot > 0, (
                f"Boundary face {i}: normal points inward after mixed-orientation fix "
                f"(dot={dot:.6g})"
            )

    @pytest.mark.skipif(
        not HAS_OPENFOAM,
        reason="OpenFOAM not available",
    )
    @pytest.mark.skipif(
        not Path("tests/benchmarks/sphere.stl").exists(),
        reason="sphere.stl not found",
    )
    def test_checkmesh_no_orientation_errors(self, tmp_path: Path) -> None:
        """Real pytetwild sphere + PolyMeshWriter → checkMesh reports no face
        orientation errors and no negative volumes."""
        try:
            import pytetwild
        except ImportError:
            pytest.skip("pytetwild not installed")

        import trimesh
        from core.generator.polymesh_writer import PolyMeshWriter
        from core.utils.openfoam_utils import run_openfoam

        sphere_path = Path("tests/benchmarks/sphere.stl")
        surf = trimesh.load(str(sphere_path))
        tet_v, tet_f = pytetwild.tetrahedralize(
            surf.vertices,
            surf.faces,
            stop_energy=100.0,
        )

        PolyMeshWriter().write(tet_v, tet_f, tmp_path)

        result = run_openfoam("checkMesh", tmp_path)
        combined = result.stdout + result.stderr

        assert "incorrectly oriented" not in combined, (
            "checkMesh reported face orientation errors"
        )
        assert "negative volume" not in combined.lower() or "0 negative" in combined, (
            "checkMesh reported negative volumes"
        )


# ---------------------------------------------------------------------------
# MMG3D post-processing tests (Task 1)
# ---------------------------------------------------------------------------


class TestMMGPostProcessing:
    """Tests for MMG3D post-processing in Tier2TetWildGenerator."""

    @pytest.fixture()
    def standard_strategy(self) -> MeshStrategy:
        """Standard quality strategy for MMG tests."""
        return MeshStrategy(
            strategy_version=2,
            iteration=1,
            selected_tier="tier2_tetwild",
            fallback_tiers=[],
            flow_type="external",
            quality_level=QualityLevel.STANDARD,
            domain=DomainConfig(
                type="box",
                min=[-1.0, -1.0, -1.0],
                max=[1.0, 1.0, 1.0],
                base_cell_size=0.1,
                location_in_mesh=[0.0, 0.0, 0.0],
            ),
            surface_mesh=SurfaceMeshConfig(
                input_file="sphere.stl",
                target_cell_size=0.05,
                min_cell_size=0.01,
            ),
            boundary_layers=BoundaryLayerConfig(
                enabled=False,
                num_layers=0,
                first_layer_thickness=0.001,
                growth_ratio=1.2,
                max_total_thickness=0.01,
                min_thickness_ratio=0.1,
            ),
            tier_specific_params={"tetwild_stop_energy": 100.0},
        )

    @pytest.fixture()
    def draft_strategy(self) -> MeshStrategy:
        """Draft quality strategy — MMG must NOT run."""
        return MeshStrategy(
            strategy_version=2,
            iteration=1,
            selected_tier="tier2_tetwild",
            fallback_tiers=[],
            flow_type="external",
            quality_level=QualityLevel.DRAFT,
            domain=DomainConfig(
                type="box",
                min=[-1.0, -1.0, -1.0],
                max=[1.0, 1.0, 1.0],
                base_cell_size=0.1,
                location_in_mesh=[0.0, 0.0, 0.0],
            ),
            surface_mesh=SurfaceMeshConfig(
                input_file="sphere.stl",
                target_cell_size=0.05,
                min_cell_size=0.01,
            ),
            boundary_layers=BoundaryLayerConfig(
                enabled=False,
                num_layers=0,
                first_layer_thickness=0.001,
                growth_ratio=1.2,
                max_total_thickness=0.01,
                min_thickness_ratio=0.1,
            ),
            tier_specific_params={"tetwild_stop_energy": 20.0},
        )

    def _mock_pytetwild_run(
        self, strategy: MeshStrategy, stl_path: Path, case_dir: Path, mmg_which_result
    ):
        """Helper: run Tier2 with mocked pytetwild and configurable mmg3d on PATH."""
        import sys
        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        vert = np.array([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        ], dtype=float)
        faces_tri = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=int)
        tet_cells = np.array([[0, 1, 2, 3]], dtype=int)

        mock_surf = MagicMock()
        mock_surf.vertices = vert
        mock_surf.faces = faces_tri

        mock_pytetwild = MagicMock()
        mock_pytetwild.tetrahedralize.return_value = (vert, tet_cells)

        with patch.dict(sys.modules, {"pytetwild": mock_pytetwild}):
            with patch("trimesh.load", return_value=mock_surf):
                with patch("shutil.which", return_value=mmg_which_result):
                    gen = Tier2TetWildGenerator()
                    attempt = gen.run(strategy, stl_path, case_dir)

        return attempt, mock_pytetwild

    def test_mmg_not_run_for_draft_quality(
        self, draft_strategy: MeshStrategy, tmp_path: Path
    ) -> None:
        """Draft quality_level → _run_mmg must NEVER be called even if mmg3d on PATH."""
        import sys
        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        vert = np.array([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        ], dtype=float)
        tet_cells = np.array([[0, 1, 2, 3]], dtype=int)

        mock_surf = MagicMock()
        mock_surf.vertices = vert
        mock_surf.faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])

        mock_pytetwild = MagicMock()
        mock_pytetwild.tetrahedralize.return_value = (vert, tet_cells)

        stl_path = tmp_path / "dummy.stl"
        stl_path.write_text("solid dummy\nendsolid dummy\n")

        mmg_called = []

        gen = Tier2TetWildGenerator()
        original_run_mmg = gen._run_mmg

        def spy_run_mmg(*args, **kwargs):
            mmg_called.append(True)
            return original_run_mmg(*args, **kwargs)

        gen._run_mmg = spy_run_mmg  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"pytetwild": mock_pytetwild}):
            with patch("trimesh.load", return_value=mock_surf):
                # mmg3d is on PATH — but draft should skip it
                with patch("shutil.which", return_value="/usr/bin/mmg3d"):
                    gen.run(draft_strategy, stl_path, tmp_path)

        assert mmg_called == [], "MMG must not run for draft quality"

    def test_mmg_runs_for_standard_quality_when_available(
        self, standard_strategy: MeshStrategy, tmp_path: Path
    ) -> None:
        """Standard quality + mmg3d on PATH → _run_mmg is called once."""
        import sys
        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        vert = np.array([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        ], dtype=float)
        tet_cells = np.array([[0, 1, 2, 3]], dtype=int)

        mock_surf = MagicMock()
        mock_surf.vertices = vert
        mock_surf.faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])

        mock_pytetwild = MagicMock()
        mock_pytetwild.tetrahedralize.return_value = (vert, tet_cells)

        stl_path = tmp_path / "dummy.stl"
        stl_path.write_text("solid dummy\nendsolid dummy\n")

        mmg_call_count = []

        gen = Tier2TetWildGenerator()
        original_run_mmg = gen._run_mmg

        def spy_run_mmg(input_msh, case_dir, strategy):
            mmg_call_count.append(1)
            # Simulate MMG failing gracefully — returns input unchanged
            return input_msh

        gen._run_mmg = spy_run_mmg  # type: ignore[method-assign]

        with patch.dict(sys.modules, {"pytetwild": mock_pytetwild}):
            with patch("trimesh.load", return_value=mock_surf):
                with patch("shutil.which", return_value="/usr/bin/mmg3d"):
                    attempt = gen.run(standard_strategy, stl_path, tmp_path)

        assert sum(mmg_call_count) == 1, "MMG must be called exactly once for standard"
        assert attempt.status == "success"

    def test_mmg_graceful_skip_when_unavailable(
        self, standard_strategy: MeshStrategy, tmp_path: Path
    ) -> None:
        """mmg3d NOT on PATH → pipeline still succeeds without MMG."""
        import sys
        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        vert = np.array([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        ], dtype=float)
        tet_cells = np.array([[0, 1, 2, 3]], dtype=int)

        mock_surf = MagicMock()
        mock_surf.vertices = vert
        mock_surf.faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])

        mock_pytetwild = MagicMock()
        mock_pytetwild.tetrahedralize.return_value = (vert, tet_cells)

        stl_path = tmp_path / "dummy.stl"
        stl_path.write_text("solid dummy\nendsolid dummy\n")

        with patch.dict(sys.modules, {"pytetwild": mock_pytetwild}):
            with patch("trimesh.load", return_value=mock_surf):
                # mmg3d NOT on PATH
                with patch("shutil.which", return_value=None):
                    gen = Tier2TetWildGenerator()
                    attempt = gen.run(standard_strategy, stl_path, tmp_path)

        assert attempt.status == "success", (
            f"Pipeline must succeed without MMG: {attempt.error_message}"
        )
        poly_dir = tmp_path / "constant" / "polyMesh"
        assert poly_dir.is_dir(), "polyMesh directory must be created"

    def test_mmg_msh_to_medit_conversion(self, tmp_path: Path) -> None:
        """_convert_msh_to_medit converts .msh → .mesh Medit format via meshio."""
        import meshio
        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        vert = np.array([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        ], dtype=float)
        tet_cells = np.array([[0, 1, 2, 3]], dtype=int)

        # Write a valid .msh file
        msh_path = tmp_path / "tetwild_result.msh"
        mesh = meshio.Mesh(points=vert, cells=[("tetra", tet_cells)])
        meshio.write(str(msh_path), mesh)

        gen = Tier2TetWildGenerator()
        medit_path = gen._convert_msh_to_medit(msh_path, tmp_path)

        # If meshio supports medit write, the file exists; otherwise returns input
        if medit_path != msh_path:
            assert medit_path.suffix == ".mesh"
            assert medit_path.exists()
        else:
            # Conversion fell back — input returned unchanged
            assert medit_path == msh_path

    def test_mmg_postprocess_when_available(
        self, standard_strategy: MeshStrategy, tmp_path: Path
    ) -> None:
        """Integration: when mmg3d binary is really available, run it on a minimal
        Medit mesh and verify the output path is returned correctly."""
        mmg3d_path = shutil.which("mmg3d")
        if mmg3d_path is None:
            pytest.skip("mmg3d not installed on this system")

        import meshio
        from core.generator.tier2_tetwild import Tier2TetWildGenerator

        vert = np.array([
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        ], dtype=float)
        tet_cells = np.array([[0, 1, 2, 3]], dtype=int)

        msh_path = tmp_path / "tetwild_result.msh"
        mesh = meshio.Mesh(points=vert, cells=[("tetra", tet_cells)])
        meshio.write(str(msh_path), mesh)

        gen = Tier2TetWildGenerator()
        # mesh_strategy fixture is available in this file
        from core.schemas import MeshStrategy, QualityLevel, DomainConfig, SurfaceMeshConfig, BoundaryLayerConfig, QualityTargets
        strategy = MeshStrategy(
            strategy_version=2, iteration=1, quality_level=QualityLevel.STANDARD, selected_tier="auto", fallback_tiers=[], flow_type="external",
            domain=DomainConfig(type="box", min=[-1, -1, -1], max=[1, 1, 1], base_cell_size=0.1, location_in_mesh=[0,0,0]),
            surface_mesh=SurfaceMeshConfig(input_file="test.stl", target_cell_size=0.05, min_cell_size=0.01),
            boundary_layers=BoundaryLayerConfig(enabled=False, num_layers=0, first_layer_thickness=0.0, growth_ratio=1.2, max_total_thickness=0.0, min_thickness_ratio=0.1),
            quality_targets=QualityTargets(max_non_orthogonality=65, max_skewness=4, max_aspect_ratio=100, min_determinant=0.001, target_y_plus=1.0),
            tier_specific_params={}
        )
        result_path = gen._run_mmg(msh_path, tmp_path, strategy)

        # MMG may succeed or fail depending on the mesh size, but must not raise
        assert result_path is not None
        assert isinstance(result_path, Path)

    def test_mmg_params_passed_from_strategy(self, tmp_path: Path) -> None:
        """_run_mmg should use hmin/hmax from strategy.surface_mesh if not in tier_specific_params."""
        from core.generator.tier2_tetwild import Tier2TetWildGenerator
        from core.schemas import MeshStrategy, QualityLevel, DomainConfig, SurfaceMeshConfig, BoundaryLayerConfig, QualityTargets
        import subprocess

        input_msh = tmp_path / "test.msh"
        input_msh.write_text("dummy mesh")
        
        gen = Tier2TetWildGenerator()
        
        strategy = MeshStrategy(
            strategy_version=2, iteration=1, quality_level=QualityLevel.STANDARD, selected_tier="auto", fallback_tiers=[], flow_type="external",
            domain=DomainConfig(type="box", min=[-1, -1, -1], max=[1, 1, 1], base_cell_size=0.1, location_in_mesh=[0,0,0]),
            surface_mesh=SurfaceMeshConfig(input_file="test.stl", target_cell_size=0.05, min_cell_size=0.01),
            boundary_layers=BoundaryLayerConfig(enabled=False, num_layers=0, first_layer_thickness=0.0, growth_ratio=1.2, max_total_thickness=0.0, min_thickness_ratio=0.1),
            quality_targets=QualityTargets(max_non_orthogonality=65, max_skewness=4, max_aspect_ratio=100, min_determinant=0.001, target_y_plus=1.0),
            tier_specific_params={}
        )

        # Mock subprocess.run to capture command line
        captured_cmd = []
        def mock_run(cmd, **kwargs):
            captured_cmd.append(cmd)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=mock_run):
            with patch("shutil.which", return_value="/usr/bin/mmg3d"):
                # meshio.write/read mocks to avoid real file IO issues in unit test
                with patch("meshio.read"), patch("meshio.write"):
                    gen._run_mmg(input_msh, tmp_path, strategy)

        assert len(captured_cmd) > 0, "MMG3D was not called"
        cmd = captured_cmd[0]
        # standard_strategy: min_cell_size=0.01, target_cell_size=0.05
        assert "-hmin" in cmd
        assert str(strategy.surface_mesh.min_cell_size) in cmd
        assert "-hmax" in cmd
        assert str(strategy.surface_mesh.target_cell_size) in cmd
