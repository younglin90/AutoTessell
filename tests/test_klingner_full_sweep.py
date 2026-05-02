"""KLINGNER-FULL + BC-PICK unit tests (low memory)."""
from __future__ import annotations

import numpy as np
import pytest


def _gen_simple_tet_mesh():
    """5 verts, 2 tets sharing a face."""
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=np.int64)
    return pts, tets


def test_klingner_full_sweep_too_small():
    from core.generator.native_tet.klingner_full_sweep import klingner_full_sweep
    pts, tets = _gen_simple_tet_mesh()
    new_pts, new_tets, r = klingner_full_sweep(pts, tets, n_cycles=2)
    # 2 tets < 50 → too_small.
    assert r.reason == "too_small"
    assert new_tets.shape == tets.shape


def test_klingner_full_sweep_empty():
    from core.generator.native_tet.klingner_full_sweep import klingner_full_sweep
    new_pts, new_tets, r = klingner_full_sweep(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
    )
    assert r.reason == "too_small"


def test_klingner_full_sweep_real_mesh():
    """scipy Delaunay 로 100+ tet 생성 후 sweep 적용."""
    pytest.importorskip("scipy")
    from scipy.spatial import Delaunay
    from core.generator.native_tet.klingner_full_sweep import klingner_full_sweep
    rng = np.random.RandomState(42)
    pts = rng.rand(60, 3).astype(np.float64)
    d = Delaunay(pts)
    tets = d.simplices.astype(np.int64)
    if tets.shape[0] < 50:
        pytest.skip("not enough tets")
    new_pts, new_tets, r = klingner_full_sweep(pts, tets, n_cycles=2)
    # accepted=True 면 mean_q 향상 또는 동등.
    if r.accepted:
        assert r.post_mean_q >= r.pre_mean_q - 1e-6


# -- BC face picker tests --

def test_bc_assignment_basic():
    from desktop.qt_app.bc_face_picker import BCAssignment, BC_TYPES
    ba = BCAssignment(name="wall_in", bc_type="inlet",
                      face_indices=[1, 2, 3])
    assert ba.bc_type == "inlet"
    assert "inlet" in BC_TYPES


def test_bc_manager_add_get_remove():
    from desktop.qt_app.bc_face_picker import BCManager, BCAssignment
    m = BCManager()
    ba1 = BCAssignment(name="wall", bc_type="wall", face_indices=[1, 2])
    m.add(ba1)
    assert len(m) == 1
    assert m.get("wall").bc_type == "wall"
    # add same name → merge.
    ba2 = BCAssignment(name="wall", bc_type="wall", face_indices=[2, 3, 4])
    m.add(ba2)
    assert len(m) == 1
    assert sorted(m.get("wall").face_indices) == [1, 2, 3, 4]
    assert m.remove("wall") is True
    assert len(m) == 0


def test_bc_manager_to_ccmio_dict():
    from desktop.qt_app.bc_face_picker import BCManager, BCAssignment
    m = BCManager()
    m.add(BCAssignment(
        name="inlet1", bc_type="inlet",
        face_indices=[1, 2],
        values={"velocity": [1.0, 0.0, 0.0]},
        comment="main flow",
    ))
    m.add(BCAssignment(
        name="outlet1", bc_type="outlet",
        face_indices=[3, 4],
        values={"pressure": 0.0},
    ))
    d = m.to_ccmio_dict()
    assert "inlet1" in d and "outlet1" in d
    assert d["inlet1"]["type"] == "inlet"
    assert d["inlet1"]["comment"] == "main flow"
    assert d["outlet1"]["values"]["pressure"] == 0.0


def test_bc_manager_export_to_ccmio(tmp_path):
    pytest.importorskip("h5py")
    import h5py
    from desktop.qt_app.bc_face_picker import BCManager, BCAssignment
    p = tmp_path / "test.h5"
    with h5py.File(p, "w") as f:
        f.create_group("Meshes/Mesh-0")

    m = BCManager()
    m.add(BCAssignment(
        name="wall", bc_type="wall", face_indices=[1, 2],
        values={"velocity": [0.0, 0, 0]},
    ))
    assert m.export_to_ccmio(p)

    from core.utils.ccmio_writer import read_ccmio_boundary_conditions
    rd = read_ccmio_boundary_conditions(p)
    assert "wall" in rd
    assert rd["wall"]["type"] == "wall"


