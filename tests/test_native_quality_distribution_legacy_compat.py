"""QUALITY-DISTRIBUTION-1 must not alter legacy evaluator runtime output."""

from __future__ import annotations

from core.evaluator.native_checker import NativeMeshChecker
from core.evaluator.quality_distribution import QualityDistributionReport, QualitySample


def test_report_only_import_and_build_do_not_change_native_checker_contract() -> None:
    before = NativeMeshChecker._compute_non_orthogonality.__name__
    report = QualityDistributionReport.from_populations(
        face_populations={
            "internal": {
                "non_orthogonality": [
                    QualitySample(
                        entity_id=1,
                        value=0.0,
                        source_entity_id=1,
                        layer="not_applicable",
                        provenance="legacy_compat_fixture",
                    )
                ]
            }
        }
    )

    assert before == NativeMeshChecker._compute_non_orthogonality.__name__
    assert report.to_dict()["schema"] == "QualityDistributionReport"
    assert "quality_distribution" not in NativeMeshChecker.__dict__
