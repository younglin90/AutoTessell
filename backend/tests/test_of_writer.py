"""
Tests for the pure-Python OpenFOAM polyMesh writer (mesh/of_writer.py).
"""
import numpy as np
import pytest
from pathlib import Path

from mesh.of_writer import write_polymesh, _build_face_tables


# ---------------------------------------------------------------------------
# Minimal tet fixtures
# ---------------------------------------------------------------------------

def _single_tet():
    """
    A single tetrahedron with 4 vertices and 1 cell.
    All 4 faces are boundary faces (no neighbours).
    """
    vertices = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int32)
    return vertices, tets


def _two_tets_sharing_face():
    """
    Two tetrahedra sharing one face.
    Tet 0: vertices 0,1,2,3
    Tet 1: vertices 0,1,2,4  (shares face 0-1-2)
    → 1 internal face, 6 boundary faces.
    """
    vertices = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, -1.0],
    ], dtype=np.float64)
    tets = np.array([
        [0, 1, 2, 3],
        [0, 1, 2, 4],
    ], dtype=np.int32)
    return vertices, tets


# ---------------------------------------------------------------------------
# _build_face_tables
# ---------------------------------------------------------------------------

class TestBuildFaceTables:
    def test_single_tet_has_no_internal_faces(self):
        _, tets = _single_tet()
        faces, owner, neighbour, n_internal = _build_face_tables(tets)
        assert n_internal == 0
        assert len(neighbour) == 0

    def test_single_tet_has_four_boundary_faces(self):
        _, tets = _single_tet()
        faces, owner, neighbour, n_internal = _build_face_tables(tets)
        assert len(faces) == 4

    def test_two_tets_one_internal_face(self):
        _, tets = _two_tets_sharing_face()
        faces, owner, neighbour, n_internal = _build_face_tables(tets)
        assert n_internal == 1

    def test_two_tets_total_faces(self):
        _, tets = _two_tets_sharing_face()
        faces, owner, neighbour, n_internal = _build_face_tables(tets)
        # 2 tets × 4 faces - 2 shared = 6 unique faces total
        assert len(faces) == 7  # 1 internal + 6 boundary

    def test_internal_faces_before_boundary(self):
        _, tets = _two_tets_sharing_face()
        faces, owner, neighbour, n_internal = _build_face_tables(tets)
        # First n_internal entries in owner correspond to internal faces
        assert len(owner) == len(faces)
        assert len(neighbour) == n_internal

    def test_owner_less_than_neighbour_for_internal_faces(self):
        _, tets = _two_tets_sharing_face()
        faces, owner, neighbour, n_internal = _build_face_tables(tets)
        for i in range(n_internal):
            assert owner[i] < neighbour[i], (
                f"internal face {i}: owner={owner[i]} >= neighbour={neighbour[i]}"
            )

    def test_all_owner_indices_valid(self):
        _, tets = _two_tets_sharing_face()
        faces, owner, neighbour, n_internal = _build_face_tables(tets)
        n_cells = len(tets)
        for i, o in enumerate(owner):
            assert 0 <= o < n_cells, f"owner[{i}]={o} out of range"

    def test_all_face_vertices_reference_valid_points(self):
        vertices, tets = _two_tets_sharing_face()
        n_verts = len(vertices)
        faces, _, _, _ = _build_face_tables(tets)
        for face in faces:
            for v in face:
                assert 0 <= v < n_verts, f"vertex {v} out of range"


# ---------------------------------------------------------------------------
# write_polymesh — file output
# ---------------------------------------------------------------------------

class TestWritePolyMesh:
    def test_all_files_created(self, tmp_path: Path):
        v, t = _single_tet()
        write_polymesh(v, t, tmp_path)
        poly_dir = tmp_path / "constant" / "polyMesh"
        for name in ("points", "faces", "owner", "neighbour", "boundary"):
            assert (poly_dir / name).exists(), f"Missing: {name}"

    def test_points_count_correct(self, tmp_path: Path):
        v, t = _single_tet()
        stats = write_polymesh(v, t, tmp_path)
        assert stats["num_points"] == 4

    def test_cells_count_correct(self, tmp_path: Path):
        v, t = _single_tet()
        stats = write_polymesh(v, t, tmp_path)
        assert stats["num_cells"] == 1

    def test_no_internal_faces_for_single_tet(self, tmp_path: Path):
        v, t = _single_tet()
        stats = write_polymesh(v, t, tmp_path)
        assert stats["num_internal_faces"] == 0
        assert stats["num_faces"] == 4

    def test_two_tets_stats(self, tmp_path: Path):
        v, t = _two_tets_sharing_face()
        stats = write_polymesh(v, t, tmp_path)
        assert stats["num_cells"] == 2
        assert stats["num_internal_faces"] == 1
        assert stats["num_faces"] == 7

    def test_points_file_has_foam_header(self, tmp_path: Path):
        v, t = _single_tet()
        write_polymesh(v, t, tmp_path)
        content = (tmp_path / "constant" / "polyMesh" / "points").read_text()
        assert "FoamFile" in content
        assert "vectorField" in content

    def test_boundary_file_contains_walls_patch(self, tmp_path: Path):
        v, t = _single_tet()
        write_polymesh(v, t, tmp_path)
        content = (tmp_path / "constant" / "polyMesh" / "boundary").read_text()
        assert "walls" in content
        assert "wall" in content
        assert "nFaces          4" in content
        assert "startFace       0" in content

    def test_neighbour_file_empty_for_single_tet(self, tmp_path: Path):
        v, t = _single_tet()
        write_polymesh(v, t, tmp_path)
        content = (tmp_path / "constant" / "polyMesh" / "neighbour").read_text()
        # 0 entries
        assert "\n0\n" in content

    def test_points_coordinates_preserved(self, tmp_path: Path):
        v, t = _single_tet()
        write_polymesh(v, t, tmp_path)
        content = (tmp_path / "constant" / "polyMesh" / "points").read_text()
        assert "(0 0 0)" in content
        assert "(1 0 0)" in content

    def test_large_mesh_stats(self, tmp_path: Path):
        """Smoke test with 100 tets to verify scalability."""
        rng = np.random.default_rng(42)
        # Generate a simple grid-like mesh
        n = 5
        verts = []
        for x in range(n + 1):
            for y in range(n + 1):
                for z in range(n + 1):
                    verts.append([x, y, z])
        vertices = np.array(verts, dtype=np.float64)
        # Make some tets (just use first 50 sequential groups of 4 vertices)
        tet_indices = np.array([[i, i+1, i+2, i+3] for i in range(50) if i+3 < len(vertices)], dtype=np.int32)
        stats = write_polymesh(vertices, tet_indices, tmp_path)
        assert stats["num_cells"] == len(tet_indices)
        assert stats["num_points"] == len(vertices)
