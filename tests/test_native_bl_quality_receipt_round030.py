"""Round 030: persisted Native BL receipt regressions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.native_bl import BLConfig, generate_native_bl


def _single_tet(case_dir: Path) -> None:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
         [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    write_generic_polymesh(
        points,
        [[[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]],
        case_dir,
        patch_name="wall",
        patch_type="wall",
    )


def _mesh_digest(case_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        digest.update((case_dir / "constant" / "polyMesh" / name).read_bytes())
    return digest.hexdigest()


def test_bl0_receipt_is_identity_and_mesh_is_unchanged(tmp_path: Path) -> None:
    _single_tet(tmp_path)
    before = _mesh_digest(tmp_path)

    result = generate_native_bl(tmp_path, BLConfig(num_layers=0))

    assert result.success
    assert result.requested_layers == 0
    assert result.actual_layers == 0
    assert result.termination_reason == "disabled_identity"
    assert result.positive_thickness is False
    assert _mesh_digest(tmp_path) == before


def test_positive_bl_receipt_reads_persisted_quality(tmp_path: Path) -> None:
    _single_tet(tmp_path)

    result = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.02,
            growth_ratio=1.0,
            collision_safety=False,
            feature_lock=False,
            quality_check_enabled=False,
            backup_original=False,
        ),
    )

    assert result.success, result.message
    assert result.requested_layers == 1
    assert result.actual_layers == 1
    assert result.positive_thickness is True
    assert result.first_layer_height > 0.0
    assert result.quality_readback_status == "measured"
    assert result.negative_volumes == 0
    assert result.max_skewness is not None
    assert result.max_non_orthogonality is not None

    quality = json.loads((tmp_path / "native_bl_quality.json").read_text())
    assert quality["boundary_layer"]["requested_layers"] == 1
    assert quality["boundary_layer"]["actual_layers"] == 1
    assert quality["boundary_layer"]["positive_first_layer_height"] > 0.0
    assert quality["boundary_layer"]["positive_cell_count"] > 0
    assert quality["boundary_layer"]["positive_thickness"] is True
    assert quality["quality_readback"]["status"] == "measured"
    assert quality["quality_readback"]["negative_volumes"] == 0
