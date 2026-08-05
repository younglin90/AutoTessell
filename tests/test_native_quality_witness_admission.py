from __future__ import annotations

import numpy as np

from core.evaluator.native_quality_witness_admission import validate_native_quality_witness
from core.utils.native_extensions import import_native_extension


def _witness():
    kernel = import_native_extension("native_quality_witness")
    points = np.array([
        [0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.],
        [0., 0., 1.], [1., 0., 1.], [1., 1., 1.], [0., 1., 1.],
    ])
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    result = dict(kernel.build_full_volume_quality_witness(
        points, faces, np.zeros(6, dtype=np.int64), np.empty(0, dtype=np.int64),
        ["core"], ["cell:0"],
    ))
    for index, row in enumerate(result["faces"]):
        row["face_uid"] = f"face:{index}"
        row["owner_cell_uid"] = "cell:0"
    for row in result["volume_quality"]["cells"]:
        row["cell_uid"] = "cell:0"
    result["entity_lineage"] = {
        "feature": {"cell:0": "feature:0"}, "patch": {"cell:0": "wall"},
        "physical_group": {"cell:0": "fluid"}, "component": {"cell:0": "component:0"},
        "provenance": {"cell:0": "source:0"},
    }
    return result


def test_complete_cpp_population_and_lineage_is_admitted():
    result = validate_native_quality_witness(_oriented_cube_witness())
    assert result["accepted"] is True, result



def test_aspect_gate_uses_p99_not_p95():
    witness = _oriented_cube_witness()
    witness["quality"]["aspect_ratio"]["p95"] = 100.0
    result = validate_native_quality_witness(witness)
    assert result["accepted"] is True, result

def test_missing_entity_uid_is_refused():
    witness = _witness()
    del witness["faces"][0]["face_uid"]
    result = validate_native_quality_witness(witness)
    assert result["accepted"] is False
    assert "witness_face_uid_missing" in result["reasons"]


def test_positive_bl_requires_measured_count_thickness_and_lineage():
    witness = _witness()
    witness["boundary_layer"] = {
        "requested_layers": 1, "actual_layers": 0,
        "positive_thickness": False, "lineage_complete": False,
    }
    result = validate_native_quality_witness(witness, requested_layers=1)
    assert result["accepted"] is False
    assert "positive_boundary_layer_count_mismatch" in result["reasons"]

def _witness():
    kernel = import_native_extension("native_quality_witness")
    points = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.], [0., 0., -1.]])
    faces = [[0, 2, 1], [0, 3, 1], [1, 3, 2], [2, 3, 0], [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    owner = np.array([0, 0, 0, 0, 1, 1, 1], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    result = dict(kernel.build_full_volume_quality_witness(
        points, faces, owner, neighbour, ["core", "boundary_layer"], ["cell:0", "cell:1"]
    ))
    for row in result["volume_quality"]["cells"]:
        row["cell_uid"] = f"cell:{row['cell_index']}"
    for index, row in enumerate(result["faces"]):
        row["face_uid"] = f"face:{index}"
        row["owner_cell_uid"] = f"cell:{row['owner_cell']}"
        if row.get("neighbour_cell") is not None:
            row["neighbour_cell_uid"] = f"cell:{row['neighbour_cell']}"
    result["entity_lineage"] = {"feature": {"cell:0": "feature:0", "cell:1": "feature:1"}, "patch": {"cell:0": "wall", "cell:1": "wall"}, "physical_group": {"cell:0": "fluid", "cell:1": "fluid"}, "component": {"cell:0": "component:0", "cell:1": "component:0"}, "provenance": {"cell:0": "source:0", "cell:1": "source:1"}}
    return result

def _oriented_cube_witness():
    kernel = import_native_extension("native_quality_witness")
    points = np.array([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.], [0., 0., 1.], [1., 0., 1.], [1., 1., 1.], [0., 1., 1.]])
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    result = dict(kernel.build_full_volume_quality_witness(points, faces, np.zeros(6, dtype=np.int64), np.empty(0, dtype=np.int64), ["core"], ["cell:0"]))
    for row in result["volume_quality"]["cells"]:
        row["cell_uid"] = "cell:0"
    for index, row in enumerate(result["faces"]):
        row["face_uid"] = f"face:{index}"
        row["owner_cell_uid"] = "cell:0"
    result["entity_lineage"] = {"feature": {"cell:0": "feature:0"}, "patch": {"cell:0": "wall"}, "physical_group": {"cell:0": "fluid"}, "component": {"cell:0": "component:0"}, "provenance": {"cell:0": "source:0"}}
    return result
