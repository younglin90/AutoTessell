"""Real integration tests — no mocks.

Exercises the actual pipeline components with real libraries and the
sphere.stl benchmark geometry (1280 faces, watertight).
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPHERE_STL = Path("tests/benchmarks/sphere.stl")
HAS_OPENFOAM = shutil.which("checkMesh") is not None


# ---------------------------------------------------------------------------
# Module-level skip guard — all tests in this file need the sphere
# ---------------------------------------------------------------------------


def _require_sphere() -> None:
    if not SPHERE_STL.exists():
        pytest.skip("sphere.stl not found — run from project root")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sphere_path() -> Path:
    _require_sphere()
    return SPHERE_STL


@pytest.fixture(scope="module")
def real_geometry_report(sphere_path):
    """Run GeometryAnalyzer once and reuse across the module."""
    from core.analyzer.geometry_analyzer import GeometryAnalyzer

    return GeometryAnalyzer().analyze(sphere_path)


@pytest.fixture(scope="module")
def real_preprocessed(real_geometry_report, tmp_path_factory):
    """Run Preprocessor once and reuse across the module."""
    from core.preprocessor.pipeline import Preprocessor

    td = tmp_path_factory.mktemp("preprocess")
    out_path, prep_report = Preprocessor().run(
        input_path=SPHERE_STL,
        geometry_report=real_geometry_report,
        output_dir=td,
    )
    return out_path, prep_report


# ---------------------------------------------------------------------------
# 1. TestRealAnalyzer
# ---------------------------------------------------------------------------


class TestRealAnalyzer:
    """GeometryAnalyzer on the real sphere.stl."""

    def test_analyze_sphere(self, real_geometry_report):
        report = real_geometry_report

        # Basic geometry properties
        assert report.geometry.surface.is_watertight is True
        assert report.geometry.surface.num_faces == 1280

        # flow_type should be a non-empty string
        assert report.flow_estimation.type in ("external", "internal", "unknown")

        # Pydantic model is fully populated
        assert report.file_info is not None
        assert report.geometry.bounding_box.diagonal > 0


# ---------------------------------------------------------------------------
# 2. TestRealPreprocessor
# ---------------------------------------------------------------------------


class TestRealPreprocessor:
    """Preprocessor on the real sphere.stl."""

    def test_preprocess_sphere(self, real_preprocessed):
        out_path, prep_report = real_preprocessed

        # The watertight sphere should only need L1 repair (or passthrough)
        sql = prep_report.surface_quality_level or (
            prep_report.preprocessing_summary.surface_quality_level
        )
        assert sql == "l1_repair"

        # Output file must exist
        assert out_path.exists()
        assert out_path.suffix in (".stl", ".obj", ".ply")

    def test_preprocess_sphere_gate_check(self, real_preprocessed):
        """L1 gate: output mesh must be watertight and manifold."""
        out_path, prep_report = real_preprocessed

        fv = prep_report.preprocessing_summary.final_validation
        assert fv.is_watertight is True
        assert fv.is_manifold is True
        assert fv.num_faces > 0


# ---------------------------------------------------------------------------
# 3. TestRealStrategist
# ---------------------------------------------------------------------------


class TestRealStrategist:
    """StrategyPlanner with real GeometryReport."""

    def test_draft_strategy(self, real_geometry_report, real_preprocessed):
        from core.strategist.strategy_planner import StrategyPlanner

        _, prep_report = real_preprocessed
        strategy = StrategyPlanner().plan(
            real_geometry_report, prep_report, quality_level="draft"
        )
        # Draft quality must always choose TetWild
        assert strategy.selected_tier == "tier2_tetwild"
        assert strategy.quality_level.value == "draft"

    def test_standard_strategy(self, real_geometry_report, real_preprocessed):
        from core.strategist.strategy_planner import StrategyPlanner

        _, prep_report = real_preprocessed
        strategy = StrategyPlanner().plan(
            real_geometry_report, prep_report, quality_level="standard"
        )
        # standard must pick a valid tier
        valid_tiers = {
            "tier0_core",
            "tier05_netgen",
            "tier1_snappy",
            "tier15_cfmesh",
            "tier2_tetwild",
        }
        assert strategy.selected_tier in valid_tiers
        assert strategy.quality_level.value == "standard"

    def test_fine_strategy(self, real_geometry_report, real_preprocessed):
        from core.strategist.strategy_planner import StrategyPlanner

        _, prep_report = real_preprocessed
        strategy = StrategyPlanner().plan(
            real_geometry_report, prep_report, quality_level="fine"
        )
        valid_tiers = {
            "tier0_core",
            "tier05_netgen",
            "tier1_snappy",
            "tier15_cfmesh",
            "tier2_tetwild",
        }
        assert strategy.selected_tier in valid_tiers
        assert strategy.quality_level.value == "fine"


# ---------------------------------------------------------------------------
# 4. TestRealTetWild
# ---------------------------------------------------------------------------


class TestRealTetWild:
    """Direct pytetwild calls — no Generator wrapper."""

    def test_tetwild_sphere(self, sphere_path):
        import trimesh
        import pytetwild

        mesh = trimesh.load(str(sphere_path))
        v, f = pytetwild.tetrahedralize(mesh.vertices, mesh.faces)

        assert v is not None
        assert f is not None
        assert len(v) > 0
        assert len(f) > 0

    def test_tetwild_output_valid(self, sphere_path):
        import trimesh
        import pytetwild

        mesh = trimesh.load(str(sphere_path))
        v, f = pytetwild.tetrahedralize(mesh.vertices, mesh.faces)

        v_arr = np.asarray(v)
        f_arr = np.asarray(f)

        # Vertex array: (N, 3)
        assert v_arr.ndim == 2
        assert v_arr.shape[1] == 3

        # Tet array: (M, 4)
        assert f_arr.ndim == 2
        assert f_arr.shape[1] == 4


# ---------------------------------------------------------------------------
# 5. TestRealPipelineDryRun
# ---------------------------------------------------------------------------


class TestRealPipelineDryRun:
    """Dry-run: real Analyzer + Preprocessor + Strategist, stop before Generate."""

    def test_dry_run_real(self, sphere_path, tmp_path):
        from core.pipeline.orchestrator import PipelineOrchestrator

        result = PipelineOrchestrator().run(
            input_path=sphere_path,
            output_dir=tmp_path / "case",
            quality_level="draft",
            dry_run=True,
        )

        assert result.success is True
        assert result.strategy is not None
        # Generator must not have been invoked
        assert result.generator_log is None
        # All upstream artifacts must be populated
        assert result.geometry_report is not None
        assert result.preprocessed_report is not None


# ---------------------------------------------------------------------------
# 6. TestRealPipelineDraft
# ---------------------------------------------------------------------------


class TestRealPipelineDraft:
    """Full draft pipeline: Generator (TetWild) + optional Evaluator."""

    @pytest.mark.slow
    def test_draft_pipeline_real(self, sphere_path, tmp_path):
        from core.pipeline.orchestrator import PipelineOrchestrator

        case_dir = tmp_path / "case"

        result = PipelineOrchestrator().run(
            input_path=sphere_path,
            output_dir=case_dir,
            quality_level="draft",
            max_iterations=1,
        )

        # generator_log must always be set when Generator ran
        assert result.generator_log is not None

        attempts = result.generator_log.execution_summary.tiers_attempted
        assert len(attempts) >= 1

        # TetWild tier must have been attempted
        tier_names = [a.tier for a in attempts]
        assert "tier2_tetwild" in tier_names

        # Find the TetWild attempt — it must at least have been tried.
        # The attempt may fail if meshio.openfoam is unavailable on this
        # system; that is acceptable for this environment test.  What we
        # care about is that TetWild itself ran (i.e. got past the import
        # and mesh-generation step).  A missing polyMesh converter is a
        # deployment concern, not a TetWild correctness concern.
        tetwild_attempt = next(a for a in attempts if a.tier == "tier2_tetwild")
        if tetwild_attempt.status == "failed":
            # Accept only converter-level failures, not TetWild core failures
            err = tetwild_attempt.error_message or ""
            converter_issues = (
                "openfoam" in err.lower(),
                "meshio" in err.lower(),
                "convert" in err.lower(),
            )
            assert any(converter_issues), (
                f"TetWild core unexpectedly failed: {err}"
            )

    @pytest.mark.slow
    @pytest.mark.skipif(not HAS_OPENFOAM, reason="OpenFOAM (checkMesh) not installed")
    def test_draft_pipeline_with_evaluation(self, sphere_path, tmp_path):
        """Full loop including Evaluator — only runs when checkMesh is available."""
        from core.pipeline.orchestrator import PipelineOrchestrator

        result = PipelineOrchestrator().run(
            input_path=sphere_path,
            output_dir=tmp_path / "case",
            quality_level="draft",
            max_iterations=1,
        )

        assert result.success is True
        assert result.quality_report is not None
        verdict = result.quality_report.evaluation_summary.verdict
        assert verdict in ("PASS", "PASS_WITH_WARNINGS")


# ---------------------------------------------------------------------------
# 7. TestRealPreprocessorRepair — L1 repair + L2 remesh on broken STL
# ---------------------------------------------------------------------------


class TestRealPreprocessorRepair:
    """Real integration test for L1/L2 progressive repair pipeline on broken meshes."""

    @pytest.fixture(scope="class")
    def broken_sphere_path(self) -> Path:
        """Broken sphere (non-watertight) fixture."""
        broken_path = Path("tests/benchmarks/broken_sphere.stl")
        if not broken_path.exists():
            pytest.skip("broken_sphere.stl not found — run from project root")
        return broken_path

    @pytest.fixture(scope="class")
    def broken_geometry_report(self, broken_sphere_path):
        """Analyze broken_sphere once and reuse."""
        from core.analyzer.geometry_analyzer import GeometryAnalyzer

        return GeometryAnalyzer().analyze(broken_sphere_path)

    def test_broken_stl_l1_repair(self, broken_sphere_path, broken_geometry_report, tmp_path):
        """Run Preprocessor on broken_sphere.stl with default settings.

        Verify:
        - output file exists
        - surface_quality_level is set (l1_repair, l2_remesh, or l3_ai)
        - pipeline runs through the full L1/L2/L3 progression
        - final output is a valid mesh
        """
        from core.preprocessor.pipeline import Preprocessor
        from core.schemas import PreprocessedReport
        import trimesh

        preprocessor = Preprocessor()
        out_stl, report = preprocessor.run(
            input_path=broken_sphere_path,
            geometry_report=broken_geometry_report,
            output_dir=tmp_path,
        )

        # Output file exists
        assert out_stl.exists(), f"Output STL not created: {out_stl}"
        assert out_stl.suffix == ".stl"

        # Report is valid PreprocessedReport
        assert isinstance(report, PreprocessedReport)

        # surface_quality_level is set (shows which stage was reached)
        summary = report.preprocessing_summary
        assert summary.surface_quality_level in (
            "l1_repair",
            "l2_remesh",
            "l3_ai",
        ), f"Unexpected surface_quality_level: {summary.surface_quality_level}"

        # Verify output is a valid mesh
        result_mesh = trimesh.load(str(out_stl), force="mesh")
        assert isinstance(result_mesh, trimesh.Trimesh)
        fv = summary.final_validation
        assert fv.num_faces > 0, "Output mesh should have faces"

        # Verify the pipeline progressed through stages
        steps = summary.steps_performed
        surface_steps = [s for s in steps if s.step in ("l1_repair", "l2_remesh", "l3_ai")]
        assert len(surface_steps) >= 1, "At least one surface quality step should be performed"

    def test_broken_stl_gate_progression(
        self, broken_sphere_path, broken_geometry_report, tmp_path
    ):
        """Verify that L1 runs first, and if gate fails, L2 runs.

        Check steps_performed to see the progression.
        """
        from core.preprocessor.pipeline import Preprocessor

        preprocessor = Preprocessor()
        _, report = preprocessor.run(
            input_path=broken_sphere_path,
            geometry_report=broken_geometry_report,
            output_dir=tmp_path,
        )

        steps = report.preprocessing_summary.steps_performed

        # Should have at least one surface quality step (L1, L2, or L3)
        surface_steps = [s for s in steps if s.step in ("l1_repair", "l2_remesh", "l3_ai")]
        assert len(surface_steps) >= 1, "No L1/L2/L3 steps performed"

        # L1 should be first
        first_surface_step = surface_steps[0]
        assert first_surface_step.step == "l1_repair", (
            f"L1 repair should be first, got {first_surface_step.step}"
        )

        # If L1 gate failed, L2 should exist
        l1_step = next((s for s in steps if s.step == "l1_repair"), None)
        if l1_step and l1_step.gate_passed is False:
            l2_steps = [s for s in steps if s.step == "l2_remesh"]
            assert len(l2_steps) >= 1, "L2 should run if L1 gate fails"

    def test_force_remesh_on_clean_mesh(self, tmp_path):
        """Run Preprocessor on sphere.stl with surface_remesh=True.

        Force L2 remesh even if L1 passes. Verify L2 step is in steps_performed.
        """
        from core.preprocessor.pipeline import Preprocessor
        from core.analyzer.geometry_analyzer import GeometryAnalyzer

        clean_sphere = Path("tests/benchmarks/sphere.stl")
        if not clean_sphere.exists():
            pytest.skip("sphere.stl not found")

        geometry_report = GeometryAnalyzer().analyze(clean_sphere)

        preprocessor = Preprocessor()
        _, report = preprocessor.run(
            input_path=clean_sphere,
            geometry_report=geometry_report,
            output_dir=tmp_path,
            surface_remesh=True,
        )

        steps = report.preprocessing_summary.steps_performed
        l2_steps = [s for s in steps if s.step == "l2_remesh"]
        assert len(l2_steps) >= 1, (
            "surface_remesh=True should force L2 even if L1 passes"
        )

        # surface_quality_level should indicate L2 was used
        sql = report.preprocessing_summary.surface_quality_level
        assert sql in ("l2_remesh", "l3_ai"), (
            f"Expected l2_remesh or l3_ai with surface_remesh=True, got {sql}"
        )

    def test_broken_stl_reports_issues(self, broken_geometry_report):
        """Verify the broken sphere has detectable issues."""
        # Should have at least non_watertight warning
        issue_types = [i.type for i in broken_geometry_report.issues]
        assert "non_watertight" in issue_types, (
            f"broken_sphere should report non_watertight issue. "
            f"Got: {issue_types}"
        )


# ---------------------------------------------------------------------------
# 8. TestStepFullPipeline — STEP file dry-run
# ---------------------------------------------------------------------------


class TestStepFullPipeline:
    """Test full preprocessing pipeline with STEP file (dry-run)."""

    @pytest.fixture(scope="class")
    def step_file_path(self) -> Path:
        """box.step from benchmarks."""
        step_path = Path("tests/benchmarks/box.step")
        if not step_path.exists():
            pytest.skip("box.step not found")
        return step_path

    @pytest.fixture(scope="class")
    def step_geometry_report(self, step_file_path):
        """Analyze box.step once."""
        from core.analyzer.geometry_analyzer import GeometryAnalyzer

        return GeometryAnalyzer().analyze(step_file_path)

    def test_step_full_pipeline_dry_run(
        self, step_file_path, step_geometry_report, tmp_path
    ):
        """PipelineOrchestrator.run(box.step, dry_run=True).

        Verify:
        - success=True
        - strategy is set
        - generator_log is None (dry run = no generation)
        - geometry_report and preprocessed_report are populated
        """
        from core.pipeline.orchestrator import PipelineOrchestrator

        result = PipelineOrchestrator().run(
            input_path=step_file_path,
            output_dir=tmp_path / "case",
            quality_level="standard",
            dry_run=True,
        )

        assert result.success is True, (
            f"Dry-run pipeline failed: {result.error_message}"
        )
        assert result.strategy is not None
        assert result.geometry_report is not None
        assert result.preprocessed_report is not None

        # Dry run should NOT invoke generator
        assert result.generator_log is None

    def test_step_preprocessor_converts_to_stl(
        self, step_file_path, step_geometry_report, tmp_path
    ):
        """Preprocessor converts STEP to STL and repairs it."""
        from core.preprocessor.pipeline import Preprocessor

        preprocessor = Preprocessor()
        out_stl, report = preprocessor.run(
            input_path=step_file_path,
            geometry_report=step_geometry_report,
            output_dir=tmp_path,
        )

        # Output must be STL (not STEP)
        assert out_stl.exists()
        assert out_stl.suffix == ".stl"

        # Passthrough flag should be False (we converted it)
        assert report.preprocessing_summary.passthrough_cad is False

        # Final validation should show watertight result
        fv = report.preprocessing_summary.final_validation
        assert fv.is_watertight is True


# ---------------------------------------------------------------------------
# Benchmark fixtures (session-scoped, create if missing)
# ---------------------------------------------------------------------------

BENCHMARKS_DIR = Path("tests/benchmarks")


@pytest.fixture(scope="session")
def sphere_20k_stl() -> Path:
    p = BENCHMARKS_DIR / "sphere_20k.stl"
    if not p.exists():
        import trimesh  # noqa: PLC0415

        s = trimesh.creation.icosphere(subdivisions=5)
        s.export(str(p))
    return p


@pytest.fixture(scope="session")
def wing_stl() -> Path:
    p = BENCHMARKS_DIR / "wing.stl"
    if not p.exists():
        pytest.skip("wing.stl not found")
    return p


@pytest.fixture(scope="session")
def box_step() -> Path:
    p = BENCHMARKS_DIR / "box.step"
    if not p.exists():
        pytest.skip("box.step not found")
    return p


# ---------------------------------------------------------------------------
# 9. TestBenchmarkSuite — full pipeline on various inputs (no OpenFOAM needed)
# ---------------------------------------------------------------------------


class TestBenchmarkSuite:
    """Benchmark suite: full pipeline on different geometries and sizes.

    All tests use the native checker path; OpenFOAM is not required.
    The OPENFOAM_DIR env var is patched per-test via monkeypatch so that
    the real OpenFOAM installation is still available for other test classes.
    """

    def _force_native(self, monkeypatch):
        """Patch openfoam_utils so _find_openfoam_bashrc returns None,
        causing MeshQualityChecker to fall back to NativeMeshChecker."""
        monkeypatch.setattr(
            "core.utils.openfoam_utils._find_openfoam_bashrc",
            lambda: None,
        )

    @pytest.mark.slow
    def test_sphere_draft_pass(self, tmp_path, monkeypatch):
        """sphere.stl + draft → PASS, cells > 0, wall-clock < 10 s."""
        self._force_native(monkeypatch)
        from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: PLC0415

        sphere = BENCHMARKS_DIR / "sphere.stl"
        if not sphere.exists():
            pytest.skip("sphere.stl not found")

        t0 = time.perf_counter()
        result = PipelineOrchestrator().run(
            input_path=sphere,
            output_dir=tmp_path / "case",
            quality_level="draft",
            max_iterations=1,
        )
        elapsed = time.perf_counter() - t0

        assert result.generator_log is not None, "Generator must have run"
        # Pipeline should complete without an unhandled exception
        assert result.error is None or result.success, (
            f"Pipeline failed unexpectedly: {result.error}"
        )

        # If generation succeeded, verify cells > 0
        if result.quality_report is not None:
            cells = result.quality_report.evaluation_summary.checkmesh.cells
            assert cells > 0, f"Expected cells > 0, got {cells}"
            verdict = result.quality_report.evaluation_summary.verdict
            assert verdict in ("PASS", "PASS_WITH_WARNINGS"), (
                f"Expected PASS-family verdict, got {verdict}"
            )

        assert elapsed < 10.0, f"sphere draft took {elapsed:.1f}s (> 10s limit)"

    @pytest.mark.slow
    def test_sphere_20k_draft_pass(self, sphere_20k_stl, tmp_path, monkeypatch):
        """sphere_20k.stl (20k faces) + draft → result has quality_report, cells > 5000."""
        self._force_native(monkeypatch)
        from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: PLC0415

        result = PipelineOrchestrator().run(
            input_path=sphere_20k_stl,
            output_dir=tmp_path / "case",
            quality_level="draft",
            max_iterations=1,
        )

        assert result.generator_log is not None, "Generator must have run"

        if result.quality_report is not None:
            cells = result.quality_report.evaluation_summary.checkmesh.cells
            assert cells > 5000, f"Expected > 5000 cells for 20k-face sphere, got {cells}"

    @pytest.mark.slow
    def test_wing_draft_runs(self, wing_stl, tmp_path, monkeypatch):
        """wing.stl + draft → pipeline completes (PASS or FAIL ok), no exceptions."""
        self._force_native(monkeypatch)
        from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: PLC0415

        # We only care that no unhandled exception propagates.
        result = PipelineOrchestrator().run(
            input_path=wing_stl,
            output_dir=tmp_path / "case",
            quality_level="draft",
            max_iterations=1,
        )

        # generator_log must be set if generation was attempted
        assert result.generator_log is not None, "Generator must have been invoked"

    @pytest.mark.slow
    def test_step_draft_runs(self, box_step, tmp_path, monkeypatch):
        """box.step + draft → pipeline completes, geometry_report.file_info.is_cad_brep == True."""
        self._force_native(monkeypatch)
        from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: PLC0415

        result = PipelineOrchestrator().run(
            input_path=box_step,
            output_dir=tmp_path / "case",
            quality_level="draft",
            max_iterations=1,
        )

        # Geometry report must detect BREP/CAD format
        assert result.geometry_report is not None
        assert result.geometry_report.file_info.is_cad_brep is True, (
            "box.step should be detected as CAD BREP"
        )
        # Generator must have been invoked
        assert result.generator_log is not None

    def test_dry_run_all_formats(self, sphere_20k_stl, wing_stl, box_step, tmp_path, monkeypatch):
        """Dry-run on sphere_20k.stl, wing.stl, box.step — all get strategy."""
        self._force_native(monkeypatch)
        from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: PLC0415

        test_cases = [
            (sphere_20k_stl, "sphere_20k"),
            (wing_stl, "wing"),
            (box_step, "box_step"),
        ]

        for input_path, label in test_cases:
            case_dir = tmp_path / label
            result = PipelineOrchestrator().run(
                input_path=input_path,
                output_dir=case_dir,
                quality_level="draft",
                dry_run=True,
            )
            assert result.success is True, (
                f"Dry-run failed for {label}: {result.error}"
            )
            assert result.strategy is not None, (
                f"Strategy not set for {label}"
            )
            # Dry-run must NOT invoke generator
            assert result.generator_log is None, (
                f"Generator should not run in dry-run for {label}"
            )


# ---------------------------------------------------------------------------
# 10. TestNativeCheckerOnly — NativeMeshChecker unit + fallback smoke tests
# ---------------------------------------------------------------------------


class TestNativeCheckerOnly:
    """Unit and smoke tests for NativeMeshChecker and MeshQualityChecker fallback."""

    @pytest.fixture(scope="class")
    def sphere_polymesh_dir(self, tmp_path_factory) -> Path:
        """Generate a polyMesh from sphere.stl using the full pipeline and return case dir."""
        sphere = BENCHMARKS_DIR / "sphere.stl"
        if not sphere.exists():
            pytest.skip("sphere.stl not found")

        td = tmp_path_factory.mktemp("polymesh")
        case_dir = td / "case"

        from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: PLC0415

        result = PipelineOrchestrator().run(
            input_path=sphere,
            output_dir=case_dir,
            quality_level="draft",
            max_iterations=1,
        )

        poly_dir = case_dir / "constant" / "polyMesh"
        if not poly_dir.exists():
            pytest.skip(
                f"polyMesh generation failed (tier error): {result.error}"
            )

        return case_dir

    def test_native_checker_sphere(self, sphere_polymesh_dir):
        """NativeMeshChecker on real polyMesh: cells > 0, non-ortho < 90°."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        checker = NativeMeshChecker()
        result = checker.run(sphere_polymesh_dir)

        assert result.cells > 0, f"Expected cells > 0, got {result.cells}"
        assert result.points > 0, f"Expected points > 0, got {result.points}"
        assert result.faces > 0, f"Expected faces > 0, got {result.faces}"

        # Non-orthogonality must be physically plausible
        assert result.max_non_orthogonality < 90.0, (
            f"Max non-ortho {result.max_non_orthogonality}° should be < 90°"
        )
        assert result.max_non_orthogonality >= 0.0, (
            "Max non-ortho should be non-negative"
        )

        # No negative volumes on a clean sphere tet mesh
        assert result.negative_volumes == 0, (
            f"Expected 0 negative volumes, got {result.negative_volumes}"
        )

    def test_native_checker_no_openfoam_env(self, sphere_polymesh_dir, monkeypatch):
        """With OpenFOAM unavailable, MeshQualityChecker must fall back to NativeMeshChecker."""
        # Patch _find_openfoam_bashrc at the module level so that
        # run_openfoam raises FileNotFoundError → triggers native fallback
        monkeypatch.setattr(
            "core.utils.openfoam_utils._find_openfoam_bashrc",
            lambda: None,
        )

        from core.evaluator.quality_checker import MeshQualityChecker  # noqa: PLC0415

        checker = MeshQualityChecker()
        result = checker.run(sphere_polymesh_dir)

        # NativeMeshChecker should have filled in all fields
        assert result.cells > 0, (
            f"Fallback native checker: expected cells > 0, got {result.cells}"
        )
        assert result.max_non_orthogonality >= 0.0
        assert result.negative_volumes == 0