def test_bc_make_assignment_from_user():
    from desktop.qt_app.bc_editor_dialog import (
        make_bc_assignment_from_user_input,
    )
    ba = make_bc_assignment_from_user_input(
        face_indices=[10, 11, 12],
        name="my_inlet",
        bc_type="velocity_inlet",
        values={"velocity": [2.0, 0, 0]},
        comment="test",
    )
    assert ba.name == "my_inlet"
    assert ba.bc_type == "velocity_inlet"
    assert ba.face_indices == [10, 11, 12]
    assert ba.values["velocity"] == [2.0, 0, 0]
    assert ba.comment == "test"


def test_bc_make_assignment_invalid_type_falls_back():
    from desktop.qt_app.bc_editor_dialog import (
        make_bc_assignment_from_user_input,
    )
    ba = make_bc_assignment_from_user_input(
        face_indices=[1], name="x", bc_type="invalid_type_xyz",
    )
    assert ba.bc_type == "wall"  # fallback.


def test_bc_export_polymesh_boundary(tmp_path):
    """polyMesh/boundary file 생성/갱신 검증."""
    from desktop.qt_app.bc_face_picker import BCManager, BCAssignment
    pdir = tmp_path / "polyMesh"
    pdir.mkdir()
    bfile = pdir / "boundary"
    bfile.write_text("0\n()\n")  # placeholder.

    m = BCManager()
    m.add(BCAssignment(
        name="inlet", bc_type="velocity_inlet", face_indices=[100, 101, 102],
    ))
    m.add(BCAssignment(
        name="wall", bc_type="wall", face_indices=[200, 201],
    ))
    assert m.export_face_groups_to_polymesh_boundary(pdir, n_total_faces=300)
    content = bfile.read_text()
    assert "inlet" in content
    assert "wall" in content
    assert "velocity_inlet" in content


# E: 확장 BC types (BETA2800).

def test_bc_extended_types_present():
    from desktop.qt_app.bc_face_picker import BC_TYPES, BC_DEFAULT_VALUES
    advanced = ["periodic", "cyclic_ami", "interface_heat",
                "sliding_mesh", "fan", "porous_jump", "wedge",
                "mass_flow_inlet", "outflow"]
    for t in advanced:
        assert t in BC_TYPES, f"{t} missing from BC_TYPES"
        assert t in BC_DEFAULT_VALUES, f"{t} missing default values"


def test_bc_extended_default_values():
    from desktop.qt_app.bc_face_picker import BC_DEFAULT_VALUES
    assert "omega" in BC_DEFAULT_VALUES["sliding_mesh"]
    assert "axis" in BC_DEFAULT_VALUES["sliding_mesh"]
    assert "pressure_jump" in BC_DEFAULT_VALUES["fan"]
    assert "resistance" in BC_DEFAULT_VALUES["porous_jump"]
    assert "htc" in BC_DEFAULT_VALUES["interface_heat"]


# D: BC overlay color map (BETA2799).

def test_bc_overlay_color_map():
    from desktop.qt_app.bc_overlay import BC_COLOR_MAP, get_bc_color
    assert "wall" in BC_COLOR_MAP
    assert "fan" in BC_COLOR_MAP
    assert "periodic" in BC_COLOR_MAP
    # default fallback.
    c = get_bc_color("nonexistent_xyz")
    assert isinstance(c, tuple) and len(c) == 3


def test_bc_overlay_legend():
    from desktop.qt_app.bc_face_picker import BCManager, BCAssignment
    from desktop.qt_app.bc_overlay import patch_color_legend
    m = BCManager()
    m.add(BCAssignment(name="w1", bc_type="wall", face_indices=[1]))
    m.add(BCAssignment(name="i1", bc_type="inlet", face_indices=[2]))
    legend = patch_color_legend(m)
    assert len(legend) == 2
    assert legend[0][0] == "w1"
    assert legend[1][1] == "inlet"


# C: OpenFOAM 0/ field write (BETA2802).

