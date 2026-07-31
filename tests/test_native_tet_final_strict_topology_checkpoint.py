"""Diagnostic-only checkpoint trace for the final native-tet writer contract.

This does not alter generator routing or acceptance.  It records the existing
in-memory arrays at the mesher's boundary-audit hooks so a strict-writer
failure can be located before the writer consumes the arrays.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.rescue_gate import audit_tet_boundary

_CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"
_SPHERE = Path(__file__).resolve().parent / "benchmarks" / "sphere.stl"
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


def test_cube_10000_l0_trace_refuses_residual_internal_overlap(tmp_path: Path, monkeypatch) -> None:
    """L0: JJ3 rolls back exactly; a later overlap still fails closed.

    Target tracking is observed only.  This card's acceptance is deterministic
    fail-closed topology detection, not target-band success.
    """
    import core.generator.native_tet.boundary_invariant as boundary_invariant
    import core.generator.native_tet.mesher as native_tet_mesher

    _disable_late_topology_mutators(monkeypatch)
    observed: list[tuple[str, int, int, int, int]] = []
    transaction: dict[str, object] = {}
    original = boundary_invariant.check_boundary_invariant
    original_transaction = native_tet_mesher._commit_sidedness_nonincreasing_candidate

    def _hash(array: np.ndarray) -> str:
        return hashlib.sha256(np.ascontiguousarray(array)).hexdigest()

    def traced_transaction(before_points, before_tets, candidate_points, candidate_tets):
        selected_points, selected_tets, report = original_transaction(
            before_points,
            before_tets,
            candidate_points,
            candidate_tets,
        )
        transaction.update(
            {
                "before_points": _hash(before_points),
                "before_tets": _hash(before_tets),
                "candidate_points": _hash(candidate_points),
                "candidate_tets": _hash(candidate_tets),
                "selected_points": _hash(selected_points),
                "selected_tets": _hash(selected_tets),
                "selected_points_is_before": selected_points is before_points,
                "selected_tets_is_before": selected_tets is before_tets,
                "report": report,
            }
        )
        return selected_points, selected_tets, report

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
                int(audit.n_same_side_internal_faces),
            )
        )
        return original(
            before_points, before_tets, after_points, after_tets, stage, *args, **kwargs
        )

    monkeypatch.setattr(boundary_invariant, "check_boundary_invariant", traced)
    monkeypatch.setattr(
        native_tet_mesher,
        "_commit_sidedness_nonincreasing_candidate",
        traced_transaction,
    )
    mesh = read_stl(_CUBE)
    result = generate_native_tet(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        tmp_path / "cube_10000",
        target_cells=10000,
    )

    final_audit = audit_tet_boundary(result.tet_points, result.tets)
    assert not result.success
    assert result.message == ("native_tet CVT candidate increases strict internal-face debt")
    assert result.n_cells == 5913
    assert not final_audit.valid
    # The returned arrays are exactly the pre-CVT checkpoint.  Later local
    # passes must not get a chance to turn CVT's quality improvement into a
    # different topology result.
    assert final_audit.n_same_side_internal_faces == 4
    assert final_audit.n_ambiguous_internal_faces == 128
    assert final_audit.n_degenerate_tets == 32
    assert final_audit.n_duplicate_tets == 0
    report = transaction["report"]
    assert isinstance(report, dict)
    assert report == {
        "accepted": False,
        "before_same_side_internal_faces": 4,
        "candidate_same_side_internal_faces": 12,
        "before_ambiguous_internal_faces": 128,
        "candidate_ambiguous_internal_faces": 0,
        "exact_rollback": True,
    }
    assert transaction["selected_points_is_before"] is True
    assert transaction["selected_tets_is_before"] is True
    assert transaction["before_points"] == transaction["selected_points"]
    assert transaction["before_tets"] == transaction["selected_tets"]
    assert transaction["candidate_points"] != transaction["before_points"]
    assert transaction["candidate_tets"] == transaction["before_tets"]
    assert not (tmp_path / "cube_10000" / "constant" / "polyMesh").exists()
    assert observed
    assert observed[-1][0] == "post_eee_quality"
    assert all(record[0] != "post_nnn_cvt" for record in observed)
    print("TET_FINAL_STRICT_TOPOLOGY_L0", observed, "final", final_audit)


def test_cube_10000_l1_disabling_degenerate_rewrite_separates_contracts(
    tmp_path: Path, monkeypatch
) -> None:
    """L1: isolate BETA2825 without changing the production implementation.

    The ablation only suppresses the inline degenerate-rewrite candidate in
    this diagnostic process.  It proves the final source-aware certificate
    rejects locally invalid topology before the writer; it is not a proposed
    runtime fallback.
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
    case_dir = tmp_path / "cube_10000_no_degenerate_rewrite"
    result = generate_native_tet(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        case_dir,
        target_cells=10000,
    )

    audit = audit_tet_boundary(result.tet_points, result.tets)
    assert not result.success
    assert result.message == "native_tet source-aware strict topology is invalid"
    assert audit.n_nonmanifold_faces == 0
    assert audit.n_duplicate_tets == 0
    assert audit.n_degenerate_tets > 0
    assert not (case_dir / "constant" / "polyMesh").exists()
    print("TET_FINAL_STRICT_TOPOLOGY_L1", result.n_cells, audit)


@pytest.mark.parametrize("fixture", (_CUBE, _SPHERE))
def test_degenerate_candidate_keeps_immutable_source_certificate(
    fixture: Path,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """L1: Cube and sphere candidate evidence is captured before later passes.

    This is intentionally an observation of the BETA2825 transaction rather
    than a success oracle for the final mesh.  The strict writer may still
    reject later topology debt; this card only proves the candidate cannot
    bypass immutable-source or inversion evidence at its own commit boundary.
    """
    import core.generator.native_tet.mesher as native_tet_mesher

    original = native_tet_mesher._commit_degenerate_removal_source_candidate
    observed: list[dict[str, object]] = []

    def traced_transaction(*args):
        selected_points, selected_tets, report = original(*args)
        observed.append(
            {
                "selected_points_is_candidate": selected_points is args[4],
                "selected_tets_is_candidate": selected_tets is args[5],
                "report": report,
            }
        )
        return selected_points, selected_tets, report

    monkeypatch.setattr(
        native_tet_mesher,
        "_commit_degenerate_removal_source_candidate",
        traced_transaction,
    )
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    monkeypatch.setenv("AUTO_TESSELL_CONVEX_EXTRUSION_RESCUE", "0")
    mesh = read_stl(fixture)
    result = generate_native_tet(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        tmp_path / fixture.stem,
        target_cells=2000,
        # The default Sphere Phase-A path resolves all BETA2825 candidates
        # before this pass.  Zero iterations isolates the existing
        # degenerate-removal transaction without changing production routing.
        smooth_iterations=0 if fixture == _SPHERE else 2,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
    )

    assert result.success is False
    assert len(observed) == 1
    trace = observed[0]
    report = trace["report"]
    assert isinstance(report, dict)
    assert report["accepted"] is True
    assert report["candidate_component_bijective"] is True
    assert report["candidate_source_faces_preserved"] is True
    assert report["candidate_unowned_candidate_faces"] == 0
    assert report["candidate_inverted_tets"] <= report["before_inverted_tets"]
    assert trace["selected_points_is_candidate"] is True
    assert trace["selected_tets_is_candidate"] is True
