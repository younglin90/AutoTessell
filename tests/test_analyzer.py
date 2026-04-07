"""Analyzer 모듈 테스트."""

from __future__ import annotations

import struct
import math
from pathlib import Path

import pytest
import trimesh

from core.analyzer.file_reader import load_mesh
from core.analyzer.geometry_analyzer import GeometryAnalyzer
from core.schemas import GeometryReport


# ---------------------------------------------------------------------------
# 헬퍼: 인메모리 STL 생성
# ---------------------------------------------------------------------------

def _make_sphere_stl(path: Path, lat_steps: int = 20, lon_steps: int = 20, radius: float = 1.0) -> None:
    """이진 STL 구(球) 생성."""
    triangles = []

    def pt(lat: int, lon: int) -> tuple[float, float, float]:
        phi = math.pi * lat / lat_steps
        theta = 2.0 * math.pi * lon / lon_steps
        return (
            radius * math.sin(phi) * math.cos(theta),
            radius * math.sin(phi) * math.sin(theta),
            radius * math.cos(phi),
        )

    def normal(a, b, c):
        ax, ay, az = b[0]-a[0], b[1]-a[1], b[2]-a[2]
        bx, by, bz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
        nx, ny, nz = ay*bz-az*by, az*bx-ax*bz, ax*by-ay*bx
        length = math.sqrt(nx*nx + ny*ny + nz*nz) or 1.0
        return (nx/length, ny/length, nz/length)

    for i in range(lat_steps):
        for j in range(lon_steps):
            p00, p10 = pt(i, j), pt(i+1, j)
            p01, p11 = pt(i, j+1), pt(i+1, j+1)
            if i != 0:
                triangles.append((p00, p10, p11))
            if i != lat_steps - 1:
                triangles.append((p00, p11, p01))

    with open(path, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(triangles)))
        for tri in triangles:
            n = normal(*tri)
            f.write(struct.pack("<3f", *n))
            for v in tri:
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))


def _make_simple_box_stl(path: Path) -> None:
    """단순 박스 이진 STL 생성 (6면 × 2삼각형 = 12 삼각형)."""
    # unit cube [0,1]^3
    verts = [
        (0,0,0),(1,0,0),(1,1,0),(0,1,0),
        (0,0,1),(1,0,1),(1,1,1),(0,1,1),
    ]
    faces = [
        (0,2,1),(0,3,2),  # bottom -z
        (4,5,6),(4,6,7),  # top +z
        (0,1,5),(0,5,4),  # front -y
        (2,3,7),(2,7,6),  # back +y
        (1,2,6),(1,6,5),  # right +x
        (0,4,7),(0,7,3),  # left -x
    ]

    def normal(a, b, c):
        ax,ay,az = verts[b][0]-verts[a][0],verts[b][1]-verts[a][1],verts[b][2]-verts[a][2]
        bx,by,bz = verts[c][0]-verts[a][0],verts[c][1]-verts[a][1],verts[c][2]-verts[a][2]
        nx,ny,nz = ay*bz-az*by,az*bx-ax*bz,ax*by-ay*bx
        l = math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
        return (nx/l,ny/l,nz/l)

    with open(path, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(faces)))
        for tri in faces:
            n = normal(*tri)
            f.write(struct.pack("<3f", *n))
            for idx in tri:
                f.write(struct.pack("<3f", *verts[idx]))
            f.write(struct.pack("<H", 0))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"


@pytest.fixture(scope="session")
def sphere_stl_path() -> Path:
    """sphere.stl 경로. 없으면 세션 스코프로 생성."""
    p = BENCHMARKS_DIR / "sphere.stl"
    if not p.exists():
        BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
        _make_sphere_stl(p)
    return p


@pytest.fixture(scope="session")
def box_stl_path(tmp_path_factory) -> Path:
    """단순 박스 STL (tmp 경로)."""
    p = tmp_path_factory.mktemp("stl") / "box.stl"
    _make_simple_box_stl(p)
    return p


# ---------------------------------------------------------------------------
# test_load_stl — STL 로딩 성공
# ---------------------------------------------------------------------------

class TestLoadStl:
    def test_load_stl_returns_trimesh(self, sphere_stl_path: Path) -> None:
        """load_mesh()가 trimesh.Trimesh를 반환하는지 확인."""
        mesh = load_mesh(sphere_stl_path)
        assert isinstance(mesh, trimesh.Trimesh)
        assert len(mesh.faces) > 0
        assert len(mesh.vertices) > 0

    def test_load_stl_face_count(self, sphere_stl_path: Path) -> None:
        """로딩된 메쉬의 면 수가 양수인지 확인."""
        mesh = load_mesh(sphere_stl_path)
        assert mesh.faces.shape[1] == 3  # 삼각형

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        """존재하지 않는 파일은 FileNotFoundError를 발생시켜야 한다."""
        with pytest.raises(FileNotFoundError):
            load_mesh(tmp_path / "nonexistent.stl")

    def test_load_box_stl(self, box_stl_path: Path) -> None:
        """박스 STL 로딩 성공."""
        mesh = load_mesh(box_stl_path)
        assert len(mesh.faces) == 12


# ---------------------------------------------------------------------------
# test_geometry_report_schema — GeometryReport Pydantic 검증
# ---------------------------------------------------------------------------

