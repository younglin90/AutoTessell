"""Round 031: user-configured Native BL quality limits are admission gates."""
from __future__ import annotations

from pathlib import Path

from core.layers.native_bl import BLConfig, generate_native_bl
from tests.test_native_bl_transaction_round031 import _mesh_digest, _single_tet


def test_min_first_layer_height_limit_refuses_without_publish(tmp_path: Path) -> None:
    _single_tet(tmp_path)
    before = _mesh_digest(tmp_path)

    result = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.02,
            growth_ratio=1.0,
            min_first_layer_height=1.0,
            collision_safety=False,
            feature_lock=False,
            quality_check_enabled=False,
            backup_original=False,
        ),
    )

    assert result.success is False
    assert result.transaction_status == "rolled_back"
    assert "quality_limit_failed:min_first_layer_height" in result.message
    assert _mesh_digest(tmp_path) == before
