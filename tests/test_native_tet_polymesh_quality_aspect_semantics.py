from __future__ import annotations

import sys
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "auto_tessell_core" / "build"))
sys.path.insert(0, str(_ROOT / "tests"))
import native_tet_polymesh_quality as native  # noqa: E402
from test_native_tet_polymesh_quality import _write_cube  # noqa: E402


def test_release_aspect_is_all_vertex_pairs_and_edge_aspect_is_diagnostic(
    tmp_path: Path,
) -> None:
    root = tmp_path / "polyMesh"
    _write_cube(root)

    result = dict(native.audit(str(root)))

    assert result["vertex_pair_aspect_ratio_exact"] == pytest.approx(3.0**0.5)
    assert result["max_aspect_ratio"] == result["vertex_pair_aspect_ratio_exact"]
    assert result["topological_edge_aspect_ratio"] == pytest.approx(1.0)
