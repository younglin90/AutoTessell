from __future__ import annotations

from pathlib import Path

from core.analyzer.readers import read_stl
from core.evaluator.native_authority_transaction_gate import canonical_sha256
from core.evaluator.native_checker import NativeMeshChecker
from core.evaluator.native_tet_cube_authority import validate_cube_authority_ledger
from core.evaluator.native_tet_quality_witness import build_native_tet_quality_witness
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.staged_runner import run_tet_in_private_stage


def test_actual_cube_readback_records_immutable_tet_witness(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    mesh = read_stl(Path("tests/benchmarks/cube.stl"))
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("old", encoding="utf-8")
    observed: dict[str, object] = {}

    def full_audit(stage: Path) -> dict[str, object]:
        strict = audit_strict_volume_topology(stage)
        checker = NativeMeshChecker().run(stage)
        ledger = validate_cube_authority_ledger()
        witness = build_native_tet_quality_witness(
            stage, source_ledger_digest=canonical_sha256(ledger)
        )
        observed["witness"] = witness.as_dict()
        return {
            "valid": bool(strict.valid and ledger["accepted"] and witness.valid),
            "strict": strict.as_dict(),
            "quality": {
                "non_orthogonality_max": checker.max_non_orthogonality,
                "skewness_max": checker.max_skewness,
                "aspect_ratio_max": checker.max_aspect_ratio,
            },
            "witness": witness.as_dict(),
        }

    result = run_tet_in_private_stage(
        generate_native_tet,
        mesh.vertices,
        mesh.faces,
        destination,
        audit_callback=full_audit,
        seed_density=4,
        sliver_quality_threshold=0.0,
        enable_phase_a=False,
        recovery_iterations=0,
        smooth_iterations=0,
    )
    assert result.published
    witness = observed["witness"]
    assert isinstance(witness, dict)
    assert witness["status"] == "measured"
    assert witness["valid"] is True
    assert witness["n_cells"] == 17
    assert witness["worst_non_orthogonality_face"] is not None
    assert witness["worst_skewness_face"] is not None
    assert witness["worst_aspect_ratio_cell"] is not None
    assert witness["p95_non_orthogonality"] <= witness["max_non_orthogonality"]
    assert witness["p95_skewness"] <= witness["max_skewness"]
    assert witness["p95_aspect_ratio"] <= witness["max_aspect_ratio"]
    assert witness["source_ledger_digest"]
