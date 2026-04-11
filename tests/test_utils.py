"""core/utils/ 미테스트 모듈 단위 테스트.

대상:
  - core/utils/bc_writer.py
  - core/utils/boundary_classifier.py
  - core/utils/parallel.py     (write_decompose_par_dict)
  - core/utils/profiler.py
  - core/utils/vtk_exporter.py
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# 헬퍼: 간단한 polyMesh 디렉터리 생성
# ---------------------------------------------------------------------------

def _make_polymesh(case_dir: Path) -> Path:
    """테스트용 최소 polyMesh를 생성한다.

    단위 정육면체 하나짜리 tet 메쉬 (4 points, 4 faces, 1 cell).
    faces: 3개는 외부(boundary), 1개는 내부 shared face 없이 단순하게 구성.
    여기서는 boundary 패치 분류 테스트를 위해 BBox 좌표계를 명확히 한다.
    """
    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)

    # 4개 점: 단위 tetrahedron
    points_text = """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       vectorField;
    object      points;
}
4
(
(0 0 0)
(1 0 0)
(0.5 1 0)
(0.5 0.5 1)
)
"""

    # 4개 face (모두 boundary — 내부 인접 없음)
    faces_text = """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       faceList;
    object      faces;
}
4
(
3(0 1 2)
3(0 1 3)
3(1 2 3)
3(0 2 3)
)
"""

    # owner: 모든 face가 cell 0 소유
    owner_text = """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       labelList;
    object      owner;
}
4
(
0
0
0
0
)
"""

    # neighbour: internal face 없음
    neighbour_text = """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       labelList;
    object      neighbour;
}
0
(
)
"""

    # boundary: 4개 패치
    boundary_text = """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       polyBoundaryMesh;
    object      boundary;
}
4
(
    inlet
    {
        type    patch;
        nFaces  1;
        startFace 0;
    }
    outlet
    {
        type    patch;
        nFaces  1;
        startFace 1;
    }
    wall
    {
        type    wall;
        nFaces  1;
        startFace 2;
    }
    top
    {
        type    patch;
        nFaces  1;
        startFace 3;
    }
)
"""

    (poly_dir / "points").write_text(points_text)
    (poly_dir / "faces").write_text(faces_text)
    (poly_dir / "owner").write_text(owner_text)
    (poly_dir / "neighbour").write_text(neighbour_text)
    (poly_dir / "boundary").write_text(boundary_text)
    return poly_dir


# ===========================================================================
# bc_writer 테스트
# ===========================================================================

from core.utils.bc_writer import write_boundary_conditions


class TestBcWriter:
    def _patches(self) -> list[dict[str, Any]]:
        return [
            {"name": "inlet", "type": "inlet"},
            {"name": "outlet", "type": "outlet"},
            {"name": "wall", "type": "wall"},
            {"name": "sym", "type": "symmetryPlane"},
        ]

    def test_files_created(self, tmp_path: Path) -> None:
        """write_boundary_conditions가 0/ 아래 5개 파일과 constant/ 2개를 생성한다."""
        written = write_boundary_conditions(tmp_path, self._patches())
        assert "0/p" in written
        assert "0/U" in written
        assert "0/k" in written
        assert "0/omega" in written
        assert "0/nut" in written
        assert "constant/transportProperties" in written
        assert "constant/turbulenceProperties" in written

    def test_zero_dir_created(self, tmp_path: Path) -> None:
        """0/ 디렉터리가 자동으로 생성된다."""
        write_boundary_conditions(tmp_path, self._patches())
        assert (tmp_path / "0").is_dir()

    def test_p_file_exists(self, tmp_path: Path) -> None:
        """0/p 파일이 존재한다."""
        write_boundary_conditions(tmp_path, self._patches())
        assert (tmp_path / "0" / "p").is_file()

    def test_u_file_exists(self, tmp_path: Path) -> None:
        """0/U 파일이 존재한다."""
        write_boundary_conditions(tmp_path, self._patches())
        assert (tmp_path / "0" / "U").is_file()

    def test_foam_file_header_in_p(self, tmp_path: Path) -> None:
        """0/p 파일에 FoamFile 헤더가 포함된다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "0" / "p").read_text()
        assert "FoamFile" in content
        assert "version" in content

    def test_foam_class_volscalarfield_in_p(self, tmp_path: Path) -> None:
        """0/p 파일의 class는 volScalarField이다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "0" / "p").read_text()
        assert "volScalarField" in content

    def test_inlet_p_bc_is_zerogradient(self, tmp_path: Path) -> None:
        """inlet 패치의 압력 BC는 zeroGradient이다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "0" / "p").read_text()
        # inlet block should contain zeroGradient
        assert "zeroGradient" in content

    def test_outlet_p_bc_is_fixedvalue(self, tmp_path: Path) -> None:
        """outlet 패치의 압력 BC는 fixedValue 0이다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "0" / "p").read_text()
        assert "fixedValue" in content

    def test_inlet_u_bc_is_fixedvalue(self, tmp_path: Path) -> None:
        """inlet 패치의 속도 BC는 fixedValue이다."""
        write_boundary_conditions(tmp_path, self._patches(), flow_velocity=2.0)
        content = (tmp_path / "0" / "U").read_text()
        assert "fixedValue" in content
        assert "2.0" in content or "2 0 0" in content

    def test_wall_u_bc_is_noslip(self, tmp_path: Path) -> None:
        """wall 패치의 속도 BC는 noSlip이다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "0" / "U").read_text()
        assert "noSlip" in content

    def test_wall_k_bc_uses_kqrwallfunction(self, tmp_path: Path) -> None:
        """wall 패치의 k BC는 kqRWallFunction이다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "0" / "k").read_text()
        assert "kqRWallFunction" in content

    def test_wall_nut_bc_is_nutkwallfunction(self, tmp_path: Path) -> None:
        """wall 패치의 nut BC는 nutkWallFunction이다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "0" / "nut").read_text()
        assert "nutkWallFunction" in content

    def test_transport_properties_content(self, tmp_path: Path) -> None:
        """transportProperties 파일에 nu와 Newtonian이 포함된다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "constant" / "transportProperties").read_text()
        assert "Newtonian" in content
        assert "nu" in content

    def test_turbulence_properties_model(self, tmp_path: Path) -> None:
        """turbulenceProperties 파일에 지정된 난류 모델이 포함된다."""
        write_boundary_conditions(tmp_path, self._patches(), turbulence_model="kEpsilon")
        content = (tmp_path / "constant" / "turbulenceProperties").read_text()
        assert "kEpsilon" in content

    def test_empty_patches(self, tmp_path: Path) -> None:
        """패치가 없어도 파일이 정상 생성된다."""
        written = write_boundary_conditions(tmp_path, [])
        assert len(written) == 7  # 5 field + 2 constant

    def test_symmetry_u_bc(self, tmp_path: Path) -> None:
        """symmetryPlane 패치의 속도 BC는 symmetry이다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "0" / "U").read_text()
        assert "symmetry" in content

    def test_omega_file_created(self, tmp_path: Path) -> None:
        """0/omega 파일이 생성된다."""
        write_boundary_conditions(tmp_path, self._patches())
        assert (tmp_path / "0" / "omega").is_file()

    def test_wall_omega_bc_uses_wallfunction(self, tmp_path: Path) -> None:
        """wall 패치의 omega BC는 omegaWallFunction이다."""
        write_boundary_conditions(tmp_path, self._patches())
        content = (tmp_path / "0" / "omega").read_text()
        assert "omegaWallFunction" in content


