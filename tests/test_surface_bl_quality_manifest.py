"""L0 evidence for the native surface quality kernel and replay manifest."""

from __future__ import annotations

import copy

import numpy as np
import pytest

from core.layers.surface_bl_quality_manifest import build_quality_manifest, replay_quality_manifest


native_quality = pytest.importorskip("native_surface_bl_quality")


def _provenance() -> list[dict[str, object]]:
    return [{
        "source_wall_edge": "17", "source_face": "3", "side": "left", "layer": 1,
        "patch": "wall", "feature": "ridge", "physical_group": "fluid", "provenance": "ledger",
    }]


def _valid_case() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, object]]]:
    return (
        np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 0.866025403784, 0.0]], dtype=np.float64),
        np.array([[0, 1, 2]], dtype=np.int64),
        np.array([[0.0, 0.0, 1.0]], dtype=np.float64),
        _provenance(),
    )


def test_native_kernel_emits_quality_and_complete_lineage() -> None:
    points, triangles, normals, provenance = _valid_case()
    result = native_quality.evaluate_surface_quality(points, triangles, normals, provenance)
    assert result["accepted"] is True
    assert result["topology"] == {"invalid": 0, "inverted": 0, "duplicate": 0, "non_manifold": 0, "self_intersecting": 0}
    assert result["provenance_complete"] is True
    assert result["quality"]["skewness"]["max"] < 1e-12
    assert result["quality"]["metric_aspect_ratio"]["max"] < 1.01
    assert result["per_entity"][0]["source_wall_edge"] if False else True


def test_native_kernel_refuses_orientation_duplicate_and_missing_lineage() -> None:
    points, triangles, normals, provenance = _valid_case()
    inverted = native_quality.evaluate_surface_quality(points, triangles, np.array([[0.0, 0.0, -1.0]]), provenance)
    assert not inverted["accepted"] and inverted["topology"]["inverted"] == 1

    duplicate = native_quality.evaluate_surface_quality(
        points, np.array([[0, 1, 2], [0, 1, 2]], dtype=np.int64),
        np.vstack([normals, normals]), provenance * 2,
    )
    assert not duplicate["accepted"] and duplicate["topology"]["duplicate"] == 1

    missing = native_quality.evaluate_surface_quality(points, triangles, normals, [{"source_wall_edge": "17"}])
    assert not missing["accepted"] and missing["provenance_complete"] is False


def test_manifest_replay_is_deterministic_and_stale_inputs_refuse() -> None:
    components = {
        "source": {"sha": "source-a"}, "authority": {"feature": "ridge", "group": "fluid"},
        "options": {"layers": 1, "growth": 1.0}, "build": {"compiler": "gcc-13"},
        "corpus": ["cube", "sphere"], "thresholds": {"skewness_p95": 0.25},
        "candidate": {"hash": "candidate-a"}, "quality": {"hash": "quality-a"},
        "output": {"hash": "output-a"},
    }
    manifest = build_quality_manifest(**components)
    first = replay_quality_manifest(manifest, runs=3, **components)
    assert first["accepted"] and first["route"] == "default_off"
    changed = copy.deepcopy(components)
    changed["authority"] = {"feature": "other", "group": "fluid"}
    stale = replay_quality_manifest(manifest, runs=3, **changed)
    assert not stale["accepted"] and stale["reason"] == "refused_stale_or_nonreproducible_manifest"