def test_openfoam_field_write_U_p(tmp_path):
    from desktop.qt_app.bc_face_picker import BCManager, BCAssignment
    from core.utils.openfoam_field_writer import write_openfoam_fields

    m = BCManager()
    m.add(BCAssignment(
        name="inlet", bc_type="velocity_inlet", face_indices=[1, 2],
        values={"velocity": [2.5, 0.0, 0.0]},
    ))
    m.add(BCAssignment(
        name="outlet", bc_type="pressure_outlet", face_indices=[3, 4],
        values={"pressure": 0.0},
    ))
    m.add(BCAssignment(
        name="wall", bc_type="wall", face_indices=[5, 6],
        values={"velocity": [0, 0, 0]},
    ))

    res = write_openfoam_fields(tmp_path, m, fields=("U", "p"))
    assert res.success
    assert res.n_fields_written == 2
    assert (tmp_path / "0" / "U").exists()
    assert (tmp_path / "0" / "p").exists()

    u_text = (tmp_path / "0" / "U").read_text()
    assert "boundaryField" in u_text
    assert "inlet" in u_text
    assert "fixedValue" in u_text
    assert "(2.5 0.0 0.0)" in u_text
    assert "zeroGradient" in u_text  # outlet U = zeroGradient.

    p_text = (tmp_path / "0" / "p").read_text()
    assert "outlet" in p_text
    assert "fixedValue" in p_text


def test_openfoam_field_temperature(tmp_path):
    from desktop.qt_app.bc_face_picker import BCManager, BCAssignment
    from core.utils.openfoam_field_writer import write_openfoam_fields

    m = BCManager()
    m.add(BCAssignment(
        name="hot_wall", bc_type="interface_heat", face_indices=[1],
        values={"htc": 500.0, "T_ext": 350.0},
    ))
    res = write_openfoam_fields(
        tmp_path, m, fields=("T",), include_temperature=True,
    )
    assert res.success
    t_text = (tmp_path / "0" / "T").read_text()
    assert "externalWallHeatFluxTemperature" in t_text
    assert "500.0" in t_text
    assert "350.0" in t_text


def test_openfoam_field_advanced_bc(tmp_path):
    from desktop.qt_app.bc_face_picker import BCManager, BCAssignment
    from core.utils.openfoam_field_writer import write_openfoam_fields

    m = BCManager()
    m.add(BCAssignment(
        name="fan_in", bc_type="fan", face_indices=[1, 2],
        values={"pressure_jump": 200.0},
    ))
    m.add(BCAssignment(
        name="periodic_x", bc_type="periodic", face_indices=[3, 4],
    ))
    m.add(BCAssignment(
        name="symm", bc_type="symmetry", face_indices=[5, 6],
    ))
    res = write_openfoam_fields(tmp_path, m)
    assert res.success
    p_text = (tmp_path / "0" / "p").read_text()
    assert "fan" in p_text
    assert "200.0" in p_text
    u_text = (tmp_path / "0" / "U").read_text()
    assert "cyclic" in u_text
    assert "symmetryPlane" in u_text


def test_openfoam_bcmanager_export_fields(tmp_path):
    from desktop.qt_app.bc_face_picker import BCManager, BCAssignment
    m = BCManager()
    m.add(BCAssignment(
        name="inlet", bc_type="velocity_inlet", face_indices=[1],
        values={"velocity": [1, 0, 0]},
    ))
    m.add(BCAssignment(
        name="outlet", bc_type="outlet", face_indices=[2],
    ))
    res = m.export_openfoam_fields(tmp_path)
    assert res.success
    assert (tmp_path / "0" / "U").exists()
    assert (tmp_path / "0" / "p").exists()


# Self-impl: METRIC-TENSOR sweep (BETA2803).