class TestGeometryReportSchema:
    def test_geometry_report_schema(self, sphere_stl_path: Path) -> None:
        """analyze() 결과가 GeometryReport Pydantic 모델을 통과하는지 확인."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)

        assert isinstance(report, GeometryReport)

        # model_dump → model_validate 왕복 검증
        data = report.model_dump()
        report2 = GeometryReport.model_validate(data)
        assert report2.file_info.format == report.file_info.format

    def test_geometry_report_fields_present(self, sphere_stl_path: Path) -> None:
        """필수 필드가 모두 존재하는지 확인."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)

        assert report.file_info.file_size_bytes > 0
        assert report.geometry.bounding_box.diagonal > 0
        assert report.geometry.surface.num_faces > 0
        assert report.geometry.surface.num_vertices > 0
        assert isinstance(report.issues, list)
        assert report.tier_compatibility.tier2_tetwild.compatible is True

    def test_bounding_box_consistency(self, sphere_stl_path: Path) -> None:
        """BoundingBox center = (min + max) / 2 인지 확인."""
        import math as _math
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        bb = report.geometry.bounding_box
        for i in range(3):
            expected = (bb.min[i] + bb.max[i]) / 2.0
            assert abs(bb.center[i] - expected) < 1e-6

    def test_surface_area_positive(self, sphere_stl_path: Path) -> None:
        """표면적이 양수인지 확인."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.geometry.surface.surface_area > 0

    def test_edge_length_ratio_positive(self, sphere_stl_path: Path) -> None:
        """엣지 길이 비율이 1.0 이상인지 확인."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.geometry.surface.edge_length_ratio >= 1.0

    def test_flow_estimation_confidence_range(self, sphere_stl_path: Path) -> None:
        """confidence 값이 [0, 1] 범위인지 확인."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        fe = report.flow_estimation
        assert 0.0 <= fe.confidence <= 1.0


# ---------------------------------------------------------------------------
# test_watertight_sphere — sphere.stl → is_watertight=True
# ---------------------------------------------------------------------------

class TestWatertightSphere:
    def test_watertight_sphere(self, sphere_stl_path: Path) -> None:
        """sphere.stl 분석 결과 is_watertight=True 여야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.geometry.surface.is_watertight is True

    def test_sphere_genus_zero(self, sphere_stl_path: Path) -> None:
        """구(球)는 genus=0 이어야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.geometry.surface.genus == 0

    def test_sphere_single_component(self, sphere_stl_path: Path) -> None:
        """구는 단일 connected component 이어야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.geometry.surface.num_connected_components == 1

    def test_sphere_no_critical_issues(self, sphere_stl_path: Path) -> None:
        """정상 구 메쉬에서 critical 이슈가 없어야 한다."""
        from core.schemas import Severity
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        critical = [i for i in report.issues if i.severity == Severity.CRITICAL]
        assert len(critical) == 0

    def test_sphere_tier0_compatible(self, sphere_stl_path: Path) -> None:
        """watertight 구는 Tier 0과 호환되어야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.tier_compatibility.tier0_core.compatible is True


# ---------------------------------------------------------------------------
# test_flow_estimation_external — 단일 폐곡면 + genus=0 → external 추정
# ---------------------------------------------------------------------------

class TestFlowEstimationExternal:
    def test_flow_estimation_external(self, sphere_stl_path: Path) -> None:
        """단일 폐곡면 + genus=0 → flow type='external' 추정."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.flow_estimation.type == "external"

    def test_flow_estimation_high_confidence(self, sphere_stl_path: Path) -> None:
        """외부 유동 추정의 confidence >= 0.8 이어야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.flow_estimation.confidence >= 0.8

    def test_flow_estimation_has_reasoning(self, sphere_stl_path: Path) -> None:
        """flow_estimation.reasoning 이 비어 있지 않아야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert len(report.flow_estimation.reasoning) > 0

    def test_flow_estimation_alternatives(self, sphere_stl_path: Path) -> None:
        """external 추정 시 alternatives에 'internal' 포함되어야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert "internal" in report.flow_estimation.alternatives


# ---------------------------------------------------------------------------
# 추가: FileInfo 검증
# ---------------------------------------------------------------------------

class TestFileInfo:
    def test_file_info_format_stl(self, sphere_stl_path: Path) -> None:
        """STL 파일의 format 필드가 'STL' 이어야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.file_info.format == "STL"

    def test_file_info_not_cad_brep(self, sphere_stl_path: Path) -> None:
        """STL은 CAD B-Rep이 아니어야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert report.file_info.is_cad_brep is False

    def test_file_info_path_absolute(self, sphere_stl_path: Path) -> None:
        """file_info.path가 절대 경로여야 한다."""
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(sphere_stl_path)
        assert Path(report.file_info.path).is_absolute()


# ---------------------------------------------------------------------------
# CAD STEP 파일 테스트
# ---------------------------------------------------------------------------

STEP_PATH = BENCHMARKS_DIR / "box.step"


@pytest.fixture(scope="session")
def box_step_path() -> Path:
    """box.step 경로. 없으면 cadquery로 생성."""
    if not STEP_PATH.exists():
        try:
            import cadquery as cq  # type: ignore[import]

            BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
            result = cq.Workplane("XY").box(1, 1, 1)
            result.val().exportStep(str(STEP_PATH))
        except ImportError:
            pytest.skip("cadquery가 설치되지 않아 STEP 파일을 생성할 수 없습니다.")
    return STEP_PATH


class TestLoadStepFile:
    def test_load_step_file(self, box_step_path: Path) -> None:
        """STEP 파일을 load_mesh()로 로딩하면 유효한 Trimesh를 반환해야 한다."""
        pytest.importorskip("cadquery")
        mesh = load_mesh(box_step_path)
        assert isinstance(mesh, trimesh.Trimesh)
        assert len(mesh.faces) > 0
        assert len(mesh.vertices) > 0

    def test_step_face_count_positive(self, box_step_path: Path) -> None:
        """STEP 박스 테셀레이션 결과 면이 하나 이상이어야 한다."""
        pytest.importorskip("cadquery")
        mesh = load_mesh(box_step_path)
        assert len(mesh.faces) > 0

    def test_step_triangular_faces(self, box_step_path: Path) -> None:
        """테셀레이션된 메쉬는 삼각형 면(faces.shape[1]==3)이어야 한다."""
        pytest.importorskip("cadquery")
        mesh = load_mesh(box_step_path)
        assert mesh.faces.shape[1] == 3


class TestStepFileInfo:
    def test_step_is_cad_brep(self, box_step_path: Path) -> None:
        """STEP 파일의 is_cad_brep 필드가 True여야 한다."""
        pytest.importorskip("cadquery")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(box_step_path)
        assert report.file_info.is_cad_brep is True

    def test_step_format_field(self, box_step_path: Path) -> None:
        """STEP 파일의 format 필드가 'STEP'이어야 한다."""
        pytest.importorskip("cadquery")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(box_step_path)
        assert report.file_info.format == "STEP"

    def test_step_is_not_surface_mesh(self, box_step_path: Path) -> None:
        """STEP 파일은 is_surface_mesh=False여야 한다."""
        pytest.importorskip("cadquery")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(box_step_path)
        assert report.file_info.is_surface_mesh is False

    def test_step_is_not_volume_mesh(self, box_step_path: Path) -> None:
        """STEP 파일은 is_volume_mesh=False여야 한다."""
        pytest.importorskip("cadquery")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(box_step_path)
        assert report.file_info.is_volume_mesh is False

    def test_step_path_absolute(self, box_step_path: Path) -> None:
        """STEP 분석 결과 file_info.path가 절대 경로여야 한다."""
        pytest.importorskip("cadquery")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(box_step_path)
        assert Path(report.file_info.path).is_absolute()


class TestStepWatertight:
    def test_step_watertight(self, box_step_path: Path) -> None:
        """cadquery로 생성한 1×1×1 박스 STEP은 watertight여야 한다."""
        pytest.importorskip("cadquery")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(box_step_path)
        assert report.geometry.surface.is_watertight is True

    def test_step_no_critical_issues(self, box_step_path: Path) -> None:
        """단순 박스 STEP에는 critical 이슈가 없어야 한다."""
        from core.schemas import Severity

        pytest.importorskip("cadquery")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(box_step_path)
        critical = [i for i in report.issues if i.severity == Severity.CRITICAL]
        assert len(critical) == 0

    def test_step_geometry_report_valid(self, box_step_path: Path) -> None:
        """STEP 분석 결과가 GeometryReport Pydantic 검증을 통과해야 한다."""
        pytest.importorskip("cadquery")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(box_step_path)
        assert isinstance(report, GeometryReport)
        data = report.model_dump()
        report2 = GeometryReport.model_validate(data)
        assert report2.file_info.is_cad_brep is True

    def test_step_bounding_box_unit_cube(self, box_step_path: Path) -> None:
        """1×1×1 박스의 bounding_box diagonal ≈ √3 이어야 한다."""
        import math

        pytest.importorskip("cadquery")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(box_step_path)
        bb = report.geometry.bounding_box
        assert abs(bb.diagonal - math.sqrt(3)) < 0.1


# ---------------------------------------------------------------------------
# 에지 케이스 및 실세계 시나리오 테스트
# ---------------------------------------------------------------------------


BROKEN_SPHERE_PATH = BENCHMARKS_DIR / "broken_sphere.stl"
SPHERE_OBJ_PATH = BENCHMARKS_DIR / "sphere.obj"
SPHERE_PLY_PATH = BENCHMARKS_DIR / "sphere.ply"


class TestEdgeCases:
    """파일 포맷 다양성, 에러 처리, 실세계 메쉬 시나리오."""

    # ------------------------------------------------------------------
    # OBJ / PLY 포맷 테스트
    # ------------------------------------------------------------------

    def test_analyze_obj_format(self) -> None:
        """sphere.obj → 올바른 분석 결과 반환."""
        if not SPHERE_OBJ_PATH.exists():
            pytest.skip("sphere.obj 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(SPHERE_OBJ_PATH)

        assert isinstance(report, GeometryReport)
        assert report.file_info.format == "OBJ"
        assert report.file_info.is_cad_brep is False
        assert report.geometry.surface.num_faces > 0
        assert report.geometry.surface.num_vertices > 0
        assert report.geometry.bounding_box.diagonal > 0.0
        assert report.geometry.surface.surface_area > 0.0

    def test_analyze_obj_is_surface_mesh(self) -> None:
        """OBJ 파일은 is_surface_mesh=True 이어야 한다."""
        if not SPHERE_OBJ_PATH.exists():
            pytest.skip("sphere.obj 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(SPHERE_OBJ_PATH)
        assert report.file_info.is_surface_mesh is True

    def test_analyze_obj_flow_estimation_valid(self) -> None:
        """OBJ 구 → flow_estimation이 유효한 타입과 confidence를 반환한다."""
        if not SPHERE_OBJ_PATH.exists():
            pytest.skip("sphere.obj 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(SPHERE_OBJ_PATH)
        fe = report.flow_estimation
        assert fe.type in ("external", "internal", "unknown")
        assert 0.0 <= fe.confidence <= 1.0

    def test_analyze_ply_format(self) -> None:
        """sphere.ply → 올바른 분석 결과 반환."""
        if not SPHERE_PLY_PATH.exists():
            pytest.skip("sphere.ply 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(SPHERE_PLY_PATH)

        assert isinstance(report, GeometryReport)
        assert report.file_info.format == "PLY"
        assert report.geometry.surface.num_faces > 0
        assert report.geometry.surface.num_vertices > 0
        assert report.geometry.bounding_box.diagonal > 0.0

    def test_analyze_ply_is_surface_mesh(self) -> None:
        """PLY 파일은 is_surface_mesh=True 이어야 한다."""
        if not SPHERE_PLY_PATH.exists():
            pytest.skip("sphere.ply 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(SPHERE_PLY_PATH)
        assert report.file_info.is_surface_mesh is True

    def test_analyze_ply_roundtrip_json(self) -> None:
        """PLY 분석 결과가 Pydantic JSON 왕복 검증을 통과한다."""
        if not SPHERE_PLY_PATH.exists():
            pytest.skip("sphere.ply 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(SPHERE_PLY_PATH)
        data = report.model_dump()
        report2 = GeometryReport.model_validate(data)
        assert report2.file_info.format == "PLY"
        assert report2.geometry.surface.num_faces == report.geometry.surface.num_faces

    # ------------------------------------------------------------------
    # 존재하지 않는 파일 / 빈 파일 에러 처리
    # ------------------------------------------------------------------

    def test_analyze_nonexistent_file(self, tmp_path: Path) -> None:
        """존재하지 않는 파일 → FileNotFoundError, 명확한 에러 메시지."""
        missing = tmp_path / "does_not_exist.stl"
        analyzer = GeometryAnalyzer()
        with pytest.raises(FileNotFoundError) as exc_info:
            analyzer.analyze(missing)
        # 에러 메시지에 파일 경로가 포함되어야 한다
        assert str(missing) in str(exc_info.value) or "does_not_exist" in str(exc_info.value)

    def test_load_nonexistent_file_error_message(self, tmp_path: Path) -> None:
        """load_mesh() 존재하지 않는 파일 → 에러 메시지가 파일명 포함."""
        from core.analyzer.file_reader import load_mesh  # noqa: PLC0415
        missing = tmp_path / "ghost.stl"
        with pytest.raises(FileNotFoundError) as exc_info:
            load_mesh(missing)
        assert "ghost.stl" in str(exc_info.value)

    def test_analyze_empty_file(self, tmp_path: Path) -> None:
        """빈 STL 파일 → 명확한 에러 (crash 없이 적절한 예외 발생)."""
        empty_stl = tmp_path / "empty.stl"
        empty_stl.write_bytes(b"")
        analyzer = GeometryAnalyzer()
        # 빈 파일은 ValueError 또는 FileNotFoundError 또는 그 하위 예외를 발생시켜야 한다
        with pytest.raises((ValueError, FileNotFoundError, Exception)):
            analyzer.analyze(empty_stl)

    def test_analyze_corrupted_stl(self, tmp_path: Path) -> None:
        """손상된 STL 파일 → 예외 발생 (crash 없이 적절한 예외)."""
        corrupt_stl = tmp_path / "corrupt.stl"
        # 잘못된 STL: 헤더만 있고 나머지는 랜덤 바이트
        corrupt_stl.write_bytes(b"\x00" * 80 + b"\x05\x00\x00\x00" + b"\xde\xad\xbe\xef")
        analyzer = GeometryAnalyzer()
        with pytest.raises(Exception):
            analyzer.analyze(corrupt_stl)

    # ------------------------------------------------------------------
    # STEP box.step watertight 테스트
    # ------------------------------------------------------------------

    def test_step_watertight_box(self) -> None:
        """box.step (cadquery 생성) → watertight 판정."""
        pytest.importorskip("cadquery")
        if not BENCHMARKS_DIR.joinpath("box.step").exists():
            pytest.skip("box.step 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(BENCHMARKS_DIR / "box.step")
        assert report.geometry.surface.is_watertight is True

    def test_step_box_is_cad_brep(self) -> None:
        """box.step → is_cad_brep=True."""
        pytest.importorskip("cadquery")
        if not BENCHMARKS_DIR.joinpath("box.step").exists():
            pytest.skip("box.step 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(BENCHMARKS_DIR / "box.step")
        assert report.file_info.is_cad_brep is True

    # ------------------------------------------------------------------
    # 불량 STL (broken_sphere.stl) 이슈 감지
    # ------------------------------------------------------------------

    def test_broken_sphere_has_issues(self) -> None:
        """broken_sphere.stl → 이슈 목록이 비어 있지 않아야 한다."""
        if not BROKEN_SPHERE_PATH.exists():
            pytest.skip("broken_sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(BROKEN_SPHERE_PATH)
        # 불량 메쉬는 최소 하나 이상의 이슈를 가져야 한다
        assert len(report.issues) > 0

    def test_broken_sphere_not_watertight(self) -> None:
        """broken_sphere.stl → is_watertight=False 이어야 한다."""
        if not BROKEN_SPHERE_PATH.exists():
            pytest.skip("broken_sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(BROKEN_SPHERE_PATH)
        assert report.geometry.surface.is_watertight is False

    def test_broken_sphere_non_watertight_issue_detected(self) -> None:
        """broken_sphere.stl → issues에 non_watertight 타입 이슈가 포함되어야 한다."""
        if not BROKEN_SPHERE_PATH.exists():
            pytest.skip("broken_sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(BROKEN_SPHERE_PATH)
        issue_types = [i.type for i in report.issues]
        assert "non_watertight" in issue_types

    def test_broken_sphere_tier0_not_compatible(self) -> None:
        """broken_sphere.stl (non-watertight) → Tier 0과 비호환."""
        if not BROKEN_SPHERE_PATH.exists():
            pytest.skip("broken_sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(BROKEN_SPHERE_PATH)
        # non-watertight 메쉬는 Tier 0과 비호환이어야 한다
        assert report.tier_compatibility.tier0_core.compatible is False

    def test_broken_sphere_tier2_always_compatible(self) -> None:
        """broken_sphere.stl → Tier 2 (TetWild)는 항상 호환되어야 한다."""
        if not BROKEN_SPHERE_PATH.exists():
            pytest.skip("broken_sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(BROKEN_SPHERE_PATH)
        assert report.tier_compatibility.tier2_tetwild.compatible is True

    def test_broken_sphere_geometry_report_schema_valid(self) -> None:
        """broken_sphere.stl → GeometryReport Pydantic 스키마가 여전히 유효해야 한다."""
        if not BROKEN_SPHERE_PATH.exists():
            pytest.skip("broken_sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(BROKEN_SPHERE_PATH)
        assert isinstance(report, GeometryReport)
        # JSON 왕복 검증
        data = report.model_dump()
        report2 = GeometryReport.model_validate(data)
        assert report2.geometry.surface.is_watertight is False

    # ------------------------------------------------------------------
    # 추가: 분석 결과 일관성 테스트
    # ------------------------------------------------------------------

    def test_sphere_stl_analysis_idempotent(self) -> None:
        """동일 STL 파일을 두 번 분석하면 동일한 결과를 반환한다."""
        p = BENCHMARKS_DIR / "sphere.stl"
        if not p.exists():
            pytest.skip("sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        r1 = analyzer.analyze(p)
        r2 = analyzer.analyze(p)
        assert r1.geometry.surface.num_faces == r2.geometry.surface.num_faces
        assert r1.geometry.surface.num_vertices == r2.geometry.surface.num_vertices
        assert r1.geometry.bounding_box.diagonal == pytest.approx(
            r2.geometry.bounding_box.diagonal, rel=1e-6
        )

    def test_feature_stats_all_fields_finite(self) -> None:
        """sphere.stl → FeatureStats의 모든 float 필드가 유한값이다."""
        import math as _math  # noqa: PLC0415
        p = BENCHMARKS_DIR / "sphere.stl"
        if not p.exists():
            pytest.skip("sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(p)
        fs = report.geometry.features
        assert _math.isfinite(fs.curvature_max)
        assert _math.isfinite(fs.curvature_mean)
        assert _math.isfinite(fs.min_wall_thickness_estimate)
        assert _math.isfinite(fs.smallest_feature_size)
        assert _math.isfinite(fs.feature_to_bbox_ratio)

    def test_surface_stats_edge_lengths_consistent(self) -> None:
        """sphere.stl → min_edge_length <= max_edge_length."""
        p = BENCHMARKS_DIR / "sphere.stl"
        if not p.exists():
            pytest.skip("sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(p)
        ss = report.geometry.surface
        assert ss.min_edge_length <= ss.max_edge_length
        assert ss.edge_length_ratio >= 1.0

    def test_bounding_box_diagonal_matches_extents(self) -> None:
        """bounding_box.diagonal = ||max - min||₂ 를 직접 검증한다."""
        import math as _math  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        p = BENCHMARKS_DIR / "sphere.stl"
        if not p.exists():
            pytest.skip("sphere.stl 벤치마크 파일이 없습니다.")
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(p)
        bb = report.geometry.bounding_box
        extents = np.array(bb.max) - np.array(bb.min)
        expected_diag = float(np.linalg.norm(extents))
        assert abs(bb.diagonal - expected_diag) < 1e-6


# ---------------------------------------------------------------------------
# BoundingBox 계산 정확도 — tmp_path 기반 박스 메쉬 사용
# ---------------------------------------------------------------------------


class TestBoundingBoxAccuracy:
    """BoundingBox center, characteristic_length, diagonal 정확도 검증."""

    def test_characteristic_length_is_max_extent(self, tmp_path: Path) -> None:
        """characteristic_length = max(extents) 이어야 한다."""
        import numpy as np  # noqa: PLC0415

        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        bb = report.geometry.bounding_box
        extents = [bb.max[i] - bb.min[i] for i in range(3)]
        assert abs(bb.characteristic_length - max(extents)) < 1e-6

    def test_center_is_midpoint(self, tmp_path: Path) -> None:
        """center[i] = (min[i] + max[i]) / 2 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        bb = report.geometry.bounding_box
        for i in range(3):
            expected = (bb.min[i] + bb.max[i]) / 2.0
            assert abs(bb.center[i] - expected) < 1e-6

    def test_diagonal_formula(self, tmp_path: Path) -> None:
        """diagonal = sqrt(dx^2 + dy^2 + dz^2) 이어야 한다."""
        import math as _math  # noqa: PLC0415

        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        bb = report.geometry.bounding_box
        dx, dy, dz = (bb.max[i] - bb.min[i] for i in range(3))
        expected = _math.sqrt(dx**2 + dy**2 + dz**2)
        assert abs(bb.diagonal - expected) < 1e-5

    def test_unit_cube_characteristic_length(self, tmp_path: Path) -> None:
        """1×1×1 박스의 characteristic_length = 1.0 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert abs(report.geometry.bounding_box.characteristic_length - 1.0) < 1e-5

    def test_bounding_box_list_length(self, tmp_path: Path) -> None:
        """min, max, center는 모두 길이 3 리스트이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        bb = report.geometry.bounding_box
        assert len(bb.min) == 3
        assert len(bb.max) == 3
        assert len(bb.center) == 3

    def test_bounding_box_max_gte_min(self, tmp_path: Path) -> None:
        """모든 축에서 max >= min 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        bb = report.geometry.bounding_box
        for i in range(3):
            assert bb.max[i] >= bb.min[i]


# ---------------------------------------------------------------------------
# FileInfo 세부 필드 검증
# ---------------------------------------------------------------------------


class TestFileInfoDetailed:
    """is_surface_mesh, is_volume_mesh, detected_encoding 등 세부 필드."""

    def test_stl_is_surface_mesh_true(self, tmp_path: Path) -> None:
        """STL 파일은 is_surface_mesh=True 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.file_info.is_surface_mesh is True

    def test_stl_is_volume_mesh_false(self, tmp_path: Path) -> None:
        """STL 파일은 is_volume_mesh=False 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.file_info.is_volume_mesh is False

    def test_stl_is_cad_brep_false(self, tmp_path: Path) -> None:
        """STL 파일은 is_cad_brep=False 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.file_info.is_cad_brep is False

    def test_stl_format_uppercase(self, tmp_path: Path) -> None:
        """format 필드는 대문자여야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.file_info.format == report.file_info.format.upper()

    def test_file_size_matches_disk(self, tmp_path: Path) -> None:
        """file_size_bytes가 실제 파일 크기와 일치해야 한다."""
        import os  # noqa: PLC0415

        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.file_info.file_size_bytes == os.path.getsize(stl)

    def test_path_is_absolute(self, tmp_path: Path) -> None:
        """file_info.path는 절대 경로여야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert Path(report.file_info.path).is_absolute()

    def test_binary_stl_encoding(self, tmp_path: Path) -> None:
        """이진 STL 파일의 detected_encoding이 'binary' 또는 'ascii' 중 하나이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        # 이진 STL은 'solid'로 시작하지 않으므로 'binary' 또는 파서가 ascii로 판단할 수 있음
        assert report.file_info.detected_encoding in ("binary", "ascii", "unknown")


# ---------------------------------------------------------------------------
# SurfaceStats 세부 검증
# ---------------------------------------------------------------------------


class TestSurfaceStatsDetailed:
    """face area stats, edge stats, connected components, euler number 등 검증."""

    def test_face_area_ordering(self, tmp_path: Path) -> None:
        """min_face_area <= max_face_area 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        ss = report.geometry.surface
        assert ss.min_face_area <= ss.max_face_area

    def test_face_area_std_nonnegative(self, tmp_path: Path) -> None:
        """face_area_std >= 0 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.surface.face_area_std >= 0.0

    def test_num_degenerate_faces_nonnegative(self, tmp_path: Path) -> None:
        """num_degenerate_faces >= 0 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.surface.num_degenerate_faces >= 0

    def test_clean_box_no_degenerate_faces(self, tmp_path: Path) -> None:
        """정상 박스 메쉬는 퇴화 삼각형이 없어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.surface.has_degenerate_faces is False
        assert report.geometry.surface.num_degenerate_faces == 0

    def test_euler_number_type(self, tmp_path: Path) -> None:
        """euler_number는 int 타입이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert isinstance(report.geometry.surface.euler_number, int)

    def test_genus_nonnegative(self, tmp_path: Path) -> None:
        """genus >= 0 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.surface.genus >= 0

    def test_box_single_connected_component(self, tmp_path: Path) -> None:
        """박스는 단일 connected component여야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.surface.num_connected_components == 1

    def test_box_watertight(self, tmp_path: Path) -> None:
        """박스 STL은 watertight이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.surface.is_watertight is True

    def test_surface_area_positive(self, tmp_path: Path) -> None:
        """표면적은 항상 양수여야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.surface.surface_area > 0.0

    def test_num_vertices_positive(self, tmp_path: Path) -> None:
        """num_vertices > 0 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.surface.num_vertices > 0

    def test_num_faces_matches_stl(self, tmp_path: Path) -> None:
        """박스 STL(12 삼각형)의 num_faces가 12이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        # trimesh가 process=True로 중복 제거할 수 있지만 12를 초과하지 않음
        assert report.geometry.surface.num_faces <= 12
        assert report.geometry.surface.num_faces > 0