# ===========================================================================
# boundary_classifier 테스트
# ===========================================================================

from core.utils.boundary_classifier import (
    classify_boundaries,
    _classify_patch,
    _classify_external,
    _classify_internal,
)


class TestBoundaryClassifierNameHints:
    """이름 기반 힌트로 분류되는 케이스."""

    def _dummy_bbox(self):
        bbox_min = np.zeros(3)
        bbox_max = np.ones(3)
        bbox_size = np.ones(3)
        center = np.array([0.5, 0.5, 0.5])
        normal = np.array([1.0, 0.0, 0.0])
        return center, normal, bbox_min, bbox_max, bbox_size

    def test_inlet_name_returns_inlet(self) -> None:
        c, n, bmin, bmax, bs = self._dummy_bbox()
        result = _classify_patch("inlet_patch", c, n, bmin, bmax, bs, "external", 0, 10)
        assert result == "inlet"

    def test_inflow_name_returns_inlet(self) -> None:
        c, n, bmin, bmax, bs = self._dummy_bbox()
        result = _classify_patch("inflow", c, n, bmin, bmax, bs, "external", 0, 10)
        assert result == "inlet"

    def test_outlet_name_returns_outlet(self) -> None:
        c, n, bmin, bmax, bs = self._dummy_bbox()
        result = _classify_patch("outlet_patch", c, n, bmin, bmax, bs, "external", 0, 10)
        assert result == "outlet"

    def test_exit_name_returns_outlet(self) -> None:
        c, n, bmin, bmax, bs = self._dummy_bbox()
        result = _classify_patch("exit_plane", c, n, bmin, bmax, bs, "external", 0, 10)
        assert result == "outlet"

    def test_wall_name_returns_wall(self) -> None:
        c, n, bmin, bmax, bs = self._dummy_bbox()
        result = _classify_patch("wallPatch", c, n, bmin, bmax, bs, "external", 0, 10)
        assert result == "wall"

    def test_body_name_returns_wall(self) -> None:
        c, n, bmin, bmax, bs = self._dummy_bbox()
        result = _classify_patch("body_surface", c, n, bmin, bmax, bs, "external", 0, 10)
        assert result == "wall"

    def test_sym_name_returns_symmetry(self) -> None:
        c, n, bmin, bmax, bs = self._dummy_bbox()
        result = _classify_patch("symPlane", c, n, bmin, bmax, bs, "external", 0, 10)
        assert result == "symmetryPlane"

    def test_default_name_returns_wall(self) -> None:
        c, n, bmin, bmax, bs = self._dummy_bbox()
        result = _classify_patch("defaultFaces", c, n, bmin, bmax, bs, "external", 0, 10)
        assert result == "wall"


