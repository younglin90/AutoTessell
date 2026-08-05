from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.native_bl import BLConfig, generate_native_bl


def test_committed_native_bl_history_contains_all_durable_states(tmp_path: Path) -> None:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
         [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    write_generic_polymesh(
        points,
        [[[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]],
        tmp_path,
        patch_name="wall",
        patch_type="wall",
    )
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
    assert not (tmp_path / "native_bl_transaction_journal.json").exists()
    history = json.loads(
        (tmp_path / "native_bl_transaction_history.json").read_text(encoding="utf-8")
    )
    assert history["history"] == [
        "stage_created",
        "candidate_admitted",
        "backup_renamed",
        "candidate_renamed",
        "directory_fsynced",
        "commit_receipt_published",
        "backup_retired",
    ]
