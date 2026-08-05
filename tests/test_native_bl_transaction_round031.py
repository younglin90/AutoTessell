"""Round 031: Native BL private-stage admission and rollback evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.native_bl import BLConfig, NativeBLResult, generate_native_bl
from core.layers.native_bl_transaction import run_private_native_bl_transaction


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
    poly = case_dir / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        digest.update((poly / name).read_bytes())
    return digest.hexdigest()


def test_positive_native_bl_publishes_private_candidate_with_receipt(tmp_path: Path) -> None:
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
    assert result.transaction_status == "committed"
    receipt = json.loads(
        (tmp_path / "native_bl_transaction_receipt.json").read_text()
    )
    assert receipt["status"] == "committed"
    assert receipt["rolled_back"] is False
    assert receipt["input_fingerprint"] != receipt["candidate_fingerprint"]
    assert receipt["topology"]["valid"] is True


def test_rejected_private_candidate_preserves_authoritative_mesh(tmp_path: Path) -> None:
    _single_tet(tmp_path)
    before = _mesh_digest(tmp_path)

    def reject_candidate(stage: Path, _cfg: BLConfig, **_: object) -> NativeBLResult:
        points = stage / "constant" / "polyMesh" / "points"
        points.write_bytes(points.read_bytes() + b"\n")
        return NativeBLResult(
            success=False,
            elapsed=0.0,
            requested_layers=1,
            actual_layers=0,
            message="synthetic_candidate_rejection",
        )

    result = run_private_native_bl_transaction(
        tmp_path,
        BLConfig(num_layers=1, first_thickness=0.02),
        engine_tag="test",
        generate_fn=reject_candidate,
        result_cls=NativeBLResult,
    )

    assert result.success is False
    assert result.transaction_status == "rolled_back"
    assert _mesh_digest(tmp_path) == before
    receipt = json.loads(
        (tmp_path / "native_bl_transaction_receipt.json").read_text()
    )
    assert receipt["status"] == "refused_rollback"
    assert receipt["rolled_back"] is True
    assert any("candidate_failed" in reason for reason in receipt["reasons"])
    assert not list(tmp_path.glob(".native_bl_stage.*"))
