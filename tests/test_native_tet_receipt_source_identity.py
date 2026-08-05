from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from core.generator.native_tet.receipt_route import verify_surface_receipt_output


def _receipt() -> dict[str, object]:
    return {
        "interface_triangles": [
            {
                "source_face": "0",
                "output_face": "0",
                "triangle": [0, 1, 2],
                "feature": "wall",
                "patch": "wall",
                "physical_group": "fluid",
                "component": "main",
                "provenance": "source:0",
            }
        ]
    }


def test_receipt_output_requires_bitwise_source_prefix_identity() -> None:
    source = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    output = source.copy()
    output[0, 0] = 1.0e-12
    result = SimpleNamespace(
        tet_points=output,
        tets=np.asarray([[0, 1, 2, 3]], dtype=np.int64),
    )

    audit = verify_surface_receipt_output(
        _receipt(), result, source, np.asarray([[0, 1, 2]], dtype=np.int64), 0
    )

    assert audit == {
        "accepted": False,
        "reason": "tet_output_source_prefix_identity_mismatch",
    }