def test_metric_tensor_isotropic():
    from core.generator.native_tet.metric_tensor_sweep import (
        compute_isotropic_metric,
    )
    pts = np.random.RandomState(0).rand(20, 3).astype(np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    M = compute_isotropic_metric(pts, tets, target_edge=0.5)
    assert M.shape == (20, 3, 3)
    # M[i] = (1/0.25) * I = 4 * I.
    assert abs(M[0, 0, 0] - 4.0) < 1e-9
    assert abs(M[0, 0, 1]) < 1e-9


def test_metric_edge_length_sq():
    from core.generator.native_tet.metric_tensor_sweep import metric_edge_length_sq
    p0 = np.array([0, 0, 0])
    p1 = np.array([1, 0, 0])
    M = np.eye(3) * 4.0
    L_sq = metric_edge_length_sq(p0, p1, M, M)
    assert abs(float(L_sq) - 4.0) < 1e-9


def test_metric_tensor_sweep_too_small():
    from core.generator.native_tet.metric_tensor_sweep import metric_tensor_sweep
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    new_pts, new_tets, r = metric_tensor_sweep(pts, tets, n_cycles=2)
    # 1 tet < 50 → too_small (no change).
    assert new_tets.shape == tets.shape


# CCMIO-NATIVE Pro-STAR mimic (BETA2804).

def test_ccmio_native_cell_classify():
    from core.utils.ccmio_native_binary import _classify_cell_pro_star
    # tet: 4 tri faces → 1.
    assert _classify_cell_pro_star(4, [3, 3, 3, 3]) == 1
    # hex: 6 quad → 4.
    assert _classify_cell_pro_star(6, [4, 4, 4, 4, 4, 4]) == 4
    # pyr: 4 tri + 1 quad → 2.
    assert _classify_cell_pro_star(5, [3, 3, 3, 3, 4]) == 2
    # wedge: 2 tri + 3 quad → 3.
    assert _classify_cell_pro_star(5, [3, 3, 4, 4, 4]) == 3
    # poly: anything else → 5.
    assert _classify_cell_pro_star(7, [3, 3, 4, 5, 5, 6, 6]) == 5


def test_ccmio_native_simple_polymesh_read(tmp_path):
    """간단 polyMesh fixture 생성 후 _simple_polymesh_read 테스트."""
    from core.utils.ccmio_native_binary import _simple_polymesh_read
    pdir = tmp_path / "polyMesh"
    pdir.mkdir()
    (pdir / "points").write_text(
        "FoamFile\n3\n(\n(0 0 0)\n(1 0 0)\n(0 1 0)\n)\n",
    )
    (pdir / "faces").write_text(
        "1\n(\n3(0 1 2)\n)\n",
    )
    (pdir / "owner").write_text("1\n(\n0\n)\n")
    (pdir / "neighbour").write_text("0\n(\n)\n")
    (pdir / "boundary").write_text(
        "FoamFile\n1\n(\n    inlet\n    {\n"
        "        type            patch;\n"
        "        nFaces          1;\n"
        "        startFace       0;\n"
        "    }\n)\n",
    )
    pts, faces, owner, nbr, bnd = _simple_polymesh_read(pdir)
    assert pts is not None and pts.shape == (3, 3)
    assert len(faces) == 1
    assert len(owner) == 1
    assert len(bnd) == 1 and bnd[0]["name"] == "inlet"


def test_ccmio_native_write_pro_star(tmp_path):
    pytest.importorskip("h5py")
    import h5py
    from core.utils.ccmio_native_binary import write_ccmio_native_pro_star

    # fake polyMesh: 1 tet + 4 tri patches.
    pdir = tmp_path / "polyMesh"
    pdir.mkdir()
    (pdir / "points").write_text(
        "FoamFile\n4\n(\n(0 0 0)\n(1 0 0)\n(0 1 0)\n(0 0 1)\n)\n",
    )
    (pdir / "faces").write_text(
        "4\n(\n3(0 1 2)\n3(0 1 3)\n3(0 2 3)\n3(1 2 3)\n)\n",
    )
    (pdir / "owner").write_text("4\n(\n0\n0\n0\n0\n)\n")
    (pdir / "neighbour").write_text("0\n(\n)\n")
    (pdir / "boundary").write_text(
        "FoamFile\n1\n(\n    walls\n    {\n"
        "        type            wall;\n"
        "        nFaces          4;\n"
        "        startFace       0;\n"
        "    }\n)\n",
    )

    out = tmp_path / "test.ccm"
    res = write_ccmio_native_pro_star(pdir, out, big_endian=True)
    assert res.success, f"failed: {res.message}"
    assert res.n_vertices == 4
    assert res.n_cells == 1
    assert res.pro_star_compat_level == "HDF1.4-mimic"

    # verify hdf5 structure.
    with h5py.File(str(out), "r") as f:
        assert "State" in f
        assert "State/Default/Topology/Mesh-1" in f
        mg = f["State/Default/Topology/Mesh-1"]
        assert "Vertices/Coordinates" in mg
        assert "Cells/CellType" in mg
        assert "BoundaryFaces-1" in mg
        # cell type = tet → 1.
        ct = mg["Cells/CellType"][...]
        assert int(ct[0]) == 1
        # attrs.
        assert mg.attrs["NumVertices"] == 4
        assert mg.attrs["NumCells"] == 1
    # root attrs.
    with h5py.File(str(out), "r") as f:
        assert f.attrs["AdapcoCompat"] == b"HDF5-mimic-v1"
