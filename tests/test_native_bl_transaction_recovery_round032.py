from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

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
    poly = case_dir / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        digest.update((poly / name).read_bytes())
    return digest.hexdigest()


@pytest.mark.parametrize(
    ("fail_state", "expect_candidate"),
    (
        ("stage_created", False),
        ("candidate_admitted", False),
        ("backup_renamed", False),
        ("candidate_renamed", False),
        ("directory_fsynced", False),
        ("commit_receipt_published", True),
    ),
)
def test_native_bl_failpoint_recovers_to_one_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_state: str,
    expect_candidate: bool,
) -> None:
    _single_tet(tmp_path)
    baseline = _mesh_digest(tmp_path)
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TX_FAIL_AFTER", fail_state)
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
    assert result.success is False
    assert not (tmp_path / "native_bl_transaction_journal.json").exists()
    assert not list(tmp_path.glob(".native_bl_stage.*"))
    final_digest = _mesh_digest(tmp_path)
    if expect_candidate:
        receipt = json.loads(
            (tmp_path / "native_bl_transaction_receipt.json").read_text()
        )
        assert final_digest != baseline
        assert receipt["candidate_fingerprint"] is not None
    else:
        assert final_digest == baseline