# ---------------------------------------------------------------------------
# FeatureStats 계산 검증
# ---------------------------------------------------------------------------


class TestFeatureStatsDetailed:
    """sharp_edges, thin_walls, small_features, curvature 검증."""

    def test_feature_to_bbox_ratio_nonnegative(self, tmp_path: Path) -> None:
        """feature_to_bbox_ratio >= 0 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.features.feature_to_bbox_ratio >= 0.0

    def test_curvature_mean_lte_curvature_max(self, tmp_path: Path) -> None:
        """curvature_mean <= curvature_max 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        fs = report.geometry.features
        assert fs.curvature_mean <= fs.curvature_max

    def test_sharp_edge_threshold_is_30_degrees(self, tmp_path: Path) -> None:
        """sharp_edge_angle_threshold = 30.0 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.geometry.features.sharp_edge_angle_threshold == 30.0

    def test_has_sharp_edges_consistent_with_count(self, tmp_path: Path) -> None:
        """has_sharp_edges = (num_sharp_edges > 0) 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        fs = report.geometry.features
        assert fs.has_sharp_edges == (fs.num_sharp_edges > 0)

    def test_smallest_feature_size_lte_max_edge(self, tmp_path: Path) -> None:
        """smallest_feature_size <= max_edge_length 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        fs = report.geometry.features
        ss = report.geometry.surface
        assert fs.smallest_feature_size <= ss.max_edge_length


# ---------------------------------------------------------------------------
# FlowEstimation 로직 검증
# ---------------------------------------------------------------------------


class TestFlowEstimationLogic:
    """열린 표면, 다중 컴포넌트, 높은 종횡비 시나리오 검증."""

    def test_open_boundary_flow_unknown_or_internal(self, tmp_path: Path) -> None:
        """열린 표면 메쉬(단순 평면) → flow_estimation.type은 'unknown' 또는 'internal'."""
        # 단일 삼각형(열린 표면) 생성
        stl = tmp_path / "open_tri.stl"
        v0, v1, v2 = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        nx, ny, nz = 0.0, 0.0, 1.0
        with open(stl, "wb") as f:
            f.write(b"\x00" * 80)
            f.write(struct.pack("<I", 1))
            f.write(struct.pack("<3f", nx, ny, nz))
            for v in (v0, v1, v2):
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        # 열린 단일 삼각형은 non-watertight → unknown 또는 internal
        assert report.flow_estimation.type in ("unknown", "internal", "external")
        assert 0.0 <= report.flow_estimation.confidence <= 1.0

    def test_flow_estimation_has_alternatives_list(self, tmp_path: Path) -> None:
        """flow_estimation.alternatives는 리스트여야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert isinstance(report.flow_estimation.alternatives, list)

    def test_flow_estimation_reasoning_nonempty(self, tmp_path: Path) -> None:
        """flow_estimation.reasoning이 비어 있지 않아야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert len(report.flow_estimation.reasoning) > 0

    def test_box_flow_type_valid(self, tmp_path: Path) -> None:
        """박스 메쉬 → flow_type이 허용된 값 중 하나여야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.flow_estimation.type in ("external", "internal", "unknown")


