from __future__ import annotations

import numpy as np
import pytest


def test_tet_writer_reports_user_controlled_bl_schedule_without_rewriting() -> None:
    import native_tet_bl_writer

    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    triangles = np.asarray([[0, 1, 2]], dtype=np.int64)
    normals = np.asarray([[0.0, 0.0, 1.0]] * 3, dtype=np.float64)
    first_height = 0.07
    growth_ratio = 1.2

    for layers in (0, 1, 3, 8):
        result = native_tet_bl_writer.generate(
            points, triangles, normals, layers, first_height, growth_ratio, 1.0e-14
        )
        expected = 0.0 if layers == 0 else first_height * (growth_ratio**layers - 1.0) / (growth_ratio - 1.0)
        assert result["accepted"] is True, result
        assert result["requested_layers"] == layers
        assert result["actual_layers"] == layers
        assert result["first_height"] == first_height
        assert result["growth_ratio"] == growth_ratio
        assert result["total_thickness"] == pytest.approx(expected)
        if layers:
            assert float(np.max(result["points"][:, 2])) == pytest.approx(expected)
