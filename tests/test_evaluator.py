"""Evaluator 모듈 테스트.

checkMesh를 실제 실행하지 않고 파싱/판정 로직만 검증한다.
OpenFOAM, pyvista 없이도 모든 테스트가 통과해야 한다.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from core.evaluator.quality_checker import CheckMeshParser
from core.evaluator.report import EvaluationReporter, get_thresholds
from core.schemas import (
    AdditionalMetrics,
    BoundaryLayerStats,
    CheckMeshResult,
    CellVolumeStats,
    GeometryFidelity,
    QualityReport,
    Verdict,
)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_checkmesh(
    *,
    cells: int = 100000,
    faces: int = 300000,
    points: int = 150000,
    max_non_orthogonality: float = 30.0,
    avg_non_orthogonality: float = 5.0,
    max_skewness: float = 1.5,
    max_aspect_ratio: float = 20.0,
    min_face_area: float = 1e-8,
    min_cell_volume: float = 1e-12,
    min_determinant: float = 0.5,
    negative_volumes: int = 0,
    severely_non_ortho_faces: int = 0,
    failed_checks: int = 0,
    mesh_ok: bool = True,
) -> CheckMeshResult:
    return CheckMeshResult(
        cells=cells,
        faces=faces,
        points=points,
        max_non_orthogonality=max_non_orthogonality,
        avg_non_orthogonality=avg_non_orthogonality,
        max_skewness=max_skewness,
        max_aspect_ratio=max_aspect_ratio,
        min_face_area=min_face_area,
        min_cell_volume=min_cell_volume,
        min_determinant=min_determinant,
        negative_volumes=negative_volumes,
        severely_non_ortho_faces=severely_non_ortho_faces,
        failed_checks=failed_checks,
        mesh_ok=mesh_ok,
    )


def _make_report(
    checkmesh: CheckMeshResult,
    metrics: AdditionalMetrics | None = None,
    quality_level: str = "standard",
    geometry_fidelity: GeometryFidelity | None = None,
) -> QualityReport:
    reporter = EvaluationReporter()
    return reporter.evaluate(
        checkmesh=checkmesh,
        strategy=None,
        metrics=metrics or AdditionalMetrics(),
        geometry_fidelity=geometry_fidelity,
        iteration=1,
        tier="test_tier",
        elapsed=1.0,
        quality_level=quality_level,
    )


# ---------------------------------------------------------------------------
# checkMesh 파싱 테스트
# ---------------------------------------------------------------------------

_CHECKMESH_OK_STDOUT = """\
Create time

Create polyMesh for time = 0

Time = 0

Mesh stats
    points:           2567890
    internal points:  0
    faces:            3890123
    internal faces:   3456789
    cells:            1245678
    faces per cell:   5.34
    boundary patches: 6
    point zones:      0
    face zones:       0
    cell zones:       0

Overall number of cells of each type:
    hexahedra:     876543
    prisms:        0
    wedges:        0
    pyramids:      0
    tet wedges:    0
    tetrahedra:    369135
    polyhedra:     0

Checking topology...
    Boundary definition OK.
    Cell to face addressing OK.
    Point usage OK.
    Upper triangular ordering OK.
    Face vertices OK.
    Number of regions: 1 (OK).

Checking patch topology for multiply connected surfaces...
    Patch Faces    Points   Surface topology
    inlet      100    120    ok (non-closed singly connected)
    outlet     100    120    ok (non-closed singly connected)
    walls      5000   5200   ok (non-closed singly connected)

Checking geometry...
    Overall domain bounding box (0 0 0) (1 1 1)
    Mesh (non-empty, non-wedge) directions (1 1 1)
    Mesh (non-empty) directions (1 1 1)
    All edges aligned with or perpendicular to non-empty directions.
    Boundary openness (2.1e-17 -3.4e-17 1.2e-17) OK.
    Max cell openness = 3.4e-16 OK.
    Max aspect ratio = 45.6 OK.
    Minimum face area = 1.2e-10. Maximum face area = 8.5e-05.  Face area magnitudes OK.
    Min volume = 3.4e-15. Max volume = 8.0e-09.  Total volume = 1.0.  Cell volumes OK.
    Mesh non-orthogonality Max: 62.3 average: 8.7
    *Number of severely non-orthogonal (> 70 degrees) faces: 0.
    Non-orthogonality check OK.
    Face pyramids OK.
    Max skewness = 3.2 OK.
    Coupled point location match (average 0) OK.
    Min determinant = 0.012 OK.

Mesh OK.
"""


_CHECKMESH_FAIL_STDOUT = """\
Mesh stats
    points:           100000
    faces:            200000
    internal faces:   150000
    cells:            50000

Checking geometry...
    Max aspect ratio = 12.0 OK.
    Minimum face area = 5e-9.
    Min volume = 2e-10. Max volume = 1e-6.
    Mesh non-orthogonality Max: 73.2 average: 12.1
    *Number of severely non-orthogonal (> 70 degrees) faces: 142.
    Max skewness = 2.1 OK.
    Min determinant = 0.05 OK.