class TestClassifyExternal:
    """외부 유동 위치 기반 분류."""

    def _bbox(self):
        return np.zeros(3), np.ones(3), np.ones(3)

    def test_min_x_is_inlet(self) -> None:
        bmin, bmax, bs = self._bbox()
        center = np.array([0.02, 0.5, 0.5])  # x방향 앞쪽
        normal = np.array([1.0, 0.0, 0.0])
        result = _classify_external(center, normal, bmin, bmax, bs, flow_dir=0)
        assert result == "inlet"

    def test_max_x_is_outlet(self) -> None:
        bmin, bmax, bs = self._bbox()
        center = np.array([0.98, 0.5, 0.5])  # x방향 뒤쪽
        normal = np.array([1.0, 0.0, 0.0])
        result = _classify_external(center, normal, bmin, bmax, bs, flow_dir=0)
        assert result == "outlet"

    def test_side_face_is_wall(self) -> None:
        bmin, bmax, bs = self._bbox()
        center = np.array([0.5, 0.02, 0.5])  # y 최소면 (측면)
        normal = np.array([0.0, 1.0, 0.0])
        result = _classify_external(center, normal, bmin, bmax, bs, flow_dir=0)
        assert result == "wall"

    def test_interior_body_is_wall(self) -> None:
        bmin, bmax, bs = self._bbox()
        center = np.array([0.5, 0.5, 0.5])  # 도메인 내부
        normal = np.array([0.0, 1.0, 0.0])
        result = _classify_external(center, normal, bmin, bmax, bs, flow_dir=0)
        assert result == "wall"


class TestClassifyInternal:
    """내부 유동 위치 기반 분류."""

    def _bbox(self):
        return np.zeros(3), np.ones(3), np.ones(3)

    def test_min_z_is_inlet_z_flow(self) -> None:
        bmin, bmax, bs = self._bbox()
        center = np.array([0.5, 0.5, 0.02])
        normal = np.array([0.0, 0.0, 1.0])
        result = _classify_internal(center, normal, bmin, bmax, bs, flow_dir=2, n_faces=10)
        assert result == "inlet"

    def test_max_z_is_outlet_z_flow(self) -> None:
        bmin, bmax, bs = self._bbox()
        center = np.array([0.5, 0.5, 0.98])
        normal = np.array([0.0, 0.0, 1.0])
        result = _classify_internal(center, normal, bmin, bmax, bs, flow_dir=2, n_faces=10)
        assert result == "outlet"

    def test_side_is_wall(self) -> None:
        bmin, bmax, bs = self._bbox()
        center = np.array([0.5, 0.5, 0.5])
        normal = np.array([1.0, 0.0, 0.0])
        result = _classify_internal(center, normal, bmin, bmax, bs, flow_dir=2, n_faces=10)
        assert result == "wall"


