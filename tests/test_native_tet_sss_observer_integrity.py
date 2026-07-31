"""Regression coverage for report-only SSS pass-0 observer checkpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_tet.mesher import generate_native_tet

_ROOT = Path(__file__).resolve().parents[1]
_MESHER = _ROOT / "core" / "generator" / "native_tet" / "mesher.py"
_SPHERE = _ROOT / "tests" / "benchmarks" / "sphere.stl"
_PRE = "pre_sss_pass0_relocate"
_POST = "post_sss_pass0_relocate_pre_accept"


def test_sss_pass0_observer_source_order() -> None:
    source = _MESHER.read_text(encoding="utf-8")

    pre = source.index(f'stage="{_PRE}"')
    relocate = source.index("new_pts = _envelope_bounded_relocate(", pre)
    post = source.index(f'stage="{_POST}"', relocate)

    assert pre < relocate < post
    assert source.count(f'stage="{_PRE}"') == 1
    assert source.count(f'stage="{_POST}"') == 1


def test_sss_pass0_observer_emits_pre_and_post(tmp_path: Path) -> None:
    mesh = read_stl(_SPHERE)
    stages: list[str] = []

    def observe(checkpoint: Any) -> None:
        stages.append(checkpoint.stage)

    generate_native_tet(
        np.ascontiguousarray(mesh.vertices, dtype=np.float64),
        np.ascontiguousarray(mesh.faces, dtype=np.int64),
        tmp_path / "sphere",
        target_cells=2000,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
        _phase_a_observer=observe,
    )

    assert _PRE in stages
    assert _POST in stages
    assert stages.index(_PRE) < stages.index(_POST)
