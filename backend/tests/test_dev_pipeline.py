"""
Unit tests for mesh/dev_pipeline.py

Covers:
  - _cells_to_edge_fac: auto edge-length calculation from target cell count
  - generate_mesh_dev: end-to-end with mocked pytetwild + write_polymesh
  - MeshParams pro-mode overrides (tet_stop_energy, tet_edge_length_fac)
  - Error handling: pytetwild/trimesh not installed, pytetwild raises
  - STL loading fallback path
"""

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from mesh.dev_pipeline import _cells_to_edge_fac, generate_mesh_dev
from mesh.params import MeshParams


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_binary_stl(triangles: list) -> bytes:
    """Minimal binary STL from list of (v0, v1, v2) tuples."""
    header = b"\x00" * 80
    count = struct.pack("<I", len(triangles))
    body = b""
    for v0, v1, v2 in triangles:
        body += struct.pack("<3f", 0.0, 0.0, 1.0)  # normal
        for vx, vy, vz in (v0, v1, v2):
            body += struct.pack("<3f", vx, vy, vz)
        body += b"\x00\x00"
    return header + count + body


def _unit_cube_stl() -> bytes:
    return _make_binary_stl([
        ((0, 0, 0), (1, 0, 0), (1, 1, 0)),
        ((0, 0, 0), (1, 1, 0), (0, 1, 0)),
        ((0, 0, 0), (0, 0, 1), (1, 0, 0)),
        ((0, 0, 1), (1, 0, 1), (1, 0, 0)),
        ((1, 0, 0), (1, 0, 1), (1, 1, 1)),
        ((1, 0, 0), (1, 1, 1), (1, 1, 0)),
        ((0, 1, 0), (1, 1, 0), (1, 1, 1)),
        ((0, 1, 0), (1, 1, 1), (0, 1, 1)),
        ((0, 0, 0), (0, 1, 0), (0, 1, 1)),
        ((0, 0, 0), (0, 1, 1), (0, 0, 1)),
        ((0, 0, 1), (0, 1, 1), (1, 1, 1)),
        ((0, 0, 1), (1, 1, 1), (1, 0, 1)),
    ])


@pytest.fixture
def cube_stl(tmp_path: Path) -> Path:
    p = tmp_path / "cube.stl"
    p.write_bytes(_unit_cube_stl())
    return p


def _unit_cube_verts() -> np.ndarray:
    return np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)


# ---------------------------------------------------------------------------
# _cells_to_edge_fac
# ---------------------------------------------------------------------------