class TestClassifyBoundaries:
    """classify_boundaries 통합 테스트."""

    def test_no_polymesh_returns_empty(self, tmp_path: Path) -> None:
        """polyMesh 디렉터리가 없으면 빈 리스트를 반환한다."""
        result = classify_boundaries(tmp_path)
        assert result == []

    def test_empty_polymesh_returns_empty(self, tmp_path: Path) -> None:
        """polyMesh 파일이 파싱 불가한 경우 빈 리스트를 반환한다."""
        poly_dir = tmp_path / "constant" / "polyMesh"
        poly_dir.mkdir(parents=True)
        # 파일이 없으면 parse에서 예외 → 빈 반환
        result = classify_boundaries(tmp_path)
        assert result == []

    def test_with_valid_polymesh(self, tmp_path: Path) -> None:
        """유효한 polyMesh가 있으면 패치 목록을 반환한다."""
        _make_polymesh(tmp_path)
        result = classify_boundaries(tmp_path)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_result_has_name_and_type(self, tmp_path: Path) -> None:
        """반환 결과 각 항목에 name과 type 키가 있다."""
        _make_polymesh(tmp_path)
        result = classify_boundaries(tmp_path)
        for item in result:
            assert "name" in item
            assert "type" in item

    def test_inlet_patch_classified(self, tmp_path: Path) -> None:
        """이름이 inlet인 패치는 inlet으로 분류된다."""
        _make_polymesh(tmp_path)
        result = classify_boundaries(tmp_path)
        names_types = {r["name"]: r["type"] for r in result}
        assert names_types.get("inlet") == "inlet"

    def test_outlet_patch_classified(self, tmp_path: Path) -> None:
        """이름이 outlet인 패치는 outlet으로 분류된다."""
        _make_polymesh(tmp_path)
        result = classify_boundaries(tmp_path)
        names_types = {r["name"]: r["type"] for r in result}
        assert names_types.get("outlet") == "outlet"

    def test_wall_patch_classified(self, tmp_path: Path) -> None:
        """이름이 wall인 패치는 wall로 분류된다."""
        _make_polymesh(tmp_path)
        result = classify_boundaries(tmp_path)
        names_types = {r["name"]: r["type"] for r in result}
        assert names_types.get("wall") == "wall"

    def test_result_nfaces_field(self, tmp_path: Path) -> None:
        """결과 항목에 nFaces 필드가 있다."""
        _make_polymesh(tmp_path)
        result = classify_boundaries(tmp_path)
        for item in result:
            assert "nFaces" in item


# ===========================================================================
# parallel.py (write_decompose_par_dict) 테스트
# ===========================================================================

from core.utils.parallel import write_decompose_par_dict


class TestWriteDecomposeParDict:
    def test_file_created(self, tmp_path: Path) -> None:
        """decomposeParDict 파일이 생성된다."""
        path = write_decompose_par_dict(tmp_path, n_procs=4)
        assert path.is_file()

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """반환 경로가 system/decomposeParDict이다."""
        path = write_decompose_par_dict(tmp_path, n_procs=4)
        assert path == tmp_path / "system" / "decomposeParDict"

    def test_n_procs_in_content(self, tmp_path: Path) -> None:
        """지정한 프로세서 수가 파일에 포함된다."""
        write_decompose_par_dict(tmp_path, n_procs=8)
        content = (tmp_path / "system" / "decomposeParDict").read_text()
        assert "8" in content

    def test_method_in_content(self, tmp_path: Path) -> None:
        """지정한 분해 방법이 파일에 포함된다."""
        write_decompose_par_dict(tmp_path, n_procs=4, method="hierarchical")
        content = (tmp_path / "system" / "decomposeParDict").read_text()
        assert "hierarchical" in content

    def test_foamfile_header(self, tmp_path: Path) -> None:
        """FoamFile 헤더가 포함된다."""
        write_decompose_par_dict(tmp_path, n_procs=2)
        content = (tmp_path / "system" / "decomposeParDict").read_text()
        assert "FoamFile" in content

    def test_default_method_is_scotch(self, tmp_path: Path) -> None:
        """기본 분해 방법은 scotch이다."""
        write_decompose_par_dict(tmp_path, n_procs=2)
        content = (tmp_path / "system" / "decomposeParDict").read_text()
        assert "scotch" in content

    def test_none_n_procs_auto_detect(self, tmp_path: Path) -> None:
        """n_procs=None이면 자동 감지하여 1 이상의 값을 사용한다."""
        path = write_decompose_par_dict(tmp_path, n_procs=None)
        assert path.is_file()
        content = path.read_text()
        # numberOfSubdomains 값이 양수임을 확인 (최소 1)
        import re
        m = re.search(r"numberOfSubdomains\s+(\d+)", content)
        assert m is not None
        assert int(m.group(1)) >= 1

    def test_system_dir_created(self, tmp_path: Path) -> None:
        """system/ 디렉터리가 없어도 자동 생성된다."""
        write_decompose_par_dict(tmp_path / "newcase", n_procs=2)
        assert (tmp_path / "newcase" / "system").is_dir()


