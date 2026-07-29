"""Focused behaviour tests for the deterministic surface-remesh policy."""

from __future__ import annotations

import math

import pytest

from core.preprocessor.native_remesh.policy import (
    SurfaceRemeshCandidate,
    SurfaceRemeshProfile,
    evaluate_surface_remesh_candidate,
    rank_surface_remesh_candidates,
    surface_remesh_policy,
)


def _candidate(
    name: str, *, faces: int = 80, quality: float = 0.8, **kwargs: object
) -> SurfaceRemeshCandidate:
    watertight = bool(kwargs.pop("watertight", True))
    manifold = bool(kwargs.pop("manifold", True))
    return SurfaceRemeshCandidate(
        name=name,
        faces=faces,
        min_triangle_quality=quality,
        watertight=watertight,
        manifold=manifold,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("profile", "minimum", "target"),
    [
        (SurfaceRemeshProfile.BUDGET, 35, 60),
        (SurfaceRemeshProfile.STANDARD, 60, 100),
        (SurfaceRemeshProfile.STRICT, 85, 140),
    ],
)
def test_profiles_supply_deterministic_recommended_face_counts(
    profile: SurfaceRemeshProfile, minimum: int, target: int
) -> None:
    policy = surface_remesh_policy(profile, face_cap=500)

    recommendations = policy.recommended_faces(100)

    assert (recommendations.minimum, recommendations.target, recommendations.cap) == (
        minimum,
        target,
        500,
    )


def test_recommendations_clamp_target_and_minimum_to_hard_cap() -> None:
    recommendations = surface_remesh_policy("strict", face_cap=90).recommended_faces(100)

    assert recommendations.minimum == 85
    assert recommendations.target == 90


def test_safety_gate_rejects_topology_and_geometry_failures() -> None:
    policy = surface_remesh_policy("standard", face_cap=100, max_geometry_drift=0.01)
    decision = evaluate_surface_remesh_candidate(
        _candidate(
            "unsafe",
            watertight=False,
            manifold=False,
            degenerate_faces=1,
            flipped_faces=2,
            max_geometry_drift=0.02,
        ),
        policy,
        input_faces=100,
    )

    assert not decision.safety_eligible
    assert not decision.eligible
    assert decision.reasons == (
        "degenerate_faces",
        "flipped_faces",
        "not_watertight",
        "not_manifold",
        "geometry_drift_exceeded",
    )


def test_ranking_is_safety_then_cap_then_quality_then_face_cost() -> None:
    policy = surface_remesh_policy("standard", face_cap=100)
    ranked = rank_surface_remesh_candidates(
        [
            _candidate("unsafe", faces=10, quality=1.0, watertight=False),
            _candidate("over-cap", faces=101, quality=1.0),
            _candidate("quality-shortfall", faces=10, quality=0.2),
            _candidate("larger-tie", faces=90, quality=0.8),
            _candidate("smaller-tie", faces=80, quality=0.8),
        ],
        policy,
        input_faces=100,
    )

    assert [decision.candidate.name for decision in ranked] == [
        "smaller-tie",
        "larger-tie",
        "quality-shortfall",
        "over-cap",
        "unsafe",
    ]
    assert ranked[2].quality_shortfall == pytest.approx(0.15)
    assert ranked[3].face_cap_excess == 1


def test_invalid_quality_is_an_explicit_safety_failure_and_infinite_shortfall() -> None:
    decision = evaluate_surface_remesh_candidate(
        _candidate("nan-quality", quality=math.nan),
        surface_remesh_policy("budget", face_cap=100),
        input_faces=100,
    )

    assert not decision.safety_eligible
    assert math.isinf(decision.quality_shortfall)
    assert "invalid_triangle_quality" in decision.reasons


def test_policy_validates_its_limits() -> None:
    with pytest.raises(ValueError, match="face_cap"):
        surface_remesh_policy("budget", face_cap=0)
    with pytest.raises(ValueError, match="minimum_triangle_quality"):
        surface_remesh_policy("budget", face_cap=10, minimum_triangle_quality=1.1)
