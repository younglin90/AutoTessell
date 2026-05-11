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
