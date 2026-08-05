from __future__ import annotations

from pathlib import Path

from core.analyzer.readers import read_stl
from core.evaluator.native_checker import NativeMeshChecker
from core.evaluator.native_tet_cube_authority import validate_cube_authority_ledger
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.staged_runner import run_tet_in_private_stage


def test_actual_cube_writer_runs_only_in_stage_and_refuses_current_quality(
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
        observed["strict"] = strict.as_dict()
        observed["max_non_orthogonality"] = checker.max_non_orthogonality
        observed["max_skewness"] = checker.max_skewness
        observed["ledger"] = ledger
        quality_pass = (
            checker.max_non_orthogonality <= 35.0
            and checker.max_skewness <= 0.50
        )
        return {
            "valid": bool(strict.valid and ledger["accepted"] and quality_pass),
            "strict": strict.as_dict(),
            "ledger": ledger,
            "quality": {
                "non_orthogonality_max": checker.max_non_orthogonality,
                "skewness_max": checker.max_skewness,
            },
            "reason": "quality_infeasible_fixed_topology",
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
    assert not result.published
    assert result.refused_reason == "quality_infeasible_fixed_topology"
    assert observed["strict"]["valid"] is True
    assert observed["ledger"]["accepted"] is True
    assert (
        observed["max_non_orthogonality"] > 35.0
        or observed["max_skewness"] > 0.50
    )
    assert (destination / "old").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".autotessell-stage-*"))