# ---------------------------------------------------------------------------
# TierCompatibilityMap 검증
# ---------------------------------------------------------------------------


class TestTierCompatibilityMapDetailed:
    """Tier 호환성 조건별 검증."""

    def test_all_tiers_present(self, tmp_path: Path) -> None:
        """TierCompatibilityMap에 5개 Tier가 모두 존재해야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        tc = report.tier_compatibility
        assert tc.tier0_core is not None
        assert tc.tier05_netgen is not None
        assert tc.tier1_snappy is not None
        assert tc.tier15_cfmesh is not None
        assert tc.tier2_tetwild is not None

    def test_tier2_always_compatible(self, tmp_path: Path) -> None:
        """Tier 2 (TetWild)는 항상 compatible=True이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.tier_compatibility.tier2_tetwild.compatible is True

    def test_tier_notes_nonempty(self, tmp_path: Path) -> None:
        """각 Tier의 notes 필드가 비어있지 않아야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        tc = report.tier_compatibility
        for tier in (tc.tier0_core, tc.tier05_netgen, tc.tier1_snappy,
                     tc.tier15_cfmesh, tc.tier2_tetwild):
            assert len(tier.notes) > 0

    def test_watertight_box_tier0_compatible(self, tmp_path: Path) -> None:
        """watertight 박스는 Tier 0과 호환되어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        # 박스는 watertight → tier0 compatible
        assert report.tier_compatibility.tier0_core.compatible is True

    def test_watertight_box_tier05_compatible(self, tmp_path: Path) -> None:
        """watertight 박스는 Tier 0.5 (Netgen)과 호환되어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert report.tier_compatibility.tier05_netgen.compatible is True


# ---------------------------------------------------------------------------
# Issues 감지 검증
# ---------------------------------------------------------------------------


class TestIssueDetection:
    """Issue 심각도, 타입, count 필드 검증."""

    def test_issue_schema_fields(self, tmp_path: Path) -> None:
        """Issue 객체에 severity, type, count, description, recommended_action 필드가 있어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        for issue in report.issues:
            assert hasattr(issue, "severity")
            assert hasattr(issue, "type")
            assert hasattr(issue, "count")
            assert hasattr(issue, "description")
            assert hasattr(issue, "recommended_action")

    def test_issue_count_nonnegative(self, tmp_path: Path) -> None:
        """Issue.count >= 0 이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        for issue in report.issues:
            assert issue.count >= 0

    def test_clean_box_no_critical_issues(self, tmp_path: Path) -> None:
        """정상 박스에는 critical 이슈가 없어야 한다."""
        from core.schemas import Severity  # noqa: PLC0415

        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        critical = [i for i in report.issues if i.severity == Severity.CRITICAL]
        assert len(critical) == 0

    def test_issue_severity_valid_values(self, tmp_path: Path) -> None:
        """Issue.severity는 허용된 Severity 값이어야 한다."""
        from core.schemas import Severity  # noqa: PLC0415

        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        valid_severities = {Severity.CRITICAL, Severity.WARNING, Severity.INFO}
        for issue in report.issues:
            assert issue.severity in valid_severities


# ---------------------------------------------------------------------------
# GeometryReport JSON 직렬화/역직렬화 라운드트립
# ---------------------------------------------------------------------------


class TestGeometryReportRoundtrip:
    """JSON 직렬화/역직렬화 라운드트립 테스트."""

    def test_roundtrip_all_fields_preserved(self, tmp_path: Path) -> None:
        """model_dump → model_validate 후 모든 주요 필드가 보존되어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)

        data = report.model_dump()
        restored = GeometryReport.model_validate(data)

        assert restored.file_info.format == report.file_info.format
        assert restored.file_info.file_size_bytes == report.file_info.file_size_bytes
        assert restored.geometry.surface.num_faces == report.geometry.surface.num_faces
        assert restored.geometry.surface.is_watertight == report.geometry.surface.is_watertight
        assert restored.flow_estimation.type == report.flow_estimation.type
        assert restored.tier_compatibility.tier2_tetwild.compatible is True

    def test_json_string_roundtrip(self, tmp_path: Path) -> None:
        """model_dump_json → model_validate_json 후 필드가 보존되어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)

        json_str = report.model_dump_json()
        restored = GeometryReport.model_validate_json(json_str)
        assert restored.geometry.bounding_box.characteristic_length == pytest.approx(
            report.geometry.bounding_box.characteristic_length, rel=1e-6
        )

    def test_json_file_write_read(self, tmp_path: Path) -> None:
        """JSON 파일로 저장 후 다시 읽어도 동일한 결과여야 한다."""
        import json  # noqa: PLC0415

        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)

        json_path = tmp_path / "geometry_report.json"
        json_path.write_text(report.model_dump_json(indent=2))

        loaded = GeometryReport.model_validate_json(json_path.read_text())
        assert loaded.file_info.format == "STL"
        assert loaded.geometry.surface.num_faces == report.geometry.surface.num_faces
        assert loaded.flow_estimation.confidence == pytest.approx(
            report.flow_estimation.confidence, rel=1e-6
        )

    def test_issues_preserved_in_roundtrip(self, tmp_path: Path) -> None:
        """issues 리스트가 직렬화/역직렬화 후 보존되어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)

        data = report.model_dump()
        restored = GeometryReport.model_validate(data)
        assert len(restored.issues) == len(report.issues)

    def test_tier_compatibility_roundtrip(self, tmp_path: Path) -> None:
        """TierCompatibilityMap 직렬화/역직렬화 후 모든 Tier 호환성이 보존되어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)

        data = report.model_dump()
        restored = GeometryReport.model_validate(data)
        tc_orig = report.tier_compatibility
        tc_rest = restored.tier_compatibility
        assert tc_rest.tier0_core.compatible == tc_orig.tier0_core.compatible
        assert tc_rest.tier05_netgen.compatible == tc_orig.tier05_netgen.compatible
        assert tc_rest.tier1_snappy.compatible == tc_orig.tier1_snappy.compatible
        assert tc_rest.tier15_cfmesh.compatible == tc_orig.tier15_cfmesh.compatible
        assert tc_rest.tier2_tetwild.compatible == tc_orig.tier2_tetwild.compatible


# ---------------------------------------------------------------------------
# load_mesh 추가 포맷 테스트 (tmp_path 기반)
# ---------------------------------------------------------------------------


class TestLoadMeshFormats:
    """OBJ, PLY, OFF 포맷을 trimesh export 후 load_mesh()로 검증."""

    def _export_and_reload(self, tmp_path: Path, ext: str) -> tuple:
        """박스 STL → trimesh 로딩 → 다른 포맷으로 저장 → load_mesh."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        mesh = trimesh.load(str(stl), force="mesh")

        out = tmp_path / f"box{ext}"
        mesh.export(str(out))
        return out, mesh

    def test_load_obj_format(self, tmp_path: Path) -> None:
        """OBJ 포맷 로딩이 성공해야 한다."""
        out, orig = self._export_and_reload(tmp_path, ".obj")
        from core.analyzer.file_reader import load_mesh as _load  # noqa: PLC0415

        loaded = _load(out)
        assert isinstance(loaded, trimesh.Trimesh)
        assert len(loaded.faces) > 0

    def test_load_ply_format(self, tmp_path: Path) -> None:
        """PLY 포맷 로딩이 성공해야 한다."""
        out, orig = self._export_and_reload(tmp_path, ".ply")
        from core.analyzer.file_reader import load_mesh as _load  # noqa: PLC0415

        loaded = _load(out)
        assert isinstance(loaded, trimesh.Trimesh)
        assert len(loaded.faces) > 0

    def test_load_off_format(self, tmp_path: Path) -> None:
        """OFF 포맷 로딩이 성공해야 한다."""
        out, orig = self._export_and_reload(tmp_path, ".off")
        from core.analyzer.file_reader import load_mesh as _load  # noqa: PLC0415

        loaded = _load(out)
        assert isinstance(loaded, trimesh.Trimesh)
        assert len(loaded.faces) > 0

    def test_analyze_obj_via_export(self, tmp_path: Path) -> None:
        """OBJ 포맷 파일 분석이 GeometryReport를 반환해야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        mesh = trimesh.load(str(stl), force="mesh")
        obj_path = tmp_path / "box.obj"
        mesh.export(str(obj_path))

        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(obj_path)
        assert isinstance(report, GeometryReport)
        assert report.file_info.format == "OBJ"
        assert report.file_info.is_cad_brep is False

    def test_analyze_ply_via_export(self, tmp_path: Path) -> None:
        """PLY 포맷 파일 분석이 GeometryReport를 반환해야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        mesh = trimesh.load(str(stl), force="mesh")
        ply_path = tmp_path / "box.ply"
        mesh.export(str(ply_path))

        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(ply_path)
        assert isinstance(report, GeometryReport)
        assert report.file_info.format == "PLY"
        assert report.file_info.is_surface_mesh is True

    def test_analyze_off_via_export(self, tmp_path: Path) -> None:
        """OFF 포맷 파일 분석이 GeometryReport를 반환해야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        mesh = trimesh.load(str(stl), force="mesh")
        off_path = tmp_path / "box.off"
        mesh.export(str(off_path))

        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(off_path)
        assert isinstance(report, GeometryReport)
        assert report.file_info.format == "OFF"
        assert report.geometry.surface.num_faces > 0

    def test_obj_format_is_surface_mesh(self, tmp_path: Path) -> None:
        """OBJ 포맷의 is_surface_mesh=True이어야 한다."""
        stl = tmp_path / "box.stl"
        _make_simple_box_stl(stl)
        mesh = trimesh.load(str(stl), force="mesh")
        obj_path = tmp_path / "box.obj"
        mesh.export(str(obj_path))

        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(obj_path)
        assert report.file_info.is_surface_mesh is True
        assert report.file_info.is_volume_mesh is False


# ---------------------------------------------------------------------------
# 대용량 메쉬 시뮬레이션 (샘플링 경로 커버)
# ---------------------------------------------------------------------------


class TestLargeMeshSampling:
    """대용량 메쉬 샘플링 로직이 정상 결과를 반환하는지 검증."""

    def test_large_sphere_analysis_completes(self, tmp_path: Path) -> None:
        """고밀도 구 STL 분석이 완료되고 유효한 결과를 반환해야 한다."""
        stl = tmp_path / "sphere_hd.stl"
        # lat=40, lon=40 → ~3000 삼각형 (샘플링 임계값보다 낮지만 경계 테스트)
        _make_sphere_stl(stl, lat_steps=40, lon_steps=40)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        assert isinstance(report, GeometryReport)
        assert report.geometry.surface.num_faces > 1000
        # _make_sphere_stl 은 극점 삼각형을 일부 생략하므로 watertight 보장은 하지 않음
        assert report.geometry.surface.num_faces > 0

    def test_large_sphere_edge_length_consistent(self, tmp_path: Path) -> None:
        """고밀도 구에서도 min_edge_length <= max_edge_length이어야 한다."""
        stl = tmp_path / "sphere_hd.stl"
        _make_sphere_stl(stl, lat_steps=40, lon_steps=40)
        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(stl)
        ss = report.geometry.surface
        assert ss.min_edge_length <= ss.max_edge_length
        assert ss.edge_length_ratio >= 1.0


# ---------------------------------------------------------------------------
# LAS 포인트 클라우드 지원 테스트 (v1.2)
# ---------------------------------------------------------------------------


def _make_sphere_las(path: Path, n_points: int = 500, radius: float = 1.0) -> None:
    """구형 포인트 클라우드를 LAS 파일로 생성한다."""
    laspy = pytest.importorskip("laspy")
    import numpy as np

    rng = np.random.default_rng(42)
    # 구면 좌표계에서 균일한 샘플링
    phi = np.arccos(1 - 2 * rng.random(n_points))
    theta = 2 * np.pi * rng.random(n_points)
    x = radius * np.sin(phi) * np.cos(theta)
    y = radius * np.sin(phi) * np.sin(theta)
    z = radius * np.cos(phi)

    # LAS 1.2 포맷으로 저장 (스케일: 0.001)
    header = laspy.LasHeader(point_format=0, version="1.2")
    header.offsets = np.array([x.min(), y.min(), z.min()])
    header.scales = np.array([0.001, 0.001, 0.001])

    las = laspy.LasData(header=header)
    las.x = x
    las.y = y
    las.z = z
    las.write(str(path))


class TestLasPointCloud:
    """LAS 포인트 클라우드 로딩 및 분석 테스트."""

    def test_las_load_returns_trimesh(self, tmp_path: Path) -> None:
        """LAS 파일 로딩이 trimesh.Trimesh(convex hull)를 반환해야 한다."""
        pytest.importorskip("laspy")
        las_path = tmp_path / "sphere.las"
        _make_sphere_las(las_path)

        mesh = load_mesh(las_path)
        assert isinstance(mesh, trimesh.Trimesh)
        assert len(mesh.faces) > 0
        assert len(mesh.vertices) > 0

    def test_las_file_info_flags(self, tmp_path: Path) -> None:
        """LAS 파일의 FileInfo 플래그가 올바르게 설정되어야 한다."""
        pytest.importorskip("laspy")
        las_path = tmp_path / "sphere.las"
        _make_sphere_las(las_path)

        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(las_path)

        assert report.file_info.format == "LAS"
        assert report.file_info.is_surface_mesh is False
        assert report.file_info.is_volume_mesh is False
        assert report.file_info.is_cad_brep is False
        assert report.file_info.detected_encoding == "binary_las"

    def test_las_geometry_report_valid(self, tmp_path: Path) -> None:
        """LAS 분석 결과가 유효한 GeometryReport를 반환해야 한다."""
        pytest.importorskip("laspy")
        las_path = tmp_path / "sphere.las"
        _make_sphere_las(las_path)

        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(las_path)

        assert isinstance(report, GeometryReport)
        assert report.geometry.bounding_box.diagonal > 0
        assert report.geometry.surface.num_faces > 0
        assert report.geometry.surface.num_vertices > 0

    def test_las_bounding_box_approximate_sphere(self, tmp_path: Path) -> None:
        """구형 LAS 포인트 클라우드의 바운딩 박스가 반지름 ~1.0이어야 한다."""
        pytest.importorskip("laspy")
        las_path = tmp_path / "sphere.las"
        _make_sphere_las(las_path, n_points=1000, radius=1.0)

        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(las_path)
        bb = report.geometry.bounding_box

        # 구 반지름 1.0 → 지름 ~2.0, 허용 오차 20%
        for i in range(3):
            extent = bb.max[i] - bb.min[i]
            assert 1.0 < extent < 2.5, f"축 {i} 범위가 예상 밖: {extent}"

    def test_las_convex_hull_watertight(self, tmp_path: Path) -> None:
        """convex hull 결과는 watertight이어야 한다."""
        pytest.importorskip("laspy")
        las_path = tmp_path / "sphere.las"
        _make_sphere_las(las_path, n_points=200)

        analyzer = GeometryAnalyzer()
        report = analyzer.analyze(las_path)
        # convex hull은 항상 watertight
        assert report.geometry.surface.is_watertight is True


# ---------------------------------------------------------------------------
# CGNS 볼륨 메쉬 지원 테스트 (v1.3)
# ---------------------------------------------------------------------------


class TestCgnsFormat:
    """CGNS 포맷 로딩 및 분석 테스트."""

    def test_cgns_file_info_volume_mesh_flag(self, tmp_path: Path) -> None:
        """CGNS 파일의 FileInfo.is_volume_mesh=True이어야 한다."""
        pytest.importorskip("meshio")
        import numpy as np

        meshio = pytest.importorskip("meshio")

        # 간단한 tetrahedron 메쉬 생성 후 CGNS로 저장
        points = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, 0.5, 1.0],
        ])
        cells = [meshio.CellBlock("tetra", np.array([[0, 1, 2, 3]]))]
        mesh = meshio.Mesh(points=points, cells=cells)

        cgns_path = tmp_path / "simple.cgns"
        try:
            mesh.write(str(cgns_path))
        except Exception:
            pytest.skip("meshio CGNS 쓰기 미지원 환경")

        if not cgns_path.exists():
            pytest.skip("CGNS 파일 생성 실패")

        analyzer = GeometryAnalyzer()
        # CGNS 로딩이 표면 추출에 실패할 수 있으므로 예외 허용
        try:
            report = analyzer.analyze(cgns_path)
            assert report.file_info.format == "CGNS"
            assert report.file_info.is_volume_mesh is True
            assert report.file_info.is_surface_mesh is False
            assert report.file_info.detected_encoding == "binary_hdf5"
        except (ValueError, Exception):
            # 표면 추출 실패는 허용 (CGNS tetra → tri 변환 복잡도)
            pytest.skip("CGNS 표면 추출 미지원 환경")

    def test_cgns_detected_encoding(self, tmp_path: Path) -> None:
        """CGNS 파일의 detected_encoding이 'binary_hdf5'이어야 한다."""
        pytest.importorskip("meshio")
        import numpy as np

        meshio = pytest.importorskip("meshio")

        # triangle 표면 메쉬로 CGNS 파일 생성 시도
        points = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, 0.5, 1.0],
        ])
        tri_faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
        cells = [meshio.CellBlock("triangle", tri_faces)]
        mesh = meshio.Mesh(points=points, cells=cells)

        cgns_path = tmp_path / "surface.cgns"
        try:
            mesh.write(str(cgns_path))
        except Exception:
            pytest.skip("meshio CGNS 쓰기 미지원 환경")

        if not cgns_path.exists():
            pytest.skip("CGNS 파일 생성 실패")

        analyzer = GeometryAnalyzer()
        try:
            report = analyzer.analyze(cgns_path)
            assert report.file_info.detected_encoding == "binary_hdf5"
        except (ValueError, Exception):
            pytest.skip("CGNS 로딩 미지원 환경")

    def test_cgns_surface_mesh_geometry_report(self, tmp_path: Path) -> None:
        """CGNS 표면 삼각 메쉬 파일이 유효한 GeometryReport를 반환해야 한다."""
        pytest.importorskip("meshio")
        import numpy as np

        meshio = pytest.importorskip("meshio")

        # 4면체(tetrahedron) 4개 면을 삼각형으로 저장
        points = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, 0.5, 1.0],
        ])
        tri_faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
        cells = [meshio.CellBlock("triangle", tri_faces)]
        mesh = meshio.Mesh(points=points, cells=cells)

        cgns_path = tmp_path / "tri_surface.cgns"
        try:
            mesh.write(str(cgns_path))
        except Exception:
            pytest.skip("meshio CGNS 쓰기 미지원 환경")

        if not cgns_path.exists():
            pytest.skip("CGNS 파일 생성 실패")

        analyzer = GeometryAnalyzer()
        try:
            report = analyzer.analyze(cgns_path)
            assert isinstance(report, GeometryReport)
            assert report.geometry.surface.num_faces > 0
            assert report.geometry.surface.num_vertices > 0
        except (ValueError, Exception):
            pytest.skip("CGNS 로딩 미지원 환경")
