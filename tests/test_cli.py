"""CLI 인터페이스 테스트 — click.testing.CliRunner 기반, 실제 파이프라인 실행 없음."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli.main import cli


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sphere_stl(tmp_path: Path) -> Path:
    """단순한 ASCII STL 파일 (실제 파이프라인 없이 경로 존재 확인용)."""
    stl = tmp_path / "sphere.stl"
    stl.write_text(
        "solid sphere\n"
        "  facet normal 0 0 1\n"
        "    outer loop\n"
        "      vertex 0 0 0\n"
        "      vertex 1 0 0\n"
        "      vertex 0 1 0\n"
        "    endloop\n"
        "  endfacet\n"
        "endsolid sphere\n"
    )
    return stl


# ---------------------------------------------------------------------------
# 1. 최상위 그룹 --help
# ---------------------------------------------------------------------------


class TestCLIHelp:
    def test_root_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Auto-Tessell" in result.output

    def test_root_help_shows_subcommands(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        for cmd in ("run", "analyze", "preprocess", "strategize", "generate", "evaluate"):
            assert cmd in result.output

    def test_run_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "파이프라인" in result.output or "pipeline" in result.output.lower() or "input_file" in result.output.lower() or "INPUT_FILE" in result.output

    def test_analyze_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "analyze" in result.output.lower() or "INPUT_FILE" in result.output

    def test_preprocess_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["preprocess", "--help"])
        assert result.exit_code == 0
        assert "INPUT_FILE" in result.output

    def test_strategize_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["strategize", "--help"])
        assert result.exit_code == 0
        assert "geometry-report" in result.output

    def test_generate_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0
        assert "strategy" in result.output

    def test_evaluate_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["evaluate", "--help"])
        assert result.exit_code == 0
        assert "case" in result.output

    def test_export_vtk_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["export-vtk", "--help"])
        assert result.exit_code == 0
        assert "CASE_DIR" in result.output or "case_dir" in result.output.lower() or "vtu" in result.output.lower() or "VTK" in result.output


# ---------------------------------------------------------------------------
# 2. 전역 플래그
# ---------------------------------------------------------------------------


class TestGlobalFlags:
    def test_verbose_flag_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert "--verbose" in result.output or "-v" in result.output

    def test_json_log_flag_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert "--json-log" in result.output

    def test_verbose_short_flag(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert "-v" in result.output


# ---------------------------------------------------------------------------
# 3. run 서브커맨드 옵션 검증 (--help 기반)
# ---------------------------------------------------------------------------


class TestRunOptions:
    def test_quality_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--quality" in result.output

    def test_quality_choices_shown(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "draft" in result.output
        assert "standard" in result.output
        assert "fine" in result.output

    def test_tier_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--tier" in result.output

    def test_tier_choices_shown(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "auto" in result.output
        assert "netgen" in result.output

    def test_output_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--output" in result.output or "-o" in result.output

    def test_dry_run_flag_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--dry-run" in result.output

    def test_element_size_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--element-size" in result.output

    def test_verbose_mesh_flag_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--verbose-mesh" in result.output

    def test_no_repair_flag_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--no-repair" in result.output

    def test_max_iterations_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--max-iterations" in result.output

    def test_profile_flag_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--profile" in result.output

    def test_polyhedral_flag_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--polyhedral" in result.output

    def test_export_vtk_flag_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--export-vtk" in result.output

    def test_parallel_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--parallel" in result.output

    def test_bl_layers_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--bl-layers" in result.output

    def test_max_cells_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--max-cells" in result.output

    def test_repair_engine_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--repair-engine" in result.output

    def test_volume_engine_option_exists(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert "--volume-engine" in result.output


# ---------------------------------------------------------------------------
# 4. run — 잘못된 인수 / 없는 파일
# ---------------------------------------------------------------------------


class TestRunErrors:
    def test_run_missing_input_file(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["run", str(tmp_path / "nonexistent.stl")])
        assert result.exit_code != 0

    def test_run_invalid_quality(self, runner: CliRunner, sphere_stl: Path):
        result = runner.invoke(cli, ["run", str(sphere_stl), "--quality", "ultra"])
        assert result.exit_code != 0

    def test_run_invalid_tier(self, runner: CliRunner, sphere_stl: Path):
        result = runner.invoke(cli, ["run", str(sphere_stl), "--tier", "invalid_engine"])
        assert result.exit_code != 0

    def test_analyze_missing_file(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["analyze", str(tmp_path / "ghost.stl")])
        assert result.exit_code != 0

    def test_preprocess_missing_file(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["preprocess", str(tmp_path / "ghost.stl")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 5. run --dry-run (파이프라인 모킹)
# ---------------------------------------------------------------------------


def _make_mock_pipeline_result(dry_run: bool = True) -> MagicMock:
    """PipelineOrchestrator.run() 의 반환값 모의 객체."""
    result = MagicMock()
    result.success = True
    result.error = None
    result.iterations = 1
    result.total_time_seconds = 0.1
    result.boundary_patches = []
    result.quality_report = None
    result.generator_log = None

    # strategy mock
    strategy = MagicMock()
    strategy.selected_tier = "tetwild"
    strategy.fallback_tiers = []
    strategy.quality_level = "draft"
    strategy.flow_type = "external"
    strategy.surface_mesh = MagicMock(target_cell_size=0.05)
    strategy.domain = MagicMock(
        base_cell_size=0.1,
        min=[0.0, 0.0, 0.0],
        max=[1.0, 1.0, 1.0],
    )
    strategy.boundary_layers = MagicMock(enabled=False, num_layers=0)
    strategy.tier_specific_params = {}

    result.strategy = strategy
    result.geometry_report = None
    return result


class TestRunDryRun:
    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_dry_run_exits_zero(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result(dry_run=True)
        result = runner.invoke(
            cli,
            ["run", str(sphere_stl), "--dry-run", "--output", str(tmp_path / "case")],
        )
        assert result.exit_code == 0

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_dry_run_prints_dry_run_message(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result(dry_run=True)
        result = runner.invoke(
            cli,
            ["run", str(sphere_stl), "--dry-run", "--output", str(tmp_path / "case")],
        )
        assert "Dry-run" in result.output or "dry-run" in result.output.lower() or "전략" in result.output

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_dry_run_quality_draft(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result(dry_run=True)
        result = runner.invoke(
            cli,
            [
                "run", str(sphere_stl),
                "--dry-run", "--quality", "draft",
                "--output", str(tmp_path / "case"),
            ],
        )
        assert result.exit_code == 0
        _, kwargs = mock_run.call_args
        assert kwargs.get("quality_level") == "draft"

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_dry_run_quality_fine(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result(dry_run=True)
        result = runner.invoke(
            cli,
            [
                "run", str(sphere_stl),
                "--dry-run", "--quality", "fine",
                "--output", str(tmp_path / "case"),
            ],
        )
        assert result.exit_code == 0

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_dry_run_no_repair_flag(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result(dry_run=True)
        result = runner.invoke(
            cli,
            [
                "run", str(sphere_stl),
                "--dry-run", "--no-repair",
                "--output", str(tmp_path / "case"),
            ],
        )
        assert result.exit_code == 0
        _, kwargs = mock_run.call_args
        assert kwargs.get("no_repair") is True

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_dry_run_element_size(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result(dry_run=True)
        result = runner.invoke(
            cli,
            [
                "run", str(sphere_stl),
                "--dry-run", "--element-size", "0.05",
                "--output", str(tmp_path / "case"),
            ],
        )
        assert result.exit_code == 0
        _, kwargs = mock_run.call_args
        assert kwargs.get("element_size") == pytest.approx(0.05)

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_dry_run_tier_netgen(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result(dry_run=True)
        result = runner.invoke(
            cli,
            [
                "run", str(sphere_stl),
                "--dry-run", "--tier", "netgen",
                "--output", str(tmp_path / "case"),
            ],
        )
        assert result.exit_code == 0
        _, kwargs = mock_run.call_args
        assert kwargs.get("tier_hint") == "netgen"

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_dry_run_max_iterations(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result(dry_run=True)
        result = runner.invoke(
            cli,
            [
                "run", str(sphere_stl),
                "--dry-run", "--max-iterations", "5",
                "--output", str(tmp_path / "case"),
            ],
        )
        assert result.exit_code == 0
        _, kwargs = mock_run.call_args
        assert kwargs.get("max_iterations") == 5

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_dry_run_verbose_flag(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result(dry_run=True)
        result = runner.invoke(
            cli,
            [
                "--verbose",
                "run", str(sphere_stl),
                "--dry-run",
                "--output", str(tmp_path / "case"),
            ],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 6. run 성공 시나리오
# ---------------------------------------------------------------------------


class TestRunSuccess:
    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_run_success_exit_zero(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result()
        result = runner.invoke(
            cli,
            ["run", str(sphere_stl), "--output", str(tmp_path / "case")],
        )
        assert result.exit_code == 0

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_run_failure_exit_nonzero(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        fail_result = MagicMock()
        fail_result.success = False
        fail_result.error = "TetWild failed"
        fail_result.iterations = 1
        fail_result.total_time_seconds = 0.5
        fail_result.boundary_patches = []
        fail_result.quality_report = None
        fail_result.generator_log = None
        fail_result.strategy = None
        fail_result.geometry_report = None
        mock_run.return_value = fail_result

        result = runner.invoke(
            cli,
            ["run", str(sphere_stl), "--output", str(tmp_path / "case")],
        )
        assert result.exit_code != 0

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_run_prints_input_output_paths(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result()
        output_dir = tmp_path / "mycase"
        result = runner.invoke(
            cli,
            ["run", str(sphere_stl), "--output", str(output_dir)],
        )
        assert result.exit_code == 0
        assert str(sphere_stl) in result.output or sphere_stl.name in result.output

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_run_volume_engine_overrides_tier(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result()
        result = runner.invoke(
            cli,
            [
                "run", str(sphere_stl),
                "--volume-engine", "netgen",
                "--output", str(tmp_path / "case"),
            ],
        )
        assert result.exit_code == 0
        _, kwargs = mock_run.call_args
        assert kwargs.get("tier_hint") == "netgen"

    @patch("core.pipeline.orchestrator.PipelineOrchestrator.run")
    @patch("core.utils.logging.configure_logging")
    def test_run_repair_engine_none_sets_no_repair(
        self,
        mock_log: MagicMock,
        mock_run: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
        tmp_path: Path,
    ):
        mock_run.return_value = _make_mock_pipeline_result()
        result = runner.invoke(
            cli,
            [
                "run", str(sphere_stl),
                "--repair-engine", "none",
                "--output", str(tmp_path / "case"),
            ],
        )
        assert result.exit_code == 0
        _, kwargs = mock_run.call_args
        assert kwargs.get("no_repair") is True


# ---------------------------------------------------------------------------
# 7. analyze 서브커맨드 (모킹)
# ---------------------------------------------------------------------------


class TestAnalyzeCommand:
    @patch("core.analyzer.geometry_analyzer.GeometryAnalyzer.analyze")
    @patch("core.utils.logging.configure_logging")
    def test_analyze_dry_run(
        self,
        mock_log: MagicMock,
        mock_analyze: MagicMock,
        runner: CliRunner,
        sphere_stl: Path,
    ):
        # model_dump_json 호출을 직접 모킹하여 Pydantic 스키마 의존성 제거
        fake_report = MagicMock()
        fake_report.model_dump_json.return_value = '{"file_info": {}, "geometry": {}, "flow_estimation": {"type": "external"}, "issues": []}'
        mock_analyze.return_value = fake_report

        result = runner.invoke(cli, ["analyze", str(sphere_stl), "--dry-run"])
        assert result.exit_code == 0

    def test_analyze_missing_file(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(cli, ["analyze", str(tmp_path / "no_such.stl")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 8. 서브커맨드 존재 확인
# ---------------------------------------------------------------------------


class TestSubcommandsExist:
    @pytest.mark.parametrize(
        "cmd",
        ["run", "analyze", "preprocess", "strategize", "generate", "evaluate", "export-vtk", "interactive"],
    )
    def test_subcommand_exists(self, runner: CliRunner, cmd: str):
        result = runner.invoke(cli, [cmd, "--help"])
        # '--help'는 항상 exit_code 0 이어야 함
        assert result.exit_code == 0, f"Subcommand '{cmd}' --help failed: {result.output}"
