"""FoamCaseWriter 단위 테스트.

foamlib 설치 여부와 관계없이 케이스 파일이 정상 생성되는지 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from core.generator.case_writer import FoamCaseWriter


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_patches(names_types: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{"name": n, "type": t} for n, t in names_types]


# ---------------------------------------------------------------------------
# 테스트 1: 기본 케이스 디렉터리 구조 생성
# ---------------------------------------------------------------------------

def test_case_directory_structure(tmp_path: Path) -> None:
    """write_case 호출 후 system/, constant/, 0/ 하위 필수 파일이 모두 생성된다."""
    case_dir = tmp_path / "case"
    mesh_dir = case_dir / "constant" / "polyMesh"
    mesh_dir.mkdir(parents=True)

    writer = FoamCaseWriter()
    written = writer.write_case(
        mesh_dir=mesh_dir,
        case_dir=case_dir,
        solver="simpleFoam",
    )

    # system/ 필수 파일
    assert (case_dir / "system" / "controlDict").exists(), "controlDict missing"
    assert (case_dir / "system" / "fvSchemes").exists(), "fvSchemes missing"
    assert (case_dir / "system" / "fvSolution").exists(), "fvSolution missing"
    assert (case_dir / "system" / "decomposeParDict").exists(), "decomposeParDict missing"

    # constant/ 필수 파일
    assert (case_dir / "constant" / "transportProperties").exists()
    assert (case_dir / "constant" / "turbulenceProperties").exists()

    # 0/ 필수 파일
    assert (case_dir / "0" / "p").exists(), "0/p missing"
    assert (case_dir / "0" / "U").exists(), "0/U missing"
    assert (case_dir / "0" / "k").exists(), "0/k missing"
    assert (case_dir / "0" / "nut").exists(), "0/nut missing"

    # 반환된 파일 목록이 비어있지 않아야 함
    assert len(written) >= 8


# ---------------------------------------------------------------------------
# 테스트 2: simpleFoam vs pimpleFoam 전환
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("solver,expected_keyword", [
    ("simpleFoam", "SIMPLE"),
    ("pimpleFoam", "PIMPLE"),
])
def test_solver_switching(tmp_path: Path, solver: str, expected_keyword: str) -> None:
    """solver 파라미터에 따라 controlDict, fvSolution 내용이 달라진다."""
    case_dir = tmp_path / "case"
    mesh_dir = case_dir / "constant" / "polyMesh"
    mesh_dir.mkdir(parents=True)

    writer = FoamCaseWriter()
    writer.write_case(mesh_dir=mesh_dir, case_dir=case_dir, solver=solver)

    control_dict = (case_dir / "system" / "controlDict").read_text()
    assert solver in control_dict, f"solver '{solver}' not found in controlDict"

    fv_solution = (case_dir / "system" / "fvSolution").read_text()
    assert expected_keyword in fv_solution, (
        f"keyword '{expected_keyword}' not found in fvSolution for solver {solver}"
    )

    # pimpleFoam은 비정상 endTime (0.1), simpleFoam은 1000
    if solver == "pimpleFoam":
        assert "0.1" in control_dict
    else:
        assert "1000" in control_dict


# ---------------------------------------------------------------------------
# 테스트 3: 벽면/입구/출구 BC 자동 분류
# ---------------------------------------------------------------------------

def test_boundary_condition_classification(tmp_path: Path) -> None:
    """inlet/outlet/wall 패치에 맞는 BC 타입이 0/ 파일에 기록된다."""
    patches = _make_patches([
        ("inlet", "inlet"),
        ("outlet", "outlet"),
        ("walls", "wall"),
    ])
    case_dir = tmp_path / "case"
    mesh_dir = case_dir / "constant" / "polyMesh"
    mesh_dir.mkdir(parents=True)

    writer = FoamCaseWriter(flow_velocity=2.0)
    writer.write_case(mesh_dir=mesh_dir, case_dir=case_dir, patches=patches)

    # 0/U 검증
    u_content = (case_dir / "0" / "U").read_text()
    assert "fixedValue" in u_content, "inlet U should be fixedValue"
    assert "noSlip" in u_content, "wall U should be noSlip"
    assert "zeroGradient" in u_content, "outlet U should be zeroGradient"

    # 0/p 검증
    p_content = (case_dir / "0" / "p").read_text()
    assert "fixedValue" in p_content, "outlet p should be fixedValue"

    # 0/nut 검증
    nut_content = (case_dir / "0" / "nut").read_text()
    assert "nutkWallFunction" in nut_content, "wall nut should be nutkWallFunction"


# ---------------------------------------------------------------------------
# 테스트 4: foamlib 미설치 fallback 동작
# ---------------------------------------------------------------------------

def test_foamlib_fallback(tmp_path: Path) -> None:
    """foamlib가 없는 환경에서도 수동 파일 쓰기로 케이스가 생성된다."""
    case_dir = tmp_path / "case"
    mesh_dir = case_dir / "constant" / "polyMesh"
    mesh_dir.mkdir(parents=True)

    # foamlib를 사용 불가로 패치
    with patch("core.generator.case_writer._FOAMLIB_AVAILABLE", False), \
         patch("core.generator.case_writer._FoamFile", None):
        writer = FoamCaseWriter()
        written = writer.write_case(
            mesh_dir=mesh_dir,
            case_dir=case_dir,
            solver="simpleFoam",
        )

    # 파일이 정상 생성됐는지 확인
    assert (case_dir / "system" / "controlDict").exists()
    assert (case_dir / "system" / "fvSchemes").exists()
    assert (case_dir / "system" / "fvSolution").exists()
    assert (case_dir / "constant" / "transportProperties").exists()
    assert (case_dir / "0" / "p").exists()
    assert (case_dir / "0" / "U").exists()
    assert len(written) >= 8

    # FoamFile 헤더 포함 여부 (수동 쓰기)
    ctrl = (case_dir / "system" / "controlDict").read_text()
    assert "FoamFile" in ctrl
    assert "simpleFoam" in ctrl


# ---------------------------------------------------------------------------
# 테스트 5: kEpsilon vs kOmegaSST 난류 모델 전환
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("turb_model,expected_field", [
    ("kEpsilon", "epsilon"),
    ("kOmegaSST", "omega"),
])
def test_turbulence_model_switching(
    tmp_path: Path, turb_model: str, expected_field: str
) -> None:
    """turbulence_model에 따라 0/ 디렉터리에 올바른 secondary field 파일이 생성된다."""
    case_dir = tmp_path / "case"
    mesh_dir = case_dir / "constant" / "polyMesh"
    mesh_dir.mkdir(parents=True)

    writer = FoamCaseWriter(turbulence_model=turb_model)
    writer.write_case(mesh_dir=mesh_dir, case_dir=case_dir)

    # 해당 난류 field 파일이 존재해야 함
    assert (case_dir / "0" / expected_field).exists(), (
        f"0/{expected_field} not found for turbulence model {turb_model}"
    )

    # turbulenceProperties에 모델 이름이 기록돼야 함
    turb_props = (case_dir / "constant" / "turbulenceProperties").read_text()
    assert turb_model in turb_props, f"{turb_model} not in turbulenceProperties"


def test_generated_scalar_bc_values_end_with_semicolon(tmp_path: Path) -> None:
    """OpenFOAM field entries with explicit values must remain parseable."""
    case_dir = tmp_path / "case"
    mesh_dir = case_dir / "constant" / "polyMesh"
    mesh_dir.mkdir(parents=True)

    writer = FoamCaseWriter(turbulence_model="kEpsilon")
    writer.write_case(mesh_dir=mesh_dir, case_dir=case_dir)

    epsilon_content = (case_dir / "0" / "epsilon").read_text()
    assert "value   uniform" in epsilon_content
    assert "value   uniform 0.0022964;" in epsilon_content
