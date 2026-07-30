"""Diagnostic-only checkpoint trace for the final native-tet writer contract.

This does not alter generator routing or acceptance.  It records the existing
in-memory arrays at the mesher's boundary-audit hooks so a strict-writer
failure can be located before the writer consumes the arrays.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.rescue_gate import audit_tet_boundary

_CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"
_L0_DISABLED = (
    "AUTO_TESSELL_VVV2_QUEUE",
    "AUTO_TESSELL_VVV5B_OFF",
    "AUTO_TESSELL_VVV6_OFF",
    "AUTO_TESSELL_VVV7_OFF",
    "AUTO_TESSELL_VVV8_OFF",
    "AUTO_TESSELL_VVV9_OFF",
    "AUTO_TESSELL_VVV10_OFF",
    "AUTO_TESSELL_VVV11_OFF",
    "AUTO_TESSELL_VVV12_OFF",
    "AUTO_TESSELL_VVV13_OFF",
    "AUTO_TESSELL_VVV14_OFF",
    "AUTO_TESSELL_TET_QUALITY1_OFF",
    "AUTO_TESSELL_STELLAR_KLINGNER",
    "AUTO_TESSELL_P4C_PYTETWILD",
)


def _disable_late_topology_mutators(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_VVV2_QUEUE", "0")
    for name in _L0_DISABLED:
        if name != "AUTO_TESSELL_VVV2_QUEUE":
            monkeypatch.setenv(name, "1" if name.endswith("_OFF") else "0")


def test_cube_10000_l0_trace_records_pre_writer_strict_repair(
    tmp_path: Path, monkeypatch
) -> None:
    """L0: localize the defect and prove exact duplicate repair restores strictness.

    Target tracking is observed only.  This card's acceptance is deterministic
    in-memory topology recovery, not target-band success.
    """
    import core.generator.native_tet.boundary_invariant as boundary_invariant

    _disable_late_topology_mutators(monkeypatch)
    observed: list[tuple[str, int, int, int]] = []
    original = boundary_invariant.check_boundary_invariant

    def traced(before_points, before_tets, after_points, after_tets, stage, *args, **kwargs):
        audit = audit_tet_boundary(
            np.asarray(after_points, dtype=np.float64),
            np.asarray(after_tets, dtype=np.int64),
        )
        observed.append(
            (
                str(stage),
                int(audit.n_nonmanifold_faces),
                int(audit.n_duplicate_tets),
                int(audit.n_degenerate_tets),
            )
        )
        return original(
            before_points, before_tets, after_points, after_tets, stage, *args, **kwargs
        )

    monkeypatch.setattr(boundary_invariant, "check_boundary_invariant", traced)
    mesh = read_stl(_CUBE)
    result = generate_native_tet(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        tmp_path / "cube_10000",
        target_cells=10000,
    )

    final_audit = audit_tet_boundary(result.tet_points, result.tets)
    assert result.success, result.message
    assert result.n_cells > 0
    assert final_audit.valid
    repair = result.debug_info["strict_topology_duplicate_group_repair"]
    assert repair["applied"] is True
    assert repair["n_duplicate_groups"] == 1
    assert repair["n_removed_tets"] == 2
    assert repair["boundary_preserved"] is True
    assert repair["before_nonmanifold_faces"] > 0
    assert repair["after_nonmanifold_faces"] == 0
    assert observed

    first_unsafe = next(
        (
            record
            for record in observed
            if record[1] > 0 or record[2] > 0 or record[3] > 0
        ),
        None,
    )
    assert first_unsafe is not None
    print("TET_FINAL_STRICT_TOPOLOGY_L0", observed, "final", final_audit)


def test_cube_10000_l1_disabling_degenerate_rewrite_separates_contracts(
    tmp_path: Path, monkeypatch
) -> None:
    """L1: isolate BETA2825 without changing the production implementation.

    The ablation only suppresses the inline degenerate-rewrite candidate in
    this diagnostic process.  It proves whether the stage trades strict face
    incidence for validity; it is not a proposed runtime fallback.
    """
    import core.generator.native_tet.klingner_full_sweep as klingner
    import core.generator.native_tet.metric_tensor_sweep as metric
    import core.generator.native_tet.validate as validate

    _disable_late_topology_mutators(monkeypatch)

    def no_degenerate_candidates(_points, tets):
        return np.ones(np.asarray(tets).shape[0], dtype=np.float64)

    monkeypatch.setattr(validate, "signed_volume6", no_degenerate_candidates)

    def identity_topology_pass(points, tets, **_kwargs):
        return points.copy(), tets.copy(), SimpleNamespace(accepted=False)

    monkeypatch.setattr(klingner, "klingner_full_sweep", identity_topology_pass)
    monkeypatch.setattr(metric, "metric_tensor_sweep", identity_topology_pass)
    mesh = read_stl(_CUBE)
    result = generate_native_tet(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        tmp_path / "cube_10000_no_degenerate_rewrite",
        target_cells=10000,
    )

    audit = audit_tet_boundary(result.tet_points, result.tets)
    assert result.success, result.message
    assert audit.n_nonmanifold_faces == 0
    assert audit.n_duplicate_tets == 0
    assert audit.n_degenerate_tets > 0
    print("TET_FINAL_STRICT_TOPOLOGY_L1", result.n_cells, audit)
