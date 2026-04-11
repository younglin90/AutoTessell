from __future__ import annotations

from scripts.run_mesh_matrix import (
    _extract_error_text,
    _parse_positive_int_map,
    _profile_max_iterations,
    _parse_timeout_map,
    _profile_timeout_floor,
    _resolve_max_iterations,
    _runtime_profile_args,
    _resolve_timeout,
    classify_failure,
)


def test_parse_timeout_map() -> None:
    out = _parse_timeout_map(["draft=30", "snappy=120"])
    assert out["draft"] == 30
    assert out["snappy"] == 120


def test_parse_positive_int_map() -> None:
    out = _parse_positive_int_map(["fine=2", "tetwild=3"])
    assert out["fine"] == 2
    assert out["tetwild"] == 3


def test_resolve_timeout_uses_max_override() -> None:
    sec = _resolve_timeout(
        default_sec=60,
        quality="fine",
        tier="snappy",
        remesh_engine="auto",
        by_quality={"fine": 120},
        by_tier={"snappy": 180},
        by_remesh={},
    )
    assert sec == 180


def test_resolve_max_iterations_uses_max_override() -> None:
    it = _resolve_max_iterations(
        default_iter=1,
        quality="fine",
        tier="tetwild",
        by_quality={"fine": 2},
        by_tier={"tetwild": 3},
    )
    assert it == 3


def test_classify_failure_timeout() -> None:
    assert classify_failure("timeout", "timeout(60s)") == "timeout"


def test_classify_failure_dependency() -> None:
    c = classify_failure("fail", "No module named 'scipy'")
    assert c == "dependency_missing"


def test_classify_failure_openfoam() -> None:
    c = classify_failure("fail", "FOAM FATAL ERROR: cannot find file")
    assert c == "openfoam_failure"


def test_runtime_profile_balanced_no_extra_args() -> None:
    args = _runtime_profile_args(
        profile="balanced",
        quality="draft",
        tier="snappy",
        remesh_engine="auto",
    )
    assert args == []


def test_runtime_profile_fast_adds_tier_specific_args() -> None:
    args = _runtime_profile_args(
        profile="fast",
        quality="fine",
        tier="tetwild",
        remesh_engine="quadwild",
    )
    joined = " ".join(args)
    assert "--element-size 0.08" not in joined
    assert "--remesh-target-faces 3000" in joined
    assert "--base-cell-num 30" in joined
    assert "--element-size 0.06" in joined


def test_runtime_profile_fast_fine_snappy_tuning_args() -> None:
    args = _runtime_profile_args(
        profile="fast",
        quality="fine",
        tier="snappy",
        remesh_engine="auto",
    )
    joined = " ".join(args)
    assert "--snappy-castellated-level 1,2" in joined
    assert "--base-cell-num 16" in joined


def test_profile_timeout_floor_for_fine_fast() -> None:
    assert (
        _profile_timeout_floor(
            profile="fast",
            quality="fine",
            tier="snappy",
            remesh_engine="auto",
        )
        == 90
    )


def test_profile_timeout_floor_balanced_zero() -> None:
    assert (
        _profile_timeout_floor(
            profile="balanced",
            quality="fine",
            tier="snappy",
            remesh_engine="auto",
        )
        == 0
    )


def test_extract_error_text_prefers_final_failure_message() -> None:
    merged = "\n".join(
        [
            "some log",
            "FOAM FATAL ERROR: intermediate",
            "✗ FAIL — Failed after 1 iterations",
        ]
    )
    assert _extract_error_text(merged) == "Failed after 1 iterations"


def test_profile_max_iterations_fast_fine_netgen() -> None:
    assert _profile_max_iterations(profile="fast", quality="fine", tier="netgen") == 2


def test_profile_max_iterations_default_one() -> None:
    assert _profile_max_iterations(profile="balanced", quality="fine", tier="snappy") == 1