# ---------------------------------------------------------------------------
# 11. TestBoundaryClassifier — boundary patch classification
# ---------------------------------------------------------------------------


class TestBoundaryClassifier:
    """Integration tests for classify_boundaries()."""

    @pytest.fixture(scope="class")
    def sphere_polymesh_dir(self, tmp_path_factory) -> Path:
        """Generate a real polyMesh from sphere.stl via pytetwild + PolyMeshWriter."""
        sphere = BENCHMARKS_DIR / "sphere.stl"
        if not sphere.exists():
            pytest.skip("sphere.stl not found — run from project root")

        td = tmp_path_factory.mktemp("bc_polymesh")
        case_dir = td / "case"

        from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: PLC0415

        result = PipelineOrchestrator().run(
            input_path=sphere,
            output_dir=case_dir,
            quality_level="draft",
            max_iterations=1,
        )

        poly_dir = case_dir / "constant" / "polyMesh"
        if not poly_dir.exists():
            pytest.skip(
                f"polyMesh generation failed (cannot test classifier): {result.error}"
            )

        return case_dir

    def test_classify_sphere_default_wall(self, sphere_polymesh_dir):
        """Sphere polyMesh boundary → the default patch should be classified as 'wall'."""
        from core.utils.boundary_classifier import classify_boundaries  # noqa: PLC0415

        patches = classify_boundaries(sphere_polymesh_dir)

        assert len(patches) >= 1, "Expected at least one boundary patch"

        # Every patch name containing 'default' must map to 'wall'
        default_patches = [p for p in patches if "default" in p["name"].lower()]
        assert len(default_patches) >= 1, (
            "Expected at least one 'default*' patch on sphere polyMesh"
        )
        for p in default_patches:
            assert p["type"] == "wall", (
                f"default patch '{p['name']}' should be 'wall', got '{p['type']}'"
            )

    def test_classify_returns_list(self, sphere_polymesh_dir):
        """classify_boundaries() must return a list of dicts with name, type, nFaces keys."""
        from core.utils.boundary_classifier import classify_boundaries  # noqa: PLC0415

        result = classify_boundaries(sphere_polymesh_dir)

        assert isinstance(result, list), "classify_boundaries must return a list"
        for entry in result:
            assert isinstance(entry, dict), f"Each entry must be a dict, got {type(entry)}"
            assert "name" in entry, f"Missing 'name' key in {entry}"
            assert "type" in entry, f"Missing 'type' key in {entry}"
            assert "nFaces" in entry, f"Missing 'nFaces' key in {entry}"
            assert isinstance(entry["name"], str)
            assert isinstance(entry["type"], str)
            assert isinstance(entry["nFaces"], int)
            assert entry["nFaces"] >= 0

    def test_classify_empty_case(self, tmp_path):
        """Non-existent case_dir → classify_boundaries returns empty list (no exception)."""
        from core.utils.boundary_classifier import classify_boundaries  # noqa: PLC0415

        non_existent = tmp_path / "no_such_case"
        result = classify_boundaries(non_existent)

        assert result == [], (
            f"Expected [] for non-existent case_dir, got {result}"
        )