***Error: 5 negative volumes
Failed 2 mesh checks.
"""


class TestCheckMeshParser:
    def setup_method(self) -> None:
        self.parser = CheckMeshParser()

    def test_parse_checkmesh_pass(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert result.mesh_ok is True

    def test_parse_checkmesh_fail(self) -> None:
        result = self.parser.parse(_CHECKMESH_FAIL_STDOUT)
        assert result.mesh_ok is False
        assert result.failed_checks == 2

    def test_parse_cells(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert result.cells == 1245678

    def test_parse_faces(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert result.faces == 3890123

    def test_parse_points(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert result.points == 2567890

    def test_parse_non_ortho(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert abs(result.max_non_orthogonality - 62.3) < 0.01
        assert abs(result.avg_non_orthogonality - 8.7) < 0.01

    def test_parse_skewness(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert abs(result.max_skewness - 3.2) < 0.01

    def test_parse_negative_volumes(self) -> None:
        result = self.parser.parse(_CHECKMESH_FAIL_STDOUT)
        assert result.negative_volumes == 5

    def test_parse_aspect_ratio(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert abs(result.max_aspect_ratio - 45.6) < 0.01

    def test_parse_min_face_area(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert result.min_face_area == pytest.approx(1.2e-10)

    def test_parse_min_volume(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert result.min_cell_volume == pytest.approx(3.4e-15)

    def test_parse_min_determinant(self) -> None:
        result = self.parser.parse(_CHECKMESH_OK_STDOUT)
        assert result.min_determinant == pytest.approx(0.012)

    def test_parse_severely_non_ortho_faces(self) -> None:
        result = self.parser.parse(_CHECKMESH_FAIL_STDOUT)
        assert result.severely_non_ortho_faces == 142

    def test_parse_empty_stdout(self) -> None:
        result = self.parser.parse("")
        assert result.cells == 0
        assert result.mesh_ok is False

    def test_parse_mesh_ok_sets_flag(self) -> None:
        stdout = "Mesh OK.\n"
        result = self.parser.parse(stdout)
        assert result.mesh_ok is True

    def test_failed_checks_overrides_mesh_ok(self) -> None:
        stdout = "Mesh OK.\nFailed 1 mesh checks.\n"
        result = self.parser.parse(stdout)
        assert result.mesh_ok is False
        assert result.failed_checks == 1


# ---------------------------------------------------------------------------
# 판정 로직 테스트 (standard 기본 동작 — 기존 테스트 유지)
# ---------------------------------------------------------------------------

class TestEvaluationVerdict:
    def test_hard_fail_non_ortho(self) -> None:
        """max_non_orthogonality > 70 → Hard FAIL (standard)."""
        cm = _make_checkmesh(max_non_orthogonality=75.0)
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.FAIL
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "max_non_orthogonality" in hard_criteria

    def test_hard_fail_negative_volumes(self) -> None:
        """negative_volumes > 0 → Hard FAIL."""
        cm = _make_checkmesh(negative_volumes=3, mesh_ok=False)
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.FAIL
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "negative_volumes" in hard_criteria

    def test_hard_fail_skewness(self) -> None:
        """max_skewness > 6.0 → Hard FAIL (standard)."""
        cm = _make_checkmesh(max_skewness=6.5)
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.FAIL
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "max_skewness" in hard_criteria

    def test_hard_fail_min_cell_volume_zero(self) -> None:
        """min_cell_volume <= 0 → Hard FAIL."""
        cm = _make_checkmesh(min_cell_volume=0.0)
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.FAIL
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "min_cell_volume" in hard_criteria

    def test_hard_fail_min_determinant_zero(self) -> None:
        """min_determinant <= 0 → Hard FAIL."""
        cm = _make_checkmesh(min_determinant=0.0)
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.FAIL
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "min_determinant" in hard_criteria

    def test_hard_fail_failed_checks(self) -> None:
        """failed_checks > 0 → Hard FAIL."""
        cm = _make_checkmesh(failed_checks=1, mesh_ok=False)
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.FAIL
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "failed_checks" in hard_criteria

    def test_soft_fail_two_conditions(self) -> None:
        """Soft FAIL 2개 이상 → Verdict.FAIL."""
        # max_non_orthogonality = 66 (> 65, soft fail for standard)
        # max_skewness = 4.5 (> 4.0, soft fail for standard)
        cm = _make_checkmesh(
            max_non_orthogonality=66.0,
            max_skewness=4.5,
        )
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.FAIL
        assert len(report.evaluation_summary.soft_fails) >= 2

    def test_soft_fail_one_condition(self) -> None:
        """Soft FAIL 1개 → Verdict.PASS_WITH_WARNINGS."""
        cm = _make_checkmesh(max_non_orthogonality=66.0)
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.PASS_WITH_WARNINGS
        assert len(report.evaluation_summary.soft_fails) == 1

    def test_pass_clean_mesh(self) -> None:
        """모든 지표 기준치 이하 → Verdict.PASS."""
        cm = _make_checkmesh(
            max_non_orthogonality=30.0,
            max_skewness=1.0,
            max_aspect_ratio=10.0,
            min_cell_volume=1e-10,
            min_determinant=0.5,
            negative_volumes=0,
            failed_checks=0,
            mesh_ok=True,
        )
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.PASS
        assert len(report.evaluation_summary.hard_fails) == 0
        assert len(report.evaluation_summary.soft_fails) == 0

    def test_soft_fail_aspect_ratio(self) -> None:
        """max_aspect_ratio > 200 → soft fail (standard)."""
        cm = _make_checkmesh(max_aspect_ratio=210.0)
        report = _make_report(cm)
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_aspect_ratio" in soft_criteria

    def test_soft_fail_cell_volume_ratio(self) -> None:
        """cell_volume_ratio > 10000 → soft fail (standard)."""
        cm = _make_checkmesh()
        metrics = AdditionalMetrics(
            cell_volume_stats=CellVolumeStats(
                min=1e-15,
                max=1e-8,
                mean=1e-11,
                std=1e-11,
                ratio_max_min=1e7,
            )
        )
        report = _make_report(cm, metrics)
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "cell_volume_ratio" in soft_criteria


# ---------------------------------------------------------------------------
# 권고사항 테스트
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_recommendations_generated_on_fail(self) -> None:
        """FAIL 시 recommendations 비어 있지 않음."""
        cm = _make_checkmesh(max_non_orthogonality=75.0)
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.FAIL
        assert len(report.evaluation_summary.recommendations) > 0

    def test_recommendations_empty_on_clean_pass(self) -> None:
        """깨끗한 PASS 시 recommendations 비어 있음."""
        cm = _make_checkmesh()
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.PASS
        assert len(report.evaluation_summary.recommendations) == 0

    def test_recommendations_negative_volumes(self) -> None:
        """negative_volumes > 0 → BL 관련 권고 포함."""
        cm = _make_checkmesh(negative_volumes=5, mesh_ok=False)
        report = _make_report(cm)
        actions = [r.action for r in report.evaluation_summary.recommendations]
        assert len(actions) > 0

    def test_recommendations_priority_order(self) -> None:
        """recommendations priority가 1부터 오름차순."""
        cm = _make_checkmesh(negative_volumes=2, mesh_ok=False)
        report = _make_report(cm)
        recs = report.evaluation_summary.recommendations
        for i, rec in enumerate(recs):
            assert rec.priority == i + 1


# ---------------------------------------------------------------------------
# QualityReport 스키마 검증
# ---------------------------------------------------------------------------

class TestQualityReportSchema:
    def test_quality_report_schema(self) -> None:
        """QualityReport Pydantic 모델 검증."""
        cm = _make_checkmesh()
        report = _make_report(cm)

        # Pydantic 모델 직렬화/역직렬화 왕복 검증
        json_str = report.model_dump_json()
        recovered = QualityReport.model_validate_json(json_str)

        assert recovered.evaluation_summary.verdict == report.evaluation_summary.verdict
        assert recovered.evaluation_summary.iteration == 1
        assert recovered.evaluation_summary.tier_evaluated == "test_tier"
        assert recovered.evaluation_summary.checkmesh.cells == cm.cells

    def test_quality_report_verdict_values(self) -> None:
        """Verdict enum 값 확인."""
        assert Verdict.PASS.value == "PASS"
        assert Verdict.PASS_WITH_WARNINGS.value == "PASS_WITH_WARNINGS"
        assert Verdict.FAIL.value == "FAIL"

    def test_evaluation_summary_contains_all_fields(self) -> None:
        """EvaluationSummary 필수 필드 포함 여부."""
        cm = _make_checkmesh(max_non_orthogonality=75.0)
        report = _make_report(cm)
        s = report.evaluation_summary

        assert hasattr(s, "verdict")
        assert hasattr(s, "iteration")
        assert hasattr(s, "tier_evaluated")
        assert hasattr(s, "evaluation_time_seconds")
        assert hasattr(s, "checkmesh")
        assert hasattr(s, "hard_fails")
        assert hasattr(s, "soft_fails")
        assert hasattr(s, "recommendations")

    def test_fail_criterion_fields(self) -> None:
        """FailCriterion 필드 확인 (standard threshold = 70.0)."""
        cm = _make_checkmesh(max_non_orthogonality=75.0)
        report = _make_report(cm)
        fc = report.evaluation_summary.hard_fails[0]

        assert fc.criterion == "max_non_orthogonality"
        assert fc.value == pytest.approx(75.0)
        assert fc.threshold == pytest.approx(70.0)
        assert isinstance(fc.location_hint, str)

    def test_quality_level_in_report(self) -> None:
        """EvaluationSummary에 quality_level 필드가 채워진다."""
        cm = _make_checkmesh()
        for level in ("draft", "standard", "fine"):
            report = _make_report(cm, quality_level=level)
            assert report.evaluation_summary.quality_level == level


# ---------------------------------------------------------------------------
# 경계값 테스트
# ---------------------------------------------------------------------------

class TestBoundaryValues:
    def test_non_ortho_exactly_at_hard_threshold(self) -> None:
        """non_ortho = 70.0 (경계값) → FAIL 아님 (strictly greater than 70, standard)."""
        cm = _make_checkmesh(max_non_orthogonality=70.0)
        report = _make_report(cm)
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "max_non_orthogonality" not in hard_criteria

    def test_non_ortho_just_above_hard_threshold(self) -> None:
        """non_ortho = 70.01 → Hard FAIL (standard)."""
        cm = _make_checkmesh(max_non_orthogonality=70.01)
        report = _make_report(cm)
        assert report.evaluation_summary.verdict == Verdict.FAIL

    def test_skewness_exactly_at_soft_threshold(self) -> None:
        """skewness = 4.0 (경계값) → soft fail 아님 (standard)."""
        cm = _make_checkmesh(max_skewness=4.0)
        report = _make_report(cm)
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_skewness" not in soft_criteria

    def test_skewness_just_above_soft_threshold(self) -> None:
        """skewness = 4.01 → soft fail (standard)."""
        cm = _make_checkmesh(max_skewness=4.01)
        report = _make_report(cm)
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_skewness" in soft_criteria


# ---------------------------------------------------------------------------
# QualityLevel별 차등 임계값 테스트
# ---------------------------------------------------------------------------

class TestGetThresholds:
    def test_draft_thresholds(self) -> None:
        t = get_thresholds("draft")
        assert t["hard_non_ortho"] == 85.0
        assert t["hard_skewness"] == 8.0
        assert t["hard_hausdorff"] == pytest.approx(0.10)
        assert t["soft_non_ortho"] == 80.0
        assert t["soft_skewness"] == 6.0
        assert t["soft_aspect_ratio"] == 1000.0
        assert t["soft_volume_ratio"] == 100000.0
        assert t["soft_area_deviation"] == 20.0
        assert t["soft_bl_missing"] is None  # N/A for draft

    def test_standard_thresholds(self) -> None:
        t = get_thresholds("standard")
        assert t["hard_non_ortho"] == 70.0
        assert t["hard_skewness"] == 6.0
        assert t["hard_hausdorff"] == pytest.approx(0.05)
        assert t["soft_non_ortho"] == 65.0
        assert t["soft_skewness"] == 4.0
        assert t["soft_aspect_ratio"] == 200.0
        assert t["soft_volume_ratio"] == 10000.0
        assert t["soft_area_deviation"] == 10.0
        assert t["soft_bl_missing"] == 30.0

    def test_fine_thresholds(self) -> None:
        t = get_thresholds("fine")
        assert t["hard_non_ortho"] == 65.0
        assert t["hard_skewness"] == 4.0
        assert t["hard_hausdorff"] == pytest.approx(0.02)
        assert t["soft_non_ortho"] == 60.0
        assert t["soft_skewness"] == 3.0
        assert t["soft_aspect_ratio"] == 100.0
        assert t["soft_volume_ratio"] == 1000.0
        assert t["soft_area_deviation"] == 5.0
        assert t["soft_bl_missing"] == 20.0

    def test_unknown_quality_level_falls_back_to_standard(self) -> None:
        t = get_thresholds("unknown_level")
        assert t == get_thresholds("standard")


class TestDraftThresholds:
    def test_non_ortho_80_passes_draft(self) -> None:
        """non_ortho = 80° → PASS for draft (hard threshold 85°, soft threshold 80°; boundary is not > 80)."""
        cm = _make_checkmesh(max_non_orthogonality=80.0)
        report = _make_report(cm, quality_level="draft")
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_non_orthogonality" not in hard_criteria
        assert "max_non_orthogonality" not in soft_criteria

    def test_non_ortho_80_soft_fails_standard(self) -> None:
        """non_ortho = 80° → soft FAIL for standard (soft threshold 65°)."""
        cm = _make_checkmesh(max_non_orthogonality=80.0)
        report = _make_report(cm, quality_level="standard")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_non_orthogonality" in soft_criteria

    def test_non_ortho_80_hard_fails_standard(self) -> None:
        """non_ortho = 80° → hard FAIL for standard (hard threshold 70°)."""
        cm = _make_checkmesh(max_non_orthogonality=80.0)
        report = _make_report(cm, quality_level="standard")
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "max_non_orthogonality" in hard_criteria

    def test_non_ortho_81_soft_fails_draft(self) -> None:
        """non_ortho = 81° → soft FAIL for draft (soft threshold 80°)."""
        cm = _make_checkmesh(max_non_orthogonality=81.0)
        report = _make_report(cm, quality_level="draft")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_non_orthogonality" in soft_criteria

    def test_skewness_7_passes_draft_hard(self) -> None:
        """skewness = 7.0 → no hard FAIL for draft (hard threshold 8.0)."""
        cm = _make_checkmesh(max_skewness=7.0)
        report = _make_report(cm, quality_level="draft")
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "max_skewness" not in hard_criteria

    def test_skewness_7_hard_fails_standard(self) -> None:
        """skewness = 7.0 → hard FAIL for standard (hard threshold 6.0)."""
        cm = _make_checkmesh(max_skewness=7.0)
        report = _make_report(cm, quality_level="standard")
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "max_skewness" in hard_criteria

    def test_skewness_8_5_hard_fails_draft(self) -> None:
        """skewness = 8.5 → hard FAIL for draft (hard threshold 8.0)."""
        cm = _make_checkmesh(max_skewness=8.5)
        report = _make_report(cm, quality_level="draft")
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "max_skewness" in hard_criteria

    def test_draft_no_bl_missing_check(self) -> None:
        """draft 레벨에서는 BL missing ratio 소프트 판정을 하지 않는다."""
        cm = _make_checkmesh()
        # BL coverage 50% → missing 50%, which would fail standard/fine but not draft
        metrics = AdditionalMetrics(
            boundary_layer=BoundaryLayerStats(
                bl_coverage_percent=50.0,
                avg_first_layer_height=0.001,
                min_first_layer_height=0.0005,
                max_first_layer_height=0.002,
            )
        )
        report = _make_report(cm, metrics=metrics, quality_level="draft")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "bl_missing_ratio" not in soft_criteria

    def test_standard_bl_missing_check(self) -> None:
        """standard 레벨에서 BL missing ratio > 30% → soft FAIL."""
        cm = _make_checkmesh()
        # BL coverage 60% → missing 40% > 30%
        metrics = AdditionalMetrics(
            boundary_layer=BoundaryLayerStats(
                bl_coverage_percent=60.0,
                avg_first_layer_height=0.001,
                min_first_layer_height=0.0005,
                max_first_layer_height=0.002,
            )
        )
        report = _make_report(cm, metrics=metrics, quality_level="standard")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "bl_missing_ratio" in soft_criteria


# ---------------------------------------------------------------------------
# 지오메트리 충실도 (Hausdorff) 테스트
# ---------------------------------------------------------------------------

import tempfile  # noqa: E402
import numpy as np  # noqa: E402


def _make_sphere_stl(path: "Path", radius: float = 1.0, subdivisions: int = 3) -> None:
    """trimesh로 구 STL을 생성한다."""
    import trimesh  # noqa: PLC0415

    sphere = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    sphere.export(str(path))


def _make_minimal_polymesh(case_dir: "Path", stl_path: "Path") -> None:
    """trimesh로 읽은 STL을 기반으로 최소 polyMesh 디렉터리를 생성한다.

    points / faces / boundary 파일을 OpenFOAM 텍스트 포맷으로 작성한다.
    """
    import trimesh  # noqa: PLC0415

    mesh = trimesh.load(str(stl_path), force="mesh")
    assert isinstance(mesh, trimesh.Trimesh)

    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)

    verts = mesh.vertices
    faces = mesh.faces

    # points 파일
    lines = [f"{len(verts)}", "("]
    for v in verts:
        lines.append(f"({v[0]:.10g} {v[1]:.10g} {v[2]:.10g})")
    lines.append(")")
    (poly_dir / "points").write_text("\n".join(lines))

    # faces 파일
    lines = [f"{len(faces)}", "("]
    for f in faces:
        lines.append(f"3({f[0]} {f[1]} {f[2]})")
    lines.append(")")
    (poly_dir / "faces").write_text("\n".join(lines))

    # boundary 파일 — 全面을 "walls" 패치 하나로 등록
    n_faces = len(faces)
    boundary_content = (
        "1\n(\n"
        "    walls\n"
        "    {\n"
        f"        nFaces {n_faces};\n"
        "        startFace 0;\n"
        "    }\n"
        ")\n"
    )
    (poly_dir / "boundary").write_text(boundary_content)


class TestGeometryFidelityChecker:
    """GeometryFidelityChecker 단위 테스트."""

    def test_fidelity_identical_meshes(self) -> None:
        """동일한 STL → Hausdorff ≈ 0, 표면적 편차 ≈ 0."""
        pytest.importorskip("trimesh")
        pytest.importorskip("scipy")
        from core.evaluator.fidelity import GeometryFidelityChecker  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        # 반지름 1인 구의 대각선: diameter=2 → bounding box diagonal = 2*sqrt(3) ≈ 3.46
        diagonal = 2.0 * (3 ** 0.5)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            stl = tmp_path / "sphere.stl"
            _make_sphere_stl(stl, radius=1.0)
            _make_minimal_polymesh(tmp_path, stl)

            checker = GeometryFidelityChecker()
            result = checker.compute(
                original_stl=stl,
                case_dir=tmp_path,
                diagonal=diagonal,
            )

        assert result is not None
        # 동일 메쉬이므로 Hausdorff 매우 작음
        # icosphere 이산화 오차 포함 5% 이내로 허용 (fine 기준 2%보다는 여유 있음)
        assert result.hausdorff_relative < 0.05
        # 표면적 편차도 매우 작음 (이산화 오차 무시 수준)
        assert result.surface_area_deviation_percent < 1.0

    def test_fidelity_different_meshes(self) -> None:
        """원본 구 vs 2배 확대 구 → Hausdorff > 0, 표면적 편차 > 0."""
        pytest.importorskip("trimesh")
        pytest.importorskip("scipy")
        from core.evaluator.fidelity import GeometryFidelityChecker  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_stl = tmp_path / "sphere_r1.stl"
            scaled_stl = tmp_path / "sphere_r2.stl"
            _make_sphere_stl(original_stl, radius=1.0)
            _make_sphere_stl(scaled_stl, radius=2.0)
            _make_minimal_polymesh(tmp_path, scaled_stl)

            checker = GeometryFidelityChecker()
            result = checker.compute(
                original_stl=original_stl,
                case_dir=tmp_path,
                diagonal=2.0,
            )

        assert result is not None
        assert result.hausdorff_distance > 0.0
        assert result.hausdorff_relative > 0.0
        assert result.surface_area_deviation_percent > 0.0

    def test_fidelity_returns_none_on_missing_boundary(self) -> None:
        """polyMesh 없으면 None 반환."""
        pytest.importorskip("trimesh")
        pytest.importorskip("scipy")
        from core.evaluator.fidelity import GeometryFidelityChecker  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            stl = tmp_path / "sphere.stl"
            _make_sphere_stl(stl, radius=1.0)
            # polyMesh 디렉터리를 만들지 않음

            checker = GeometryFidelityChecker()
            result = checker.compute(
                original_stl=stl,
                case_dir=tmp_path,
                diagonal=2.0,
            )

        assert result is None

    def test_fidelity_hausdorff_fields(self) -> None:
        """GeometryFidelity 필드 타입 검증."""
        pytest.importorskip("trimesh")
        pytest.importorskip("scipy")
        from core.evaluator.fidelity import GeometryFidelityChecker  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            stl = tmp_path / "sphere.stl"
            _make_sphere_stl(stl, radius=1.0)
            _make_minimal_polymesh(tmp_path, stl)

            checker = GeometryFidelityChecker()
            result = checker.compute(
                original_stl=stl,
                case_dir=tmp_path,
                diagonal=2.0,
            )

        assert result is not None
        assert isinstance(result.hausdorff_distance, float)
        assert isinstance(result.hausdorff_relative, float)
        assert isinstance(result.surface_area_deviation_percent, float)
        assert result.hausdorff_distance >= 0.0
        assert result.hausdorff_relative >= 0.0
        assert result.surface_area_deviation_percent >= 0.0

    def test_fidelity_hard_fail_wires_into_report(self) -> None:
        """GeometryFidelity.hausdorff_relative > hard threshold → hard FAIL."""
        from core.evaluator.report import EvaluationReporter  # noqa: PLC0415

        cm = _make_checkmesh()
        fidelity = GeometryFidelity(
            hausdorff_distance=0.15,
            hausdorff_relative=0.06,  # > 0.05 (standard hard threshold)
            surface_area_deviation_percent=2.0,
        )
        report = _make_report(cm, geometry_fidelity=fidelity)
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "hausdorff_relative" in hard_criteria
        assert report.evaluation_summary.verdict == Verdict.FAIL

    def test_fidelity_soft_fail_area_deviation(self) -> None:
        """area_deviation_percent > 10% → soft FAIL (standard)."""
        cm = _make_checkmesh()
        fidelity = GeometryFidelity(
            hausdorff_distance=0.01,
            hausdorff_relative=0.005,
            surface_area_deviation_percent=12.0,  # > 10% soft threshold
        )
        report = _make_report(cm, geometry_fidelity=fidelity)
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "surface_area_deviation_percent" in soft_criteria

    def test_aspect_ratio_500_passes_draft_soft(self) -> None:
        """aspect ratio = 500 → no soft FAIL for draft (threshold 1000), but soft FAIL for standard (threshold 200)."""
        cm = _make_checkmesh(max_aspect_ratio=500.0)
        draft_report = _make_report(cm, quality_level="draft")
        standard_report = _make_report(cm, quality_level="standard")

        draft_soft = [f.criterion for f in draft_report.evaluation_summary.soft_fails]
        standard_soft = [f.criterion for f in standard_report.evaluation_summary.soft_fails]

        assert "max_aspect_ratio" not in draft_soft
        assert "max_aspect_ratio" in standard_soft


class TestFineThresholds:
    def test_non_ortho_63_passes_standard_hard(self) -> None:
        """non_ortho = 63° → no hard FAIL for standard (threshold 70°)."""
        cm = _make_checkmesh(max_non_orthogonality=63.0)
        report = _make_report(cm, quality_level="standard")
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "max_non_orthogonality" not in hard_criteria

    def test_non_ortho_63_hard_fails_fine(self) -> None:
        """non_ortho = 63° → hard FAIL for fine (hard threshold 65°)."""
        cm = _make_checkmesh(max_non_orthogonality=63.0)
        report = _make_report(cm, quality_level="fine")
        hard_criteria = [f.criterion for f in report.evaluation_summary.hard_fails]
        assert "max_non_orthogonality" not in hard_criteria

    def test_non_ortho_66_passes_standard_soft(self) -> None:
        """non_ortho = 66° → soft FAIL for standard (soft threshold 65°)."""
        cm = _make_checkmesh(max_non_orthogonality=66.0)
        report = _make_report(cm, quality_level="standard")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_non_orthogonality" in soft_criteria

    def test_non_ortho_62_soft_fails_fine(self) -> None:
        """non_ortho = 62° → soft FAIL for fine (soft threshold 60°)."""
        cm = _make_checkmesh(max_non_orthogonality=62.0)
        report = _make_report(cm, quality_level="fine")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_non_orthogonality" in soft_criteria

    def test_non_ortho_62_passes_standard_soft(self) -> None:
        """non_ortho = 62° → no soft FAIL for standard (soft threshold 65°)."""
        cm = _make_checkmesh(max_non_orthogonality=62.0)
        report = _make_report(cm, quality_level="standard")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_non_orthogonality" not in soft_criteria

    def test_skewness_3_5_passes_standard_soft(self) -> None:
        """skewness = 3.5 → no soft FAIL for standard (soft threshold 4.0)."""
        cm = _make_checkmesh(max_skewness=3.5)
        report = _make_report(cm, quality_level="standard")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_skewness" not in soft_criteria

    def test_skewness_3_5_soft_fails_fine(self) -> None:
        """skewness = 3.5 → soft FAIL for fine (soft threshold 3.0)."""
        cm = _make_checkmesh(max_skewness=3.5)
        report = _make_report(cm, quality_level="fine")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "max_skewness" in soft_criteria

    def test_hausdorff_fine_hard_fail(self) -> None:
        """hausdorff_relative = 0.03 → hard FAIL for fine (threshold 0.02) but PASS for standard (threshold 0.05)."""
        cm = _make_checkmesh()
        fidelity = GeometryFidelity(
            hausdorff_distance=0.03,
            hausdorff_relative=0.03,
            surface_area_deviation_percent=1.0,
        )
        fine_report = _make_report(cm, quality_level="fine", geometry_fidelity=fidelity)
        standard_report = _make_report(cm, quality_level="standard", geometry_fidelity=fidelity)

        fine_hard = [f.criterion for f in fine_report.evaluation_summary.hard_fails]
        standard_hard = [f.criterion for f in standard_report.evaluation_summary.hard_fails]

        assert "hausdorff_relative" in fine_hard
        assert "hausdorff_relative" not in standard_hard

    def test_fine_bl_missing_check(self) -> None:
        """fine 레벨에서 BL missing ratio > 20% → soft FAIL."""
        cm = _make_checkmesh()
        # BL coverage 75% → missing 25% > 20%
        metrics = AdditionalMetrics(
            boundary_layer=BoundaryLayerStats(
                bl_coverage_percent=75.0,
                avg_first_layer_height=0.001,
                min_first_layer_height=0.0005,
                max_first_layer_height=0.002,
            )
        )
        report = _make_report(cm, metrics=metrics, quality_level="fine")
        soft_criteria = [f.criterion for f in report.evaluation_summary.soft_fails]
        assert "bl_missing_ratio" in soft_criteria

    def test_area_deviation_fine_soft_fail(self) -> None:
        """surface_area_deviation = 7% → soft FAIL for fine (threshold 5%) but PASS for standard (threshold 10%)."""
        cm = _make_checkmesh()
        fidelity = GeometryFidelity(
            hausdorff_distance=0.001,
            hausdorff_relative=0.001,
            surface_area_deviation_percent=7.0,
        )
        fine_report = _make_report(cm, quality_level="fine", geometry_fidelity=fidelity)
        standard_report = _make_report(cm, quality_level="standard", geometry_fidelity=fidelity)

        fine_soft = [f.criterion for f in fine_report.evaluation_summary.soft_fails]
        standard_soft = [f.criterion for f in standard_report.evaluation_summary.soft_fails]

        assert "surface_area_deviation_percent" in fine_soft
        assert "surface_area_deviation_percent" not in standard_soft


class TestMultipleQualityLevelsSameData:
    """동일한 checkMesh 데이터로 품질 레벨별 다른 판정을 검증한다."""

    def test_same_data_different_verdicts(self) -> None:
        """non_ortho=75 → FAIL for fine/standard, PASS (no hard fail) for draft (threshold 85)."""
        cm = _make_checkmesh(max_non_orthogonality=75.0)

        draft_report = _make_report(cm, quality_level="draft")
        standard_report = _make_report(cm, quality_level="standard")
        fine_report = _make_report(cm, quality_level="fine")

        # draft: hard threshold 85°, soft threshold 80° → 75° has no hard/soft fail on non_ortho
        draft_hard = [f.criterion for f in draft_report.evaluation_summary.hard_fails]
        assert "max_non_orthogonality" not in draft_hard

        # standard: hard threshold 70° → 75° triggers hard fail
        assert standard_report.evaluation_summary.verdict == Verdict.FAIL

        # fine: hard threshold 65° → 75° triggers hard fail
        assert fine_report.evaluation_summary.verdict == Verdict.FAIL

    def test_threshold_values_in_fail_records_match_quality_level(self) -> None:
        """FailCriterion의 threshold 값이 quality_level에 따라 달라진다."""
        cm = _make_checkmesh(max_non_orthogonality=72.0)

        # standard hard threshold is 70°
        standard_report = _make_report(cm, quality_level="standard")
        standard_hard = [f for f in standard_report.evaluation_summary.hard_fails
                         if f.criterion == "max_non_orthogonality"]
        assert len(standard_hard) == 1
        assert standard_hard[0].threshold == pytest.approx(70.0)

        # fine hard threshold is 65°
        fine_report = _make_report(cm, quality_level="fine")
        fine_hard = [f for f in fine_report.evaluation_summary.hard_fails
                     if f.criterion == "max_non_orthogonality"]
        assert len(fine_hard) == 1
        assert fine_hard[0].threshold == pytest.approx(65.0)

    def test_cell_volume_ratio_different_levels(self) -> None:
        """cell_volume_ratio=5000 → soft FAIL for fine/standard but PASS for draft? No:
        draft threshold is 100000, standard is 10000, fine is 1000.
        5000 > 1000 (fine fail), < 10000 (standard pass), < 100000 (draft pass)."""
        cm = _make_checkmesh()
        metrics = AdditionalMetrics(
            cell_volume_stats=CellVolumeStats(
                min=1e-15,
                max=1e-12,
                mean=5e-14,
                std=1e-14,
                ratio_max_min=5000.0,
            )
        )

        draft_report = _make_report(cm, metrics=metrics, quality_level="draft")
        standard_report = _make_report(cm, metrics=metrics, quality_level="standard")
        fine_report = _make_report(cm, metrics=metrics, quality_level="fine")

        draft_soft = [f.criterion for f in draft_report.evaluation_summary.soft_fails]
        standard_soft = [f.criterion for f in standard_report.evaluation_summary.soft_fails]
        fine_soft = [f.criterion for f in fine_report.evaluation_summary.soft_fails]

        assert "cell_volume_ratio" not in draft_soft   # 5000 < 100000
        assert "cell_volume_ratio" not in standard_soft  # 5000 < 10000
        assert "cell_volume_ratio" in fine_soft          # 5000 > 1000


# ---------------------------------------------------------------------------
# NativeMeshChecker 테스트
# ---------------------------------------------------------------------------

def _write_single_tet_polymesh(case_dir: Path) -> None:
    """Write a minimal valid single-tet polyMesh.

    Tet vertices:
        v0 = (0, 0, 0)
        v1 = (1, 0, 0)
        v2 = (0, 1, 0)
        v3 = (0, 0, 1)

    The PolyMeshWriter logic is replicated here so the test does not
    depend on that module.  Faces follow the OpenFOAM outward-normal
    convention for the tet (all boundary for a single tet).
    """
    from core.generator.polymesh_writer import PolyMeshWriter  # noqa: PLC0415

    vertices = np.array(
        [[0.0, 0.0, 0.0],
         [1.0, 0.0, 0.0],
         [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    PolyMeshWriter().write(vertices, tets, case_dir)


class TestNativeMeshChecker:
    """NativeMeshChecker 단위 테스트 — OpenFOAM 불필요."""

    def test_native_checker_returns_checkmesh_result(self) -> None:
        """NativeMeshChecker.run이 CheckMeshResult를 반환한다."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert isinstance(result, CheckMeshResult)

    def test_native_checker_single_tet_cell_count(self) -> None:
        """단일 tet → cells = 1."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert result.cells == 1

    def test_native_checker_single_tet_face_count(self) -> None:
        """단일 tet → faces = 4 (all boundary)."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert result.faces == 4

    def test_native_checker_single_tet_point_count(self) -> None:
        """단일 tet → points = 4."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert result.points == 4

    def test_native_checker_face_areas_positive(self) -> None:
        """단일 tet → min_face_area > 0."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert result.min_face_area > 0.0

    def test_native_checker_cell_volume_positive(self) -> None:
        """단일 tet → min_cell_volume > 0 (no negative volumes)."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert result.min_cell_volume > 0.0
        assert result.negative_volumes == 0

    def test_native_checker_no_internal_faces_single_tet(self) -> None:
        """단일 tet는 내부 면이 없으므로 non_ortho = 0, skewness = 0."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)
            result = NativeMeshChecker().run(case_dir)

        # Single tet has no internal faces → these metrics are trivially 0
        assert result.max_non_orthogonality == pytest.approx(0.0)
        assert result.avg_non_orthogonality == pytest.approx(0.0)
        assert result.max_skewness == pytest.approx(0.0)

    def test_native_checker_two_tets_internal_face(self) -> None:
        """두 tet (공유 면 존재) → non_ortho 계산 가능."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415
        from core.generator.polymesh_writer import PolyMeshWriter  # noqa: PLC0415

        # Two tets sharing face (1,2,3)
        vertices = np.array(
            [[0.0, 0.0, 0.0],  # 0
             [1.0, 0.0, 0.0],  # 1
             [0.0, 1.0, 0.0],  # 2
             [0.0, 0.0, 1.0],  # 3
             [1.0, 1.0, 1.0]], # 4 — second tet apex
            dtype=np.float64,
        )
        tets = np.array([[0, 1, 2, 3], [4, 1, 2, 3]], dtype=np.int64)

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            PolyMeshWriter().write(vertices, tets, case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert result.cells == 2
        # There should be 1 internal face shared by the two tets
        # non_ortho should now be a valid (non-NaN) value
        assert result.max_non_orthogonality >= 0.0
        assert not np.isnan(result.max_non_orthogonality)

    def test_native_checker_multi_tet_cell_volumes_positive(self) -> None:
        """복수 tet → 모든 cell volume이 양수."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415
        from core.generator.polymesh_writer import PolyMeshWriter  # noqa: PLC0415

        # Regular tetrahedra from a unit cube corner
        vertices = np.array(
            [[0.0, 0.0, 0.0],
             [1.0, 0.0, 0.0],
             [0.0, 1.0, 0.0],
             [0.0, 0.0, 1.0],
             [1.0, 1.0, 0.0],
             [1.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        tets = np.array(
            [[0, 1, 2, 3],
             [1, 2, 3, 4],
             [1, 3, 4, 5]],
            dtype=np.int64,
        )

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            PolyMeshWriter().write(vertices, tets, case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert result.cells == 3
        assert result.min_cell_volume > 0.0
        assert result.negative_volumes == 0

    def test_native_checker_aspect_ratio_at_least_one(self) -> None:
        """Aspect ratio は常に >= 1."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert result.max_aspect_ratio >= 1.0

    def test_native_checker_min_determinant_in_range(self) -> None:
        """Min determinant は [0, 1] の範囲。"""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)
            result = NativeMeshChecker().run(case_dir)

        assert 0.0 <= result.min_determinant <= 1.0

    def test_native_checker_raises_on_missing_polymesh(self) -> None:
        """polyMesh 디렉터리 없으면 FileNotFoundError."""
        from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(FileNotFoundError):
                NativeMeshChecker().run(Path(tmp))

    def test_fallback_when_no_openfoam(self) -> None:
        """OpenFOAM checkMesh 없으면 NativeMeshChecker가 호출된다."""
        from core.evaluator.quality_checker import MeshQualityChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)

            with patch(
                "core.evaluator.quality_checker.MeshQualityChecker._run_openfoam",
                side_effect=FileNotFoundError("checkMesh not found"),
            ):
                result = MeshQualityChecker().run(case_dir)

        # NativeMeshChecker should have produced a valid result
        assert isinstance(result, CheckMeshResult)
        assert result.cells == 1

    def test_fallback_result_is_checkmesh_result_schema(self) -> None:
        """폴백 결과가 CheckMeshResult 스키마를 만족한다."""
        from core.evaluator.quality_checker import MeshQualityChecker  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            _write_single_tet_polymesh(case_dir)

            with patch(
                "core.evaluator.quality_checker.MeshQualityChecker._run_openfoam",
                side_effect=FileNotFoundError("no openfoam"),
            ):
                result = MeshQualityChecker().run(case_dir)

        # Round-trip JSON serialisation must succeed
        json_str = result.model_dump_json()
        recovered = CheckMeshResult.model_validate_json(json_str)
        assert recovered.cells == result.cells
        assert recovered.faces == result.faces
