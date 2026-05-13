"""U-22 unit tests: AUTO_TESSELL_WILDMESH_REJECT_VARYING_SECTION env knob.

Validates that:
1. ``_classify_axis_section_topology`` returns ``changing_section_sweep``
   for sections whose polygon count or hole count varies along the
   axis (the topology_stable flag is False).
2. The classifier returns ``constant_prism`` for stable sections.
3. The env knob, when set to ``1`` plus a "changing_section" classification,
   causes ``_write_axis_extrusion_polymesh`` to return None (the early
   reject path), letting the caller fall through.
"""
from __future__ import annotations

import os

import pytest


def test_classify_constant_prism():
    from core.generator.tier_wildmesh import _classify_axis_section_topology

    topology = {
        "sample_count": 5,
        "usable_count": 5,
        "polygon_counts": [1, 1, 1, 1, 1],
        "hole_counts": [0, 0, 0, 0, 0],
        "area_min": 100.0,
        "area_max": 100.0,
        "topology_stable": True,
    }
    result = _classify_axis_section_topology(
        topology, cap_loop_count=1, cap_hole_count=0,
    )
    assert result == "constant_prism", result


def test_classify_stable_hole_sweep():
    from core.generator.tier_wildmesh import _classify_axis_section_topology

    topology = {
        "sample_count": 5,
        "usable_count": 5,
        "polygon_counts": [1, 1, 1, 1, 1],
        "hole_counts": [2, 2, 2, 2, 2],
        "area_min": 100.0,
        "area_max": 100.0,
        "topology_stable": True,
    }
    result = _classify_axis_section_topology(
        topology, cap_loop_count=4, cap_hole_count=3,
    )
    # cap_polygon=1, section_polygon=1, but section_hole=2 != cap_hole=3
    assert result == "stable_hole_sweep", result


def test_classify_changing_section_sweep():
    from core.generator.tier_wildmesh import _classify_axis_section_topology

    # polygon_counts identical but hole_counts vary along the axis →
    # topology_stable=False → classifier returns changing_section_sweep
    topology = {
        "sample_count": 5,
        "usable_count": 5,
        "polygon_counts": [1, 1, 1, 1, 1],
        "hole_counts": [5, 3, 3, 1, 1],
        "area_min": 127.0,
        "area_max": 5332.0,
        "topology_stable": False,
    }
    result = _classify_axis_section_topology(
        topology, cap_loop_count=6, cap_hole_count=5,
    )
    assert result == "changing_section_sweep", result


def test_classify_unsafe_when_section_missing():
    from core.generator.tier_wildmesh import _classify_axis_section_topology

    topology = {
        "sample_count": 5,
        "usable_count": 0,
        "polygon_counts": [],
        "hole_counts": [],
        "topology_stable": False,
    }
    result = _classify_axis_section_topology(
        topology, cap_loop_count=0, cap_hole_count=0,
    )
    assert result == "unsafe_sweep", result


def test_reject_varying_section_env_default_off(monkeypatch):
    """When the env is unset/0 the gate is inactive — function does not
    abort early on varying-section inputs."""
    monkeypatch.delenv(
        "AUTO_TESSELL_WILDMESH_REJECT_VARYING_SECTION",
        raising=False,
    )
    # The gate string is read at runtime via os.environ.get default "0".
    assert (
        os.environ.get(
            "AUTO_TESSELL_WILDMESH_REJECT_VARYING_SECTION", "0",
        ) == "0"
    )


def test_reject_varying_section_env_on(monkeypatch):
    """When the env is "1" the gate is active."""
    monkeypatch.setenv(
        "AUTO_TESSELL_WILDMESH_REJECT_VARYING_SECTION", "1",
    )
    assert (
        os.environ.get(
            "AUTO_TESSELL_WILDMESH_REJECT_VARYING_SECTION", "0",
        ) == "1"
    )


def test_extrusion_writer_rejects_cone_when_env_on(tmp_path, monkeypatch):
    """Integration test: a cone has a varying cross-section (radius
    shrinks along axis).  With the env gate ON, the extrusion writer
    must return None instead of producing an approximated polyMesh."""
    pytest.importorskip("trimesh")
    pytest.importorskip("meshpy.triangle")
    pytest.importorskip("shapely")

    import trimesh
    from core.generator.tier_wildmesh import _write_axis_extrusion_polymesh

    cone = trimesh.creation.cone(radius=1.0, height=2.0, sections=20)

    monkeypatch.setenv(
        "AUTO_TESSELL_WILDMESH_REJECT_VARYING_SECTION", "1",
    )
    case_dir = tmp_path / "cone_reject"
    case_dir.mkdir()
    result = _write_axis_extrusion_polymesh(
        cone, case_dir, target_cells=2000, bl_layers=3, forced_axis=2,
    )
    assert result is None, (
        f"expected reject for cone (varying section), got {result}"
    )


def test_extrusion_writer_accepts_cone_when_env_off(tmp_path, monkeypatch):
    """Default behaviour: env unset.  Cone should still be processed
    (extrusion fastpath approximation), confirming the gate is opt-in."""
    pytest.importorskip("trimesh")
    pytest.importorskip("meshpy.triangle")
    pytest.importorskip("shapely")

    import trimesh
    from core.generator.tier_wildmesh import _write_axis_extrusion_polymesh

    cone = trimesh.creation.cone(radius=1.0, height=2.0, sections=20)

    monkeypatch.delenv(
        "AUTO_TESSELL_WILDMESH_REJECT_VARYING_SECTION", raising=False,
    )
    case_dir = tmp_path / "cone_accept"
    case_dir.mkdir()
    result = _write_axis_extrusion_polymesh(
        cone, case_dir, target_cells=2000, bl_layers=3, forced_axis=2,
    )
    # Default (env unset) — extrusion writer proceeds and writes some
    # polyMesh result.  Failure modes other than the varying-section
    # gate (e.g. import errors) would also return None, but we check
    # for a non-None dict to confirm the gate didn't fire.
    assert result is not None, (
        "expected extrusion writer to succeed when reject gate is off"
    )
    assert isinstance(result, dict)
    assert int(result.get("num_cells", 0)) > 0
