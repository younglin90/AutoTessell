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
