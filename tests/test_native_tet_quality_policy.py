from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "auto_tessell_core" / "build"))
sys.path.insert(0, str(_ROOT / "tests"))
import native_tet_polymesh_quality as native  # noqa: E402
from test_native_tet_polymesh_quality import _write_cube  # noqa: E402


def _policy(aspect: float) -> dict[str, object]:
    return {
        "max_non_orthogonality": 50.0,
        "max_skewness": 0.5,
        "max_aspect_ratio": aspect,
        "policy_sha256": "c" * 64,
    }


def test_disk_oracle_applies_user_sealed_quality_policy(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_cube(root)

    passed = dict(native.audit_with_policy(str(root), _policy(2.0)))
    refused = dict(native.audit_with_policy(str(root), _policy(1.5)))

    assert passed["valid"] is True
    assert passed["quality_pass"] is True
    assert passed["quality_policy_sealed"] is True
    assert passed["quality_policy_sha256"] == "c" * 64
    assert refused["valid"] is True
    assert refused["quality_pass"] is False


def test_disk_oracle_rejects_unsealed_or_invalid_policy(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_cube(root)

    result = dict(native.audit_with_policy(str(root), {"max_aspect_ratio": 2.0}))

    assert result["valid"] is False
    assert result["quality_pass"] is False
    assert result["quality_policy_sealed"] is False
    assert result["error"] == "quality_policy_invalid"
