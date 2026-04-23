"""beta46 — OpenFOAMWriter dedicated 회귀.

core/generator/openfoam_writer.OpenFOAMWriter 의 각 메서드 단위 격리.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.generator.openfoam_writer import OpenFOAMWriter


# ---------------------------------------------------------------------------
# ensure_case_structure
# ---------------------------------------------------------------------------


def test_ensure_case_structure_creates_all_dirs(tmp_path: Path) -> None:
    """constant/polyMesh + constant/triSurface + system 생성."""
    w = OpenFOAMWriter()
    w.ensure_case_structure(tmp_path)
    assert (tmp_path / "constant" / "polyMesh").is_dir()
    assert (tmp_path / "constant" / "triSurface").is_dir()
    assert (tmp_path / "system").is_dir()


def test_ensure_case_structure_idempotent(tmp_path: Path) -> None:
    """두 번 호출해도 에러 없음."""
    w = OpenFOAMWriter()
    w.ensure_case_structure(tmp_path)
    w.ensure_case_structure(tmp_path)  # 재호출
    assert (tmp_path / "system").is_dir()


# ---------------------------------------------------------------------------
# write_control_dict
# ---------------------------------------------------------------------------


def test_write_control_dict_creates_file_with_application(tmp_path: Path) -> None:
    w = OpenFOAMWriter()
    w.ensure_case_structure(tmp_path)
    w.write_control_dict(tmp_path, application="pimpleFoam")
    path = tmp_path / "system" / "controlDict"
    assert path.exists()
    content = path.read_text()
    assert "application" in content
    assert "pimpleFoam" in content


def test_write_control_dict_default_application_is_simpleFoam(tmp_path: Path) -> None:
    w = OpenFOAMWriter()
    w.ensure_case_structure(tmp_path)
    w.write_control_dict(tmp_path)
    content = (tmp_path / "system" / "controlDict").read_text()
    assert "simpleFoam" in content


# ---------------------------------------------------------------------------
# write_fv_schemes + write_fv_solution
# ---------------------------------------------------------------------------


def test_write_fv_schemes_contains_required_blocks(tmp_path: Path) -> None:
    w = OpenFOAMWriter()
    w.ensure_case_structure(tmp_path)
    w.write_fv_schemes(tmp_path)
    content = (tmp_path / "system" / "fvSchemes").read_text()
    for block in ("ddtSchemes", "gradSchemes", "divSchemes", "laplacianSchemes"):
        assert block in content


def test_write_fv_solution_contains_solvers(tmp_path: Path) -> None:
    w = OpenFOAMWriter()
    w.ensure_case_structure(tmp_path)
    w.write_fv_solution(tmp_path)
    content = (tmp_path / "system" / "fvSolution").read_text()
    # solvers + SIMPLE 또는 PIMPLE 알고리즘 블록 예상
    assert "solvers" in content


# ---------------------------------------------------------------------------
# write_foam_dict (generic serialization)
# ---------------------------------------------------------------------------


def test_write_foam_dict_simple_dict(tmp_path: Path) -> None:
    """평탄한 dict 를 OpenFOAM 형식으로 직렬화."""
    w = OpenFOAMWriter()
    path = tmp_path / "myDict"
    w.write_foam_dict(path, {"key1": "value1", "key2": 42})
    content = path.read_text()
    assert "key1" in content
    assert "value1" in content
    assert "key2" in content
    assert "42" in content


def test_write_foam_dict_nested_dict(tmp_path: Path) -> None:
    """중첩 dict → { ... } 블록으로 직렬화."""
    w = OpenFOAMWriter()
    path = tmp_path / "nestedDict"
    w.write_foam_dict(path, {"outer": {"inner": "val"}})
    content = path.read_text()
    assert "outer" in content
    assert "{" in content
    assert "inner" in content


def test_write_foam_dict_list_of_primitives(tmp_path: Path) -> None:
    """리스트는 (v1 v2 v3); 형식."""
    w = OpenFOAMWriter()
    path = tmp_path / "listDict"
    w.write_foam_dict(path, {"items": [1, 2, 3]})
    content = path.read_text()
    assert "items" in content
    assert "(1 2 3)" in content


def test_write_foam_dict_list_of_dicts(tmp_path: Path) -> None:
    """dict 리스트 → 병렬 { } 블록."""
    w = OpenFOAMWriter()
    path = tmp_path / "refineDict"
    data = {
        "refinement": [
            {"name": "surf1", "level": 2},
            {"name": "surf2", "level": 3},
        ],
    }
    w.write_foam_dict(path, data)
    content = path.read_text()
    assert "refinement" in content
    assert "surf1" in content
    assert "surf2" in content


# ---------------------------------------------------------------------------
# _format_foam_value
# ---------------------------------------------------------------------------


def test_format_foam_value_none_is_literal_none() -> None:
    assert OpenFOAMWriter._format_foam_value(None) == "none"


def test_format_foam_value_bool_is_lowercase() -> None:
    assert OpenFOAMWriter._format_foam_value(True) == "true"
    assert OpenFOAMWriter._format_foam_value(False) == "false"


def test_format_foam_value_number_is_str() -> None:
    assert OpenFOAMWriter._format_foam_value(42) == "42"
    assert OpenFOAMWriter._format_foam_value(3.14) == "3.14"


def test_format_foam_value_list_is_parenthesized() -> None:
    assert OpenFOAMWriter._format_foam_value([1, 2, 3]) == "(1 2 3)"


def test_format_foam_value_string_with_space_gets_quoted() -> None:
    out = OpenFOAMWriter._format_foam_value("hello world")
    assert out.startswith('"')
    assert out.endswith('"')


def test_format_foam_value_simple_string_unquoted() -> None:
    assert OpenFOAMWriter._format_foam_value("simpleFoam") == "simpleFoam"


def test_format_foam_value_path_like_gets_quoted() -> None:
    """파일 경로 / 확장자 → 쿼팅."""
    out = OpenFOAMWriter._format_foam_value("constant/polyMesh")
    assert out.startswith('"')