# ===========================================================================
# profiler.py 테스트
# ===========================================================================

from core.utils.profiler import PipelineProfiler, ProfilingResult, TimingRecord


class TestTimingRecord:
    def test_total_returns_elapsed(self) -> None:
        r = TimingRecord(name="test", elapsed=1.23)
        assert r.total == 1.23

    def test_pct_default_zero(self) -> None:
        r = TimingRecord(name="test", elapsed=1.0)
        assert r.pct == 0.0

    def test_children_default_empty(self) -> None:
        r = TimingRecord(name="test")
        assert r.children == []


class TestProfilingResult:
    def test_summary_no_data(self) -> None:
        """데이터 없을 때 summary가 문자열을 반환한다."""
        pr = ProfilingResult()
        s = pr.summary()
        assert isinstance(s, str)
        assert len(s) > 0

    def test_summary_with_stages(self) -> None:
        """스테이지가 있을 때 각 이름이 요약에 포함된다."""
        pr = ProfilingResult(
            stages=[TimingRecord("analyze", 1.0), TimingRecord("mesh", 2.5)],
            total_time=3.5,
        )
        s = pr.summary()
        assert "analyze" in s
        assert "mesh" in s

    def test_summary_contains_total(self) -> None:
        """summary에 Total 합계가 포함된다."""
        pr = ProfilingResult(
            stages=[TimingRecord("step", 1.0)],
            total_time=1.0,
        )
        s = pr.summary()
        assert "Total" in s or "1.00" in s


class TestPipelineProfiler:
    def test_stage_records_elapsed(self) -> None:
        """stage() 컨텍스트가 경과 시간을 기록한다."""
        profiler = PipelineProfiler()
        profiler.start()
        with profiler.stage("step1"):
            time.sleep(0.05)
        result = profiler.result()
        assert len(result.stages) == 1
        assert result.stages[0].name == "step1"
        assert result.stages[0].elapsed >= 0.04

    def test_multiple_stages(self) -> None:
        """여러 스테이지를 순서대로 기록한다."""
        profiler = PipelineProfiler()
        profiler.start()
        with profiler.stage("a"):
            pass
        with profiler.stage("b"):
            pass
        result = profiler.result()
        assert len(result.stages) == 2
        assert result.stages[0].name == "a"
        assert result.stages[1].name == "b"

    def test_total_time_positive_after_stages(self) -> None:
        """start() 후 result()의 total_time이 0 이상이다."""
        profiler = PipelineProfiler()
        profiler.start()
        with profiler.stage("x"):
            time.sleep(0.01)
        result = profiler.result()
        assert result.total_time >= 0.0

    def test_result_without_start(self) -> None:
        """start() 없이 result()를 호출해도 예외가 발생하지 않는다."""
        profiler = PipelineProfiler()
        result = profiler.result()
        assert isinstance(result, ProfilingResult)
        assert result.total_time == 0.0

    def test_stage_elapsed_accuracy(self) -> None:
        """stage 경과 시간이 실제 sleep 시간과 근사하게 일치한다."""
        profiler = PipelineProfiler()
        profiler.start()
        with profiler.stage("sleep"):
            time.sleep(0.1)
        result = profiler.result()
        assert result.stages[0].elapsed == pytest.approx(0.1, abs=0.05)

    def test_no_stages_empty_list(self) -> None:
        """스테이지 없이 result()를 호출하면 빈 stages 리스트를 반환한다."""
        profiler = PipelineProfiler()
        profiler.start()
        result = profiler.result()
        assert result.stages == []

    def test_start_resets_stages(self) -> None:
        """start()를 다시 호출하면 이전 스테이지가 초기화된다."""
        profiler = PipelineProfiler()
        profiler.start()
        with profiler.stage("old"):
            pass
        profiler.start()
        result = profiler.result()
        assert result.stages == []


# ===========================================================================
# vtk_exporter.py 테스트
# ===========================================================================

