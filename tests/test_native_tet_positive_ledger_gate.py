from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.generator.native_tet.staged_runner import (
    run_tet_bl_contract_in_private_stage,
)


def test_positive_contract_rejects_legacy_sidecars_without_writer_ledger(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("baseline", encoding="utf-8")
    authority = {
        "accepted": True,
        "receipt_sealed": True,
        "direct_lineage": True,
        "source_sha256": "a" * 64,
        "wall_edge_eligible": True,
        "source_authority_status": "SOURCE_VERIFIED",
        "provisional": False,
    }

    def run_callback(stage: Path, _authority: dict, _run: int) -> SimpleNamespace:
        for name in ("evidence.atne", "ledger.tsv", "binding.tsv", "layers.tsv"):
            (stage / name).write_text("legacy-sidecar", encoding="utf-8")
        return SimpleNamespace(success=True)

    result = run_tet_bl_contract_in_private_stage(
        destination,
        run_callback=run_callback,
        audit_callback=lambda _stage: {"accepted": True},
        source_authority=authority,
        requested_layers=1,
    )

    assert result.published is False
    assert result.refused_reason == "native_tet_writer_ledger_refused"
    assert (destination / "old").read_text(encoding="utf-8") == "baseline"
