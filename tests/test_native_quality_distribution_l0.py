from core.evaluator.quality_distribution import (
    METRIC_VOCABULARY,
    SURFACE_METRIC_STATUS,
)


def test_quality_metric_vocabulary_distinguishes_surface_and_volume_status():
    assert "aspect_ratio" in METRIC_VOCABULARY
    assert "surface_angle_deviation" in METRIC_VOCABULARY
    assert "boundary_non_orthogonality" in METRIC_VOCABULARY
    assert {"measured", "not_measured", "not_applicable", "unverified"} <= SURFACE_METRIC_STATUS