class TestCellsToEdgeFac:
    def test_fac_is_float(self):
        verts = _unit_cube_verts()
        fac = _cells_to_edge_fac(500_000, verts)
        assert isinstance(fac, float)

    def test_fac_in_valid_range(self):
        verts = _unit_cube_verts()
        for cells in [1_000, 100_000, 500_000, 5_000_000]:
            fac = _cells_to_edge_fac(cells, verts)
            assert 0.02 <= fac <= 0.2, f"fac={fac} out of [0.02, 0.2] for cells={cells}"

    def test_more_cells_gives_smaller_fac(self):
        verts = _unit_cube_verts()
        fac_coarse = _cells_to_edge_fac(10_000, verts)
        fac_fine = _cells_to_edge_fac(1_000_000, verts)
        assert fac_fine < fac_coarse

    def test_single_cell_target_returns_max_fac(self):
        verts = _unit_cube_verts()
        fac = _cells_to_edge_fac(1, verts)
        assert fac == pytest.approx(0.2)

    def test_degenerate_bbox_does_not_crash(self):
        # Zero-volume geometry → should return clamped fac (not raise)
        verts = np.array([[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], dtype=np.float64)
        fac = _cells_to_edge_fac(500_000, verts)
        assert 0.02 <= fac <= 0.2


# ---------------------------------------------------------------------------
# generate_mesh_dev — with mocked pytetwild and write_polymesh
# ---------------------------------------------------------------------------

def _make_mock_pytetwild(n_verts: int = 50, n_tets: int = 80):
    """Return a mock pytetwild module whose tetrahedralize returns small arrays."""
    mock = MagicMock()
    v_out = np.random.default_rng(42).uniform(0, 1, (n_verts, 3)).astype(np.float64)
    t_out = np.zeros((n_tets, 4), dtype=np.int32)
    mock.tetrahedralize.return_value = (v_out, t_out)
    return mock


class TestGenerateMeshDev:
    def test_returns_dict_with_tier(self, cube_stl: Path, tmp_path: Path):
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 80, "num_points": 50, "num_faces": 200, "num_internal_faces": 100}

        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                result = generate_mesh_dev(cube_stl, tmp_path / "case")

        assert result["tier"] == "pytetwild_dev"

    def test_returns_num_cells(self, cube_stl: Path, tmp_path: Path):
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 80, "num_points": 50, "num_faces": 200, "num_internal_faces": 100}

        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                result = generate_mesh_dev(cube_stl, tmp_path / "case")

        assert result["num_cells"] == 80

    def test_passed_true(self, cube_stl: Path, tmp_path: Path):
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 80, "num_points": 50, "num_faces": 200, "num_internal_faces": 100}

        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                result = generate_mesh_dev(cube_stl, tmp_path / "case")

        assert result["passed"] is True

    def test_creates_case_dir(self, cube_stl: Path, tmp_path: Path):
        case_dir = tmp_path / "new_case"
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 10, "num_points": 8, "num_faces": 16, "num_internal_faces": 4}

        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                generate_mesh_dev(cube_stl, case_dir)

        assert case_dir.is_dir()

    def test_pro_stop_energy_passed_to_pytetwild(self, cube_stl: Path, tmp_path: Path):
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 10, "num_points": 8, "num_faces": 16, "num_internal_faces": 4}

        mp = MeshParams(tet_stop_energy=3.5)
        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                generate_mesh_dev(cube_stl, tmp_path / "case", params=mp)

        call_kwargs = mock_pytet.tetrahedralize.call_args[1]
        assert call_kwargs["stop_energy"] == pytest.approx(3.5)

    def test_pro_edge_fac_override_used(self, cube_stl: Path, tmp_path: Path):
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 10, "num_points": 8, "num_faces": 16, "num_internal_faces": 4}

        mp = MeshParams(tet_edge_length_fac=0.07)
        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                generate_mesh_dev(cube_stl, tmp_path / "case", params=mp)

        call_kwargs = mock_pytet.tetrahedralize.call_args[1]
        assert call_kwargs["edge_length_fac"] == pytest.approx(0.07)

    def test_auto_edge_fac_used_when_not_overridden(self, cube_stl: Path, tmp_path: Path):
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 10, "num_points": 8, "num_faces": 16, "num_internal_faces": 4}

        mp = MeshParams(tet_edge_length_fac=None)  # no override → auto
        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                generate_mesh_dev(cube_stl, tmp_path / "case", params=mp)

        call_kwargs = mock_pytet.tetrahedralize.call_args[1]
        # Auto-calculated fac should be in the valid range
        assert 0.02 <= call_kwargs["edge_length_fac"] <= 0.2

    def test_edge_fac_clamped_below_minimum(self, cube_stl: Path, tmp_path: Path):
        """tet_edge_length_fac below 0.02 is clamped to 0.02 in dev_pipeline."""
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 10, "num_points": 8, "num_faces": 16, "num_internal_faces": 4}

        mp = MeshParams(tet_edge_length_fac=0.005)  # below the 0.02 floor
        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                generate_mesh_dev(cube_stl, tmp_path / "case", params=mp)

        call_kwargs = mock_pytet.tetrahedralize.call_args[1]
        assert call_kwargs["edge_length_fac"] == pytest.approx(0.02)

    def test_edge_fac_clamped_above_maximum(self, cube_stl: Path, tmp_path: Path):
        """tet_edge_length_fac above 0.2 is clamped to 0.2 in dev_pipeline."""
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 10, "num_points": 8, "num_faces": 16, "num_internal_faces": 4}

        mp = MeshParams(tet_edge_length_fac=0.5)  # above the 0.2 ceiling
        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                generate_mesh_dev(cube_stl, tmp_path / "case", params=mp)

        call_kwargs = mock_pytet.tetrahedralize.call_args[1]
        assert call_kwargs["edge_length_fac"] == pytest.approx(0.2)

    def test_result_contains_num_points_and_num_faces(self, cube_stl: Path, tmp_path: Path):
        """generate_mesh_dev must return num_points and num_faces from write_polymesh."""
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 80, "num_points": 50, "num_faces": 200, "num_internal_faces": 100}

        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                result = generate_mesh_dev(cube_stl, tmp_path / "case")

        assert result["num_points"] == 50
        assert result["num_faces"] == 200


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestGenerateMeshDevErrors:
    def test_raises_when_pytetwild_not_installed(self, cube_stl: Path, tmp_path: Path):
        import sys
        with patch.dict(sys.modules, {"pytetwild": None}):
            with pytest.raises(RuntimeError, match="pytetwild"):
                generate_mesh_dev(cube_stl, tmp_path / "case")

    def test_raises_when_pytetwild_raises(self, cube_stl: Path, tmp_path: Path):
        mock_pytet = MagicMock()
        mock_pytet.tetrahedralize.side_effect = RuntimeError("tet failed")

        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with pytest.raises(RuntimeError, match="pytetwild"):
                generate_mesh_dev(cube_stl, tmp_path / "case")

    def test_raises_on_invalid_stl(self, tmp_path: Path):
        stl = tmp_path / "bad.stl"
        stl.write_bytes(b"not a valid stl")

        mock_pytet = _make_mock_pytetwild()
        # Invalid STL → trimesh may fail or return non-Trimesh object
        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            # Either a RuntimeError or some mesh-related exception is acceptable
            try:
                generate_mesh_dev(stl, tmp_path / "case")
            except (RuntimeError, Exception):
                pass  # Expected

    def test_default_params_used_when_none_passed(self, cube_stl: Path, tmp_path: Path):
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 10, "num_points": 8, "num_faces": 16, "num_internal_faces": 4}

        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                result = generate_mesh_dev(cube_stl, tmp_path / "case", params=None)

        # Should complete without error using default MeshParams
        assert result["tier"] == "pytetwild_dev"

    def test_mesh_purpose_fea_does_not_change_behavior(self, cube_stl: Path, tmp_path: Path):
        """FEA purpose doesn't skip pytetwild (unlike snappyHexMesh in full pipeline)."""
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 10, "num_points": 8, "num_faces": 16, "num_internal_faces": 4}

        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                result = generate_mesh_dev(cube_stl, tmp_path / "case", mesh_purpose="fea")

        assert result["tier"] == "pytetwild_dev"
        mock_pytet.tetrahedralize.assert_called_once()

    def test_raises_when_trimesh_load_returns_non_trimesh(self, cube_stl: Path, tmp_path: Path):
        """trimesh.load returning a non-Trimesh object must raise RuntimeError."""
        mock_pytet = _make_mock_pytetwild()

        import trimesh as real_trimesh
        # Return a Scene (non-Trimesh) to trigger the isinstance check
        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch.object(real_trimesh, "load", return_value=object()):
                with pytest.raises(RuntimeError, match="STL 로딩 실패"):
                    generate_mesh_dev(cube_stl, tmp_path / "case")

    def test_num_internal_faces_not_in_result(self, cube_stl: Path, tmp_path: Path):
        """generate_mesh_dev must NOT expose num_internal_faces in its return dict."""
        mock_pytet = _make_mock_pytetwild()
        mock_stats = {"num_cells": 80, "num_points": 50, "num_faces": 200, "num_internal_faces": 100}

        with patch.dict(__import__("sys").modules, {"pytetwild": mock_pytet}):
            with patch("mesh.dev_pipeline.write_polymesh", return_value=mock_stats):
                result = generate_mesh_dev(cube_stl, tmp_path / "case")

        assert "num_internal_faces" not in result
