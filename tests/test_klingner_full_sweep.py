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
