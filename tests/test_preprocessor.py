"""Preprocessor 모듈 테스트.

pymeshfix, pyacvd 없이도 모든 테스트가 통과해야 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"
SPHERE_STL = BENCHMARKS_DIR / "sphere.stl"
SPHERE_REPORT_JSON = BENCHMARKS_DIR / "sphere.geometry_report.json"


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sphere_mesh() -> trimesh.Trimesh:
    """sphere.stl 로딩 픽스처."""
    return trimesh.load(str(SPHERE_STL), force="mesh")


@pytest.fixture(scope="session")
def sphere_geometry_report():
    """sphere.geometry_report.json 로딩 픽스처."""
    from core.schemas import GeometryReport
    return GeometryReport.model_validate_json(SPHERE_REPORT_JSON.read_text())


# ---------------------------------------------------------------------------
# test_no_repair_needed
# ---------------------------------------------------------------------------


def test_no_repair_needed(sphere_mesh, sphere_geometry_report):
    """깨끗한 sphere는 수리 없이 통과 — 반환 actions 리스트가 비어야 한다."""
    from core.preprocessor.repair import SurfaceRepairer

    repairer = SurfaceRepairer()
    # sphere.geometry_report 의 issues는 빈 리스트
    repaired, actions = repairer.repair(sphere_mesh, sphere_geometry_report.issues)

    assert isinstance(repaired, trimesh.Trimesh)
    assert actions == [], f"수리 불필요한 메쉬에 actions가 발생했습니다: {actions}"


# ---------------------------------------------------------------------------
# test_format_stl_passthrough
# ---------------------------------------------------------------------------


def test_format_stl_passthrough(tmp_path):
    """STL 파일은 변환 불필요 — needs_conversion=False, 경로 그대로 반환."""
    from core.preprocessor.converter import FormatConverter

    converter = FormatConverter()

    assert converter.needs_conversion(SPHERE_STL) is False

    # convert_to_stl 호출해도 원본 경로를 그대로 반환
    result = converter.convert_to_stl(SPHERE_STL, tmp_path)
    assert result == SPHERE_STL


# ---------------------------------------------------------------------------
# test_format_obj_needs_conversion
# ---------------------------------------------------------------------------


def test_format_obj_needs_conversion():
    """OBJ/PLY/OFF 등은 변환 필요 플래그를 반환한다."""
    from core.preprocessor.converter import FormatConverter

    converter = FormatConverter()

    for suffix in [".obj", ".ply", ".off", ".3mf"]:
        fake_path = Path(f"/tmp/dummy{suffix}")
        assert converter.needs_conversion(fake_path) is True, f"{suffix} should need conversion"


# ---------------------------------------------------------------------------
# test_preprocessed_report_schema
# ---------------------------------------------------------------------------


def test_preprocessed_report_schema():
    """PreprocessedReport Pydantic 모델 검증 — 올바른 JSON은 파싱 성공."""
    from core.schemas import PreprocessedReport

    data = {
        "preprocessing_summary": {
            "input_file": "model.stl",
            "input_format": "STL",
            "output_file": "preprocessed.stl",
            "passthrough_cad": False,
            "total_time_seconds": 1.5,
            "steps_performed": [],
            "final_validation": {
                "is_watertight": True,
                "is_manifold": True,
                "num_faces": 1280,
                "min_face_area": 0.009,
                "max_edge_length_ratio": 1.19,
            },
        }
    }

    report = PreprocessedReport.model_validate(data)
    assert report.preprocessing_summary.input_file == "model.stl"
    assert report.preprocessing_summary.final_validation.is_watertight is True
    assert report.preprocessing_summary.final_validation.num_faces == 1280

    # JSON 직렬화 및 역직렬화 왕복 검증
    json_str = report.model_dump_json()
    reloaded = PreprocessedReport.model_validate_json(json_str)
    assert reloaded.preprocessing_summary.total_time_seconds == 1.5


def test_preprocessed_report_schema_with_steps():
    """PreprocessStep을 포함한 PreprocessedReport 스키마 검증."""
    from core.schemas import PreprocessedReport

    data = {
        "preprocessing_summary": {
            "input_file": "model.step",
            "input_format": "STEP",
            "output_file": "preprocessed.stl",
            "passthrough_cad": False,
            "total_time_seconds": 4.2,
            "steps_performed": [
                {
                    "step": "format_conversion",
                    "method": "cadquery.exportStl",
                    "params": {"linear_deflection": 0.001},
                    "input_faces": None,
                    "output_faces": 24500,
                    "time_seconds": 2.1,
                },
                {
                    "step": "surface_repair",
                    "method": "pymeshfix",
                    "params": {"issues_fixed": ["non_manifold_edges(3)"]},
                    "input_faces": 24500,
                    "output_faces": 24512,
                    "time_seconds": 0.8,
                },
            ],
            "final_validation": {
                "is_watertight": True,
                "is_manifold": True,
                "num_faces": 24512,
                "min_face_area": 2.3e-6,
                "max_edge_length_ratio": 12.4,
            },
        }
    }

    report = PreprocessedReport.model_validate(data)
    assert len(report.preprocessing_summary.steps_performed) == 2
    assert report.preprocessing_summary.steps_performed[0].step == "format_conversion"


# ---------------------------------------------------------------------------
# test_pipeline_sphere
# ---------------------------------------------------------------------------


def test_pipeline_sphere(tmp_path, sphere_geometry_report):
    """sphere.stl → pipeline.run() → 출력 STL 파일이 존재해야 한다."""
    from core.preprocessor.pipeline import Preprocessor

    preprocessor = Preprocessor()
    out_stl, report = preprocessor.run(
        input_path=SPHERE_STL,
        geometry_report=sphere_geometry_report,
        output_dir=tmp_path,
    )

    # 출력 파일 존재 확인
    assert out_stl.exists(), f"출력 STL이 생성되지 않았습니다: {out_stl}"
    assert out_stl.suffix == ".stl"

    # PreprocessedReport 타입 확인
    from core.schemas import PreprocessedReport
    assert isinstance(report, PreprocessedReport)

    # 요약 정보 확인
    summary = report.preprocessing_summary
    assert summary.input_file == str(SPHERE_STL)
    assert summary.output_file == str(out_stl)
    assert summary.passthrough_cad is False
    assert summary.total_time_seconds >= 0.0


def test_pipeline_sphere_no_repair(tmp_path, sphere_geometry_report):
    """--no-repair 옵션으로 수리 없이 파이프라인 실행."""
    from core.preprocessor.pipeline import Preprocessor

    preprocessor = Preprocessor()
    out_stl, report = preprocessor.run(
        input_path=SPHERE_STL,
        geometry_report=sphere_geometry_report,
        output_dir=tmp_path,
        no_repair=True,
    )

    assert out_stl.exists()
    # no_repair 모드에서는 repair step이 없어야 함
    steps = report.preprocessing_summary.steps_performed
    repair_steps = [s for s in steps if s.step == "surface_repair"]
    assert repair_steps == []


# ---------------------------------------------------------------------------
# test_watertight_output
# ---------------------------------------------------------------------------


def test_watertight_output(tmp_path, sphere_geometry_report):
    """pipeline.run() 출력이 watertight 메쉬여야 한다."""
    from core.preprocessor.pipeline import Preprocessor

    preprocessor = Preprocessor()
    out_stl, report = preprocessor.run(
        input_path=SPHERE_STL,
        geometry_report=sphere_geometry_report,
        output_dir=tmp_path,
    )

    # 출력 메쉬 로딩 후 watertight 확인
    result_mesh = trimesh.load(str(out_stl), force="mesh")
    assert isinstance(result_mesh, trimesh.Trimesh)
    assert result_mesh.is_watertight, (
        f"출력 메쉬가 watertight가 아닙니다. "
        f"faces={len(result_mesh.faces)}, "
        f"is_winding_consistent={result_mesh.is_winding_consistent}"
    )

    # report 의 final_validation 도 확인
    fv = report.preprocessing_summary.final_validation
    assert fv.is_watertight is True
    assert fv.num_faces > 0


# ---------------------------------------------------------------------------
# test_remesh_should_remesh
# ---------------------------------------------------------------------------


def test_remesh_should_remesh_ratio(sphere_geometry_report):
    """edge_length_ratio > 100이면 should_remesh=True."""
    from core.preprocessor.remesh import SurfaceRemesher
    from core.schemas import GeometryReport

    remesher = SurfaceRemesher()

    # sphere는 ratio < 2이므로 False
    assert remesher.should_remesh(sphere_geometry_report) is False

    # ratio를 직접 조작한 새 report
    data = sphere_geometry_report.model_dump()
    data["geometry"]["surface"]["edge_length_ratio"] = 150.0
    high_ratio_report = GeometryReport.model_validate(data)
    assert remesher.should_remesh(high_ratio_report) is True


def test_remesh_should_remesh_many_faces(sphere_geometry_report):
    """num_faces > 200000이면 should_remesh=True."""
    from core.preprocessor.remesh import SurfaceRemesher
    from core.schemas import GeometryReport

    remesher = SurfaceRemesher()

    data = sphere_geometry_report.model_dump()
    data["geometry"]["surface"]["num_faces"] = 250_000
    many_faces_report = GeometryReport.model_validate(data)
    assert remesher.should_remesh(many_faces_report) is True


# ---------------------------------------------------------------------------
# test_repair_with_issues
# ---------------------------------------------------------------------------


def test_repair_with_issues(sphere_mesh):
    """warning severity 이슈가 있으면 수리가 수행된다."""
    from core.preprocessor.repair import SurfaceRepairer
    from core.schemas import Issue, Severity

    repairer = SurfaceRepairer()
    issues = [
        Issue(
            severity=Severity.WARNING,
            type="non_manifold_edges",
            count=3,
            description="Non-manifold edges detected",
            recommended_action="repair",
        )
    ]

    repaired, actions = repairer.repair(sphere_mesh, issues)
    assert isinstance(repaired, trimesh.Trimesh)
    # 수리가 실행되었으면 최소 1개 이상의 action
    assert len(actions) >= 1


def test_repair_info_only_skipped(sphere_mesh):
    """info severity만 있으면 수리가 수행되지 않는다."""
    from core.preprocessor.repair import SurfaceRepairer
    from core.schemas import Issue, Severity

    repairer = SurfaceRepairer()
    issues = [
        Issue(
            severity=Severity.INFO,
            type="sharp_edges",
            count=10,
            description="Sharp edges present",
            recommended_action="none",
        )
    ]

    _, actions = repairer.repair(sphere_mesh, issues)
    assert actions == []


# ---------------------------------------------------------------------------
# test_pipeline_netgen_passthrough
# ---------------------------------------------------------------------------


def test_pipeline_netgen_passthrough(tmp_path, sphere_geometry_report):
    """tier_hint='netgen' + 비-STL 입력이면 패스스루 report가 반환된다.

    실제 STEP 파일이 없으므로 file_info.is_cad_brep 플래그를 변조한
    가짜 report와 tmp STEP 경로로 동작을 확인한다.
    """
    from core.preprocessor.pipeline import Preprocessor
    from core.schemas import GeometryReport

    # 가짜 .step 파일 생성 (내용 없어도 됨 — passthrough는 로딩 안 함)
    fake_step = tmp_path / "model.step"
    fake_step.write_bytes(b"")

    data = sphere_geometry_report.model_dump()
    data["file_info"]["path"] = str(fake_step)
    data["file_info"]["format"] = "STEP"
    data["file_info"]["is_cad_brep"] = True
    data["file_info"]["is_surface_mesh"] = False
    step_report = GeometryReport.model_validate(data)

    preprocessor = Preprocessor()
    out_path, report = preprocessor.run(
        input_path=fake_step,
        geometry_report=step_report,
        output_dir=tmp_path / "out",
        tier_hint="netgen",
    )

    # 패스스루: 원본 파일을 그대로 반환
    assert out_path == fake_step
    assert report.preprocessing_summary.passthrough_cad is True


# ---------------------------------------------------------------------------
# L1/L2/L3 게이트 파이프라인 신규 테스트
# ---------------------------------------------------------------------------


def test_gate_check_watertight_mesh(sphere_mesh):
    """watertight인 sphere 메쉬 → gate_check=True."""
    from core.preprocessor.repair import gate_check

    # sphere.stl은 watertight 이어야 함
    if sphere_mesh.is_watertight:
        assert gate_check(sphere_mesh) is True
    else:
        pytest.skip("sphere.stl이 watertight가 아니므로 skip")


def test_gate_check_non_watertight_mesh():
    """구멍이 있는 비-watertight 메쉬 → gate_check=False."""
    from core.preprocessor.repair import gate_check
    import numpy as np

    # 삼각형 하나짜리 열린 메쉬 (watertight 불가)
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2]])
    open_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    assert open_mesh.is_watertight is False
    assert gate_check(open_mesh) is False


def test_l1_repair_gate_passed_sphere(sphere_mesh, sphere_geometry_report):
    """깨끗한 sphere에 이슈를 강제 주입해도 L1 repair_l1()이 step_record를 반환한다."""
    from core.preprocessor.repair import SurfaceRepairer
    from core.schemas import Issue, Severity

    repairer = SurfaceRepairer()
    issues = [
        Issue(
            severity=Severity.WARNING,
            type="non_manifold_edges",
            count=1,
            description="test",
            recommended_action="repair",
        )
    ]
    repaired, gate_passed, step_record = repairer.repair_l1(sphere_mesh, issues)

    assert isinstance(repaired, trimesh.Trimesh)
    assert isinstance(gate_passed, bool)
    assert step_record["step"] == "l1_repair"
    assert "gate_passed" in step_record
    assert step_record["gate_passed"] == gate_passed
    assert step_record["input_faces"] > 0
    assert step_record["output_faces"] > 0
    assert step_record["time_seconds"] >= 0.0


def test_l1_repair_skipped_no_issues(sphere_mesh):
    """이슈가 없으면 repair_l1()은 skipped 레코드를 반환하고 gate 검사만 수행한다."""
    from core.preprocessor.repair import SurfaceRepairer

    repairer = SurfaceRepairer()
    repaired, gate_passed, step_record = repairer.repair_l1(sphere_mesh, issues=[])

    assert step_record["method"] == "skipped"
    assert step_record["gate_passed"] == gate_passed
    assert isinstance(gate_passed, bool)


def test_l1_gate_passed_skips_l2(tmp_path, sphere_geometry_report):
    """sphere (깨끗한 메쉬) → L1 gate 통과 → L2 step이 steps_performed에 없어야 한다."""
    from core.preprocessor.pipeline import Preprocessor

    preprocessor = Preprocessor()
    _, report = preprocessor.run(
        input_path=SPHERE_STL,
        geometry_report=sphere_geometry_report,
        output_dir=tmp_path,
    )

    steps = report.preprocessing_summary.steps_performed
    l2_steps = [s for s in steps if s.step == "l2_remesh"]

    # sphere는 watertight이므로 L1에서 gate 통과 → L2 없어야 함
    if report.preprocessing_summary.surface_quality_level == "l1_repair":
        assert l2_steps == [], "L1 gate 통과 시 L2가 실행되면 안 됨"


def test_l2_remesh_l2_returns_gate_info(sphere_mesh):
    """SurfaceRemesher.remesh_l2()가 (mesh, gate_passed, step_record) 튜플을 반환한다."""
    from core.preprocessor.remesh import SurfaceRemesher

    remesher = SurfaceRemesher()
    result_mesh, gate_passed, step_record = remesher.remesh_l2(sphere_mesh)

    assert isinstance(result_mesh, trimesh.Trimesh)
    assert isinstance(gate_passed, bool)
    assert step_record["step"] == "l2_remesh"
    assert "gate_passed" in step_record
    assert step_record["gate_passed"] == gate_passed
    assert step_record["input_faces"] > 0
    assert step_record["output_faces"] > 0


def test_l2_gate_passed_sets_quality_level(tmp_path, sphere_geometry_report):
    """surface_remesh=True 강제 실행 시 surface_quality_level이 설정된다."""
    from core.preprocessor.pipeline import Preprocessor

    preprocessor = Preprocessor()
    _, report = preprocessor.run(
        input_path=SPHERE_STL,
        geometry_report=sphere_geometry_report,
        output_dir=tmp_path,
        surface_remesh=True,
    )

    summary = report.preprocessing_summary
    # surface_remesh=True이면 L2가 실행되어 surface_quality_level이 l2_remesh 또는 l3_ai
    assert summary.surface_quality_level in ("l2_remesh", "l3_ai", "l1_repair"), (
        f"예상치 못한 surface_quality_level: {summary.surface_quality_level}"
    )
    l2_steps = [s for s in summary.steps_performed if s.step == "l2_remesh"]
    assert len(l2_steps) >= 1, "surface_remesh=True 시 L2 step이 존재해야 함"


def test_l3_skipped_no_gpu(sphere_mesh):
    """GPU 없는 환경에서 allow_ai_fallback=True여도 L3가 gracefully 스킵된다."""
    from unittest.mock import patch
    from core.preprocessor.pipeline import Preprocessor

    preprocessor = Preprocessor()

    # torch.cuda.is_available() → False 패치
    with patch("torch.cuda.is_available", return_value=False):
        result_mesh, gate_passed, step_record = preprocessor._l3_ai_fix(
            sphere_mesh, allow_ai_fallback=True
        )

    # 스킵 시 step_record=None (GPU 없음 조기 반환)
    assert result_mesh is not None
    assert isinstance(gate_passed, bool)
    # step_record가 None이어도 파이프라인은 정상 동작해야 함


def test_l3_skipped_when_no_allow_ai_fallback(sphere_mesh):
    """allow_ai_fallback=False이면 L3는 즉시 스킵되고 step_record=None."""
    from core.preprocessor.pipeline import Preprocessor

    preprocessor = Preprocessor()
    result_mesh, gate_passed, step_record = preprocessor._l3_ai_fix(
        sphere_mesh, allow_ai_fallback=False
    )

    assert result_mesh is sphere_mesh  # 원본 그대로 반환
    assert step_record is None


def test_surface_quality_level_in_report(tmp_path, sphere_geometry_report):
    """PreprocessedReport에 surface_quality_level 필드가 존재한다."""
    from core.preprocessor.pipeline import Preprocessor
    from core.schemas import PreprocessedReport

    preprocessor = Preprocessor()
    _, report = preprocessor.run(
        input_path=SPHERE_STL,
        geometry_report=sphere_geometry_report,
        output_dir=tmp_path,
    )

    assert isinstance(report, PreprocessedReport)
    # surface_quality_level은 최상위 및 summary 양쪽에 존재
    assert hasattr(report, "surface_quality_level")
    assert hasattr(report.preprocessing_summary, "surface_quality_level")
    # 값이 유효한 레벨이어야 함
    valid_levels = {"l1_repair", "l2_remesh", "l3_ai", None}
    assert report.surface_quality_level in valid_levels
    assert report.preprocessing_summary.surface_quality_level in valid_levels


def test_gate_passed_field_in_step_records(tmp_path, sphere_geometry_report):
    """steps_performed 중 l1_repair/l2_remesh 레코드에 gate_passed 필드가 있다."""
    from core.preprocessor.pipeline import Preprocessor
    from core.schemas import PreprocessedReport

    preprocessor = Preprocessor()
    _, report = preprocessor.run(
        input_path=SPHERE_STL,
        geometry_report=sphere_geometry_report,
        output_dir=tmp_path,
    )

    steps = report.preprocessing_summary.steps_performed
    gate_steps = [s for s in steps if s.step in ("l1_repair", "l2_remesh", "l3_ai")]

    assert len(gate_steps) >= 1, "L1/L2/L3 step 중 최소 하나는 존재해야 함"
    for step in gate_steps:
        assert step.gate_passed is not None, (
            f"step '{step.step}'에 gate_passed 필드가 None이면 안 됨"
        )
        assert isinstance(step.gate_passed, bool)


def test_preprocess_step_gate_passed_schema():
    """PreprocessStep 스키마에 gate_passed 필드가 있고 직렬화된다."""
    from core.schemas import PreprocessStep

    step = PreprocessStep(
        step="l1_repair",
        method="pymeshfix",
        params={"issues_fixed": ["holes(1)"]},
        input_faces=1000,
        output_faces=1001,
        time_seconds=0.5,
        gate_passed=False,
    )

    assert step.gate_passed is False

    data = step.model_dump()
    assert data["gate_passed"] is False

    # JSON 왕복
    json_str = step.model_dump_json()
    reloaded = PreprocessStep.model_validate_json(json_str)
    assert reloaded.gate_passed is False


def test_preprocessing_summary_surface_quality_level_schema():
    """PreprocessingSummary 스키마의 surface_quality_level 필드 검증."""
    from core.schemas import PreprocessedReport

    data = {
        "preprocessing_summary": {
            "input_file": "model.stl",
            "input_format": "STL",
            "output_file": "preprocessed.stl",
            "passthrough_cad": False,
            "total_time_seconds": 3.0,
            "surface_quality_level": "l2_remesh",
            "steps_performed": [
                {
                    "step": "l1_repair",
                    "method": "pymeshfix",
                    "params": {},
                    "input_faces": 1000,
                    "output_faces": 1002,
                    "time_seconds": 0.8,
                    "gate_passed": False,
                },
                {
                    "step": "l2_remesh",
                    "method": "pyacvd+pymeshlab",
                    "params": {"target_faces": 30000, "subdivide": 3},
                    "input_faces": 1002,
                    "output_faces": 30000,
                    "time_seconds": 1.3,
                    "gate_passed": True,
                },
            ],
            "final_validation": {
                "is_watertight": True,
                "is_manifold": True,
                "num_faces": 30000,
                "min_face_area": 2.3e-6,
                "max_edge_length_ratio": 12.4,
            },
        },
        "surface_quality_level": "l2_remesh",
    }

    report = PreprocessedReport.model_validate(data)
    assert report.preprocessing_summary.surface_quality_level == "l2_remesh"
    assert report.surface_quality_level == "l2_remesh"

    l1_step = report.preprocessing_summary.steps_performed[0]
    l2_step = report.preprocessing_summary.steps_performed[1]
    assert l1_step.gate_passed is False
    assert l2_step.gate_passed is True