from core.utils.vtk_exporter import _write_vtu, export_vtk


class TestVtkExporter:
    def test_no_polymesh_returns_none(self, tmp_path: Path) -> None:
        """polyMesh 없으면 None을 반환한다."""
        result = export_vtk(tmp_path)
        assert result is None

    def test_with_valid_polymesh_returns_path(self, tmp_path: Path) -> None:
        """유효한 polyMesh가 있으면 .vtu 파일 경로를 반환한다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path)
        assert result is not None
        assert result.suffix == ".vtu"

    def test_vtu_file_created(self, tmp_path: Path) -> None:
        """.vtu 파일이 실제로 생성된다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path)
        assert result is not None
        assert result.is_file()

    def test_default_output_path(self, tmp_path: Path) -> None:
        """output_path=None이면 case_dir/mesh.vtu에 저장된다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path)
        assert result == tmp_path / "mesh.vtu"

    def test_custom_output_path(self, tmp_path: Path) -> None:
        """output_path를 지정하면 그 경로에 저장된다."""
        _make_polymesh(tmp_path)
        out = tmp_path / "out" / "custom.vtu"
        result = export_vtk(tmp_path, output_path=out)
        assert result == out
        assert out.is_file()

    def test_vtu_contains_vtk_xml(self, tmp_path: Path) -> None:
        """.vtu 파일이 VTKFile XML 태그를 포함한다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path)
        assert result is not None
        content = result.read_text()
        assert "VTKFile" in content
        assert "UnstructuredGrid" in content

    def test_vtu_contains_points(self, tmp_path: Path) -> None:
        """.vtu 파일에 <Points> 섹션이 있다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path)
        assert result is not None
        content = result.read_text()
        assert "<Points>" in content

    def test_vtu_contains_cells(self, tmp_path: Path) -> None:
        """.vtu 파일에 <Cells> 섹션이 있다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path)
        assert result is not None
        content = result.read_text()
        assert "<Cells>" in content

    def test_include_quality_false(self, tmp_path: Path) -> None:
        """include_quality=False이면 CellData가 없다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path, include_quality=False)
        assert result is not None
        content = result.read_text()
        assert "CellData" not in content

    def test_include_quality_true(self, tmp_path: Path) -> None:
        """include_quality=True이면 품질 필드가 포함된다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path, include_quality=True)
        assert result is not None
        content = result.read_text()
        # 품질 필드(NonOrthogonality, CellVolume)가 있거나 CellData 블록이 있어야 함
        assert "NonOrthogonality" in content or "CellData" in content

    def test_empty_polymesh_returns_none(self, tmp_path: Path) -> None:
        """polyMesh 디렉터리가 있지만 파일이 없으면 None을 반환한다."""
        poly_dir = tmp_path / "constant" / "polyMesh"
        poly_dir.mkdir(parents=True)
        result = export_vtk(tmp_path)
        assert result is None

    def test_piece_numbercells_correct(self, tmp_path: Path) -> None:
        """VTU Piece의 NumberOfCells가 1 이상이다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path)
        assert result is not None
        content = result.read_text()
        import re
        m = re.search(r'NumberOfCells="(\d+)"', content)
        assert m is not None
        assert int(m.group(1)) >= 1

    def test_vtu_uses_int32_indices_for_normal_mesh(self, tmp_path: Path) -> None:
        """일반 범위 인덱스에서는 Int32 타입을 유지한다."""
        _make_polymesh(tmp_path)
        result = export_vtk(tmp_path)
        assert result is not None
        content = result.read_text()
        assert 'type="Int32" Name="connectivity"' in content
        assert 'type="Int32" Name="offsets"' in content

    def test_vtu_upgrades_to_int64_for_large_indices(self, tmp_path: Path) -> None:
        """인덱스가 Int32 범위를 넘으면 Int64 타입으로 승격한다."""
        out = tmp_path / "large_index.vtu"
        points = np.array([[0.0, 0.0, 0.0]], dtype=np.float64)
        cell_verts = [[2**31]]
        _write_vtu(
            path=out,
            points=points,
            cell_verts=cell_verts,
            faces=[],
            owner=np.array([], dtype=np.int64),
            neighbour=np.array([], dtype=np.int64),
            n_cells=1,
            n_internal=0,
            include_quality=False,
        )
        content = out.read_text()
        assert 'type="Int64" Name="connectivity"' in content
        assert 'type="Int64" Name="offsets"' in content
