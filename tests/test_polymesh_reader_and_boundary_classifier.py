"""beta43 — core/utils/polymesh_reader + boundary_classifier dedicated 회귀.

이전까지 integration 경유로만 cover 되던 유틸의 단위 격리.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.polymesh_writer import write_generic_polymesh
from core.utils.boundary_classifier import classify_boundaries
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)


def _make_tet_polymesh(case_dir: Path) -> None:
    """최소 2-tet polyMesh (공유 face 1 → internal 1, boundary 6)."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, 1], [0, 0, -1],
    ], dtype=np.float64)
    tet1 = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    tet2 = [[0, 1, 2], [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    write_generic_polymesh(V, [tet1, tet2], case_dir)


# ---------------------------------------------------------------------------
# polymesh_reader
# ---------------------------------------------------------------------------


def test_parse_foam_points_roundtrip(tmp_path: Path) -> None:
    """write_generic_polymesh 로 쓴 points 를 parse_foam_points 로 읽어 정점 수 일치."""
    _make_tet_polymesh(tmp_path)
    pts = parse_foam_points(tmp_path / "constant" / "polyMesh" / "points")
    assert len(pts) == 5
    assert all(len(p) == 3 for p in pts)


def test_parse_foam_faces_roundtrip(tmp_path: Path) -> None:
    _make_tet_polymesh(tmp_path)
    faces = parse_foam_faces(tmp_path / "constant" / "polyMesh" / "faces")
    # 2 tet × 4 face - 1 shared = 7
    assert len(faces) == 7
    assert all(len(f) == 3 for f in faces)


def test_parse_foam_labels_roundtrip(tmp_path: Path) -> None:
    _make_tet_polymesh(tmp_path)
    owner = parse_foam_labels(tmp_path / "constant" / "polyMesh" / "owner")
    nbr = parse_foam_labels(tmp_path / "constant" / "polyMesh" / "neighbour")
    assert len(owner) == 7
    assert len(nbr) == 1  # internal face 1
    # owner values in {0, 1}
    assert all(o in (0, 1) for o in owner)
    assert nbr[0] in (0, 1)


def test_parse_foam_boundary_returns_patches(tmp_path: Path) -> None:
    _make_tet_polymesh(tmp_path)
    patches = parse_foam_boundary(tmp_path / "constant" / "polyMesh" / "boundary")
    assert len(patches) >= 1
    p = patches[0]
    assert "name" in p
    assert "nFaces" in p
    assert "startFace" in p
    assert p["nFaces"] == 6  # 2 tets × 4 - 1 internal - 1 shared → 6 boundary


def test_parse_foam_points_handles_comments(tmp_path: Path) -> None:
    """FoamFile 주석이 포함된 파일도 정상 파싱."""
    path = tmp_path / "points"
    path.write_text(
        "/* block comment */\n"
        "// line comment\n"
        "FoamFile\n{\n    class vectorField;\n}\n"
        "2\n(\n(0 0 0) (1 2 3)\n)\n"
    )
    pts = parse_foam_points(path)
    assert len(pts) == 2
    assert pts[0] == [0.0, 0.0, 0.0]
    assert pts[1] == [1.0, 2.0, 3.0]


def test_parse_foam_labels_empty_list(tmp_path: Path) -> None:
    """빈 라벨 리스트 파싱."""
    path = tmp_path / "empty_labels"
    path.write_text(
        "FoamFile\n{\n    class labelList;\n}\n"
        "0\n(\n)\n"
    )
    labels = parse_foam_labels(path)
    assert labels == []


def test_parse_foam_boundary_multiple_patches(tmp_path: Path) -> None:
    """boundary 파일에 여러 패치 블록."""
    path = tmp_path / "boundary"
    path.write_text(
        "FoamFile\n{\n    class polyBoundaryMesh;\n}\n"
        "2\n(\n"
        "    inlet\n    {\n        type patch;\n        nFaces 10;\n        startFace 100;\n    }\n"
        "    walls\n    {\n        type wall;\n        nFaces 20;\n        startFace 110;\n    }\n"
        ")\n"
    )
    patches = parse_foam_boundary(path)
    assert len(patches) == 2
    names = [p["name"] for p in patches]
    assert "inlet" in names
    assert "walls" in names


# ---------------------------------------------------------------------------
# boundary_classifier
# ---------------------------------------------------------------------------


def test_classify_boundaries_no_polymesh_returns_empty(tmp_path: Path) -> None:
    """polyMesh 디렉터리 없음 → 빈 리스트."""
    result = classify_boundaries(tmp_path, flow_type="external")
    assert result == []


def test_classify_boundaries_on_simple_polymesh(tmp_path: Path) -> None:
    """최소 polyMesh 에서 단일 defaultWall 패치 분류."""
    _make_tet_polymesh(tmp_path)
    result = classify_boundaries(tmp_path, flow_type="external", flow_direction=0)
    assert len(result) >= 1
    p = result[0]
    assert "name" in p
    assert "type" in p
    assert "nFaces" in p
    # type 은 최소한 string
    assert isinstance(p["type"], str)


def test_classify_boundaries_patch_count_matches_boundary_file(
    tmp_path: Path,
) -> None:
    """boundary 파일의 패치 개수와 결과 길이 일치."""
    _make_tet_polymesh(tmp_path)
    boundary = parse_foam_boundary(tmp_path / "constant" / "polyMesh" / "boundary")
    result = classify_boundaries(tmp_path)
    assert len(result) == len(boundary)


def test_classify_boundaries_corrupt_polymesh_returns_empty(
    tmp_path: Path,
) -> None:
    """파싱 실패 시 빈 리스트."""
    poly_dir = tmp_path / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    (poly_dir / "points").write_text("garbage\n")
    (poly_dir / "faces").write_text("garbage\n")
    (poly_dir / "boundary").write_text("garbage\n")
    # 읽기 성공 후 len==0 → 빈 리스트, 혹은 파싱 예외 → 빈 리스트
    result = classify_boundaries(tmp_path)
    assert result == []


def test_classify_external_flow_type_accepted(tmp_path: Path) -> None:
    """flow_type='external' 수용."""
    _make_tet_polymesh(tmp_path)
    result = classify_boundaries(tmp_path, flow_type="external")
    assert isinstance(result, list)


def test_classify_internal_flow_type_accepted(tmp_path: Path) -> None:
    """flow_type='internal' 수용."""
    _make_tet_polymesh(tmp_path)
    result = classify_boundaries(tmp_path, flow_type="internal")
    assert isinstance(result, list)


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_classify_boundaries_flow_direction_axes(tmp_path: Path, axis: int) -> None:
    """flow_direction 각 축 (x/y/z) 수용."""
    _make_tet_polymesh(tmp_path)
    result = classify_boundaries(tmp_path, flow_direction=axis)
    assert isinstance(result, list)
