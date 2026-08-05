from __future__ import annotations

import numpy as np


def _module():
    import native_tet_bl_writer

    return native_tet_bl_writer


def _triangle():
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    triangles = np.asarray([[0, 1, 2]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]] * 3, dtype=np.float64)
    return points, triangles, normals


def test_cpp_writer_bl0_is_exact_identity_and_sidecar_free() -> None:
    points, triangles, normals = _triangle()
    result = _module().generate(points, triangles, normals, 0, 0.0, 1.0)

    assert result["accepted"] is True
    assert result["status"] == "bl0_identity"
    assert result["actual_layers"] == 0
    assert result["writer_sidecar_emitted"] is False
    np.testing.assert_array_equal(result["points"], points)
    assert result["tets"].shape == (0, 4)


def test_cpp_writer_emits_deterministic_positive_prism_to_three_tets() -> None:
    points, triangles, normals = _triangle()
    first = _module().generate(points, triangles, normals, 1, 0.1, 1.0)
    second = _module().generate(points, triangles, normals, 1, 0.1, 1.0)

    assert first["accepted"] is True
    assert first["status"] == "candidate_writer_output"
    assert first["tets"].shape == (3, 4)
    assert first["points"].shape == (6, 3)
    assert first["quality"]["cell_count"] == 3
    assert first["quality"]["collision_checked"] is False
    assert first["ledger"]["prisms"][0]["child_tet_ids"] == ["cell-0", "cell-1", "cell-2"]
    np.testing.assert_array_equal(first["points"], second["points"])
    np.testing.assert_array_equal(first["tets"], second["tets"])
    assert first["ledger"]["graph_sha256"] == second["ledger"]["graph_sha256"]
    assert all(float(row["signed_volume"]) > 0.0 for row in first["ledger"]["cells"])
