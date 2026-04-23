"""beta37 — write_generic_polymesh dedicated 회귀 테스트.

beta12 에서 tet/hex/poly writer 를 통합한 공용 writer. PolyMeshWriter /
_write_polymesh_hex / _write_polymesh_poly 간접 테스트에서는 cover 되지만
dedicated 회귀로 edge case 보호.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from core.generator.polymesh_writer import write_generic_polymesh


def test_single_tet_boundary_only(tmp_path: Path) -> None:
    """단일 tet — 4 face 모두 boundary, 0 internal."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
    ], dtype=np.float64)
    cell_faces = [[
        [0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3],
    ]]
    stats = write_generic_polymesh(V, cell_faces, tmp_path)
    assert stats["num_cells"] == 1
    assert stats["num_faces"] == 4
    assert stats["num_internal_faces"] == 0
    assert stats["num_points"] == 4


def test_two_tets_share_one_face(tmp_path: Path) -> None:
    """공유 face 가 정확히 internal 1 개로 합쳐짐."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, 1], [0, 0, -1],
    ], dtype=np.float64)
    tet1 = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    tet2 = [[0, 1, 2], [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    stats = write_generic_polymesh(V, [tet1, tet2], tmp_path)
    assert stats["num_cells"] == 2
    assert stats["num_internal_faces"] == 1
    # 총 face = 2*4 - 1 (shared) = 7
    assert stats["num_faces"] == 7


def test_owner_less_than_neighbour_for_internal_faces(tmp_path: Path) -> None:
    """모든 internal face 에 대해 owner < neighbour."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, -1],
    ], dtype=np.float64)
    tet1 = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    tet2 = [[0, 1, 2], [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    stats = write_generic_polymesh(V, [tet1, tet2], tmp_path)

    poly_dir = tmp_path / "constant" / "polyMesh"
    from core.utils.polymesh_reader import parse_foam_labels
    owner = parse_foam_labels(poly_dir / "owner")
    nbr = parse_foam_labels(poly_dir / "neighbour")
    n_internal = stats["num_internal_faces"]
    for i in range(n_internal):
        assert owner[i] < nbr[i], f"face {i}: owner={owner[i]}, nbr={nbr[i]}"


def test_owner_note_contains_mesh_stats(tmp_path: Path) -> None:
    """owner 파일의 note 에 nPoints/nCells/nFaces/nInternalFaces 포함."""
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    cell_faces = [[[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]]
    write_generic_polymesh(V, cell_faces, tmp_path)

    owner_text = (tmp_path / "constant" / "polyMesh" / "owner").read_text()
    assert re.search(r"nPoints:\s*4", owner_text)
    assert re.search(r"nCells:\s*1", owner_text)
    assert re.search(r"nFaces:\s*4", owner_text)
    assert re.search(r"nInternalFaces:\s*0", owner_text)


def test_all_five_polymesh_files_written(tmp_path: Path) -> None:
    """points/faces/owner/neighbour/boundary 5 파일 모두 생성."""
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    cell_faces = [[[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]]
    write_generic_polymesh(V, cell_faces, tmp_path)

    poly_dir = tmp_path / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (poly_dir / name).exists(), f"{name} 파일 누락"


def test_boundary_patch_name_configurable(tmp_path: Path) -> None:
    """patch_name / patch_type 인자로 boundary 파일 설정."""
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    cell_faces = [[[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]]
    write_generic_polymesh(
        V, cell_faces, tmp_path,
        patch_name="custom_wall", patch_type="patch",
    )
    boundary_text = (tmp_path / "constant" / "polyMesh" / "boundary").read_text()
    assert "custom_wall" in boundary_text
    assert "patch" in boundary_text


def test_system_files_written(tmp_path: Path) -> None:
    """write_generic_polymesh 가 최소 system/ (controlDict / fvSchemes / fvSolution)
    생성."""
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    cell_faces = [[[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]]
    write_generic_polymesh(V, cell_faces, tmp_path)
    system_dir = tmp_path / "system"
    assert (system_dir / "controlDict").exists()


def test_internal_faces_sorted_by_owner_then_neighbour(tmp_path: Path) -> None:
    """여러 cell 공유 face 정렬 — (owner, neighbour) 오름차순."""
    # 4-tet fan: tet 0/1/2/3 이 공유 vertex (0,0,0) 주위
    V = np.array([
        [0, 0, 0],    # center
        [1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0],  # 4 outer
        [0, 0, 1],    # apex
    ], dtype=np.float64)
    # tets: (center, outer[i], outer[i+1], apex)
    tets = [
        [[0, 2, 1], [0, 1, 5], [1, 2, 5], [0, 5, 2]],  # tet 0: 0-1-2-5
        [[0, 3, 2], [0, 2, 5], [2, 3, 5], [0, 5, 3]],  # tet 1: 0-2-3-5
    ]
    stats = write_generic_polymesh(V, tets, tmp_path)

    from core.utils.polymesh_reader import parse_foam_labels
    poly_dir = tmp_path / "constant" / "polyMesh"
    owners = parse_foam_labels(poly_dir / "owner")
    nbrs = parse_foam_labels(poly_dir / "neighbour")
    n_internal = stats["num_internal_faces"]

    internal_pairs = list(zip(owners[:n_internal], nbrs))
    sorted_pairs = sorted(internal_pairs)
    assert internal_pairs == sorted_pairs, (
        f"internal faces not sorted: {internal_pairs}"
    )


def test_empty_cell_faces_produces_empty_polymesh(tmp_path: Path) -> None:
    """빈 cell_faces 입력 → num_cells=0, 5 파일 존재 (빈 entries)."""
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    stats = write_generic_polymesh(V, [], tmp_path)
    assert stats["num_cells"] == 0
    assert stats["num_faces"] == 0


def test_short_face_length_lt3_ignored(tmp_path: Path) -> None:
    """vertex 수 < 3 인 face 는 무시."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
    ], dtype=np.float64)
    # 첫 face 는 2 verts (invalid) → skip
    cell_faces = [[
        [0, 1],                 # invalid, skipped
        [0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3],
    ]]
    stats = write_generic_polymesh(V, cell_faces, tmp_path)
    assert stats["num_faces"] == 4  # 유효 4 개만 기록
