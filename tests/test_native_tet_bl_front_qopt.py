from pathlib import Path
import sys

import numpy as np

BUILD = Path("auto_tessell_core/build").resolve()
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))

from native_tet_bl_front_qopt import optimize_native_tet_wall_front  # noqa: E402


def _inputs():
    wall = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float)
    front = np.array([[0.0, 0.0, 0.0], [1.25, 0.1, 0.0]], dtype=float)
    edges = np.array([[0, 1, 0, 11]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0]], dtype=float)
    labels = [["wall"], ["smooth"], ["fluid"], ["main"]]
    return wall, front, edges, normals, labels


def test_bl0_is_identity_and_positive_path_is_deterministic():
    wall, front, edges, normals, labels = _inputs()
    disabled = optimize_native_tet_wall_front(
        wall, front, edges, normals, *labels, 0
    )
    assert disabled["accepted"] is True
    assert disabled["status"] == "native_tet_bl_front_qopt_bl0_identity"

    first = optimize_native_tet_wall_front(
        wall, front, edges, normals, *labels, 1, 8, 1.0, 1e-12
    )
    second = optimize_native_tet_wall_front(
        wall, front, edges, normals, *labels, 1, 8, 1.0, 1e-12
    )
    assert first["accepted"] is True, first
    assert first["quality"] == second["quality"]
    np.testing.assert_allclose(first["corrected_wall_points"], second["corrected_wall_points"])
    q = first["quality"]
    assert q["max_wall_front_after"] < q["max_wall_front_before"]
    assert q["accepted_iterations"] >= 1
    assert first["candidate_discarded"] is False


def test_feature_or_patch_junction_is_fail_closed():
    wall, front, edges, normals, labels = _inputs()
    edges = np.array([[0, 1, 0, 11], [1, 2, 1, 12]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]], dtype=float)
    refused = optimize_native_tet_wall_front(
        wall, front, edges, normals,
        ["wall", "wall"], ["smooth", "feature"], ["fluid", "fluid"], ["main", "main"], 1
    )
    assert refused["accepted"] is False
    assert refused["reason"] == "feature_or_patch_junction_locked"
    assert refused["candidate_discarded"] is True
