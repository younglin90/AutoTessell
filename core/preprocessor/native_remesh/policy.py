"""Deterministic profile policy for native surface-remeshing candidates.

The remeshing engines deliberately do not choose between their own results.  This
module is the small, side-effect-free policy layer used by callers to make that
choice consistently: unsafe surfaces are rejected, a face cap is preferred over
quality, and then the remaining quality/size trade-off is ordered deterministically.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from math import ceil, isfinite


class SurfaceRemeshProfile(StrEnum):
    """User-facing surface remeshing profiles."""

    BUDGET = "budget"
    STANDARD = "standard"
    STRICT = "strict"


@dataclass(frozen=True, slots=True)
class SurfaceRemeshProfileSpec:
    """Profile defaults independent of a particular input surface."""

    minimum_face_ratio: float
    target_face_ratio: float
    minimum_triangle_quality: float


_PROFILE_SPECS: dict[SurfaceRemeshProfile, SurfaceRemeshProfileSpec] = {
    SurfaceRemeshProfile.BUDGET: SurfaceRemeshProfileSpec(0.35, 0.60, 0.20),
    SurfaceRemeshProfile.STANDARD: SurfaceRemeshProfileSpec(0.60, 1.00, 0.35),
    SurfaceRemeshProfile.STRICT: SurfaceRemeshProfileSpec(0.85, 1.40, 0.50),
}


@dataclass(frozen=True, slots=True)
class RecommendedFaceCounts:
    """Profile guidance clamped to an explicit hard face cap."""

    minimum: int
    target: int
    cap: int


@dataclass(frozen=True, slots=True)
class SurfaceRemeshPolicy:
    """Acceptance limits for one surface-remesh run.

    ``face_cap`` is a hard resource limit in ranking.  ``max_geometry_drift`` is
    optional because some engine paths do not calculate a projection drift.
    """

    profile: SurfaceRemeshProfile
    face_cap: int
    minimum_triangle_quality: float
    max_geometry_drift: float | None = None
    require_watertight: bool = True
    require_manifold: bool = True

    def __post_init__(self) -> None:
        if self.face_cap < 1:
            raise ValueError("face_cap must be at least 1")
        if not 0.0 <= self.minimum_triangle_quality <= 1.0:
            raise ValueError("minimum_triangle_quality must be in [0, 1]")
        if self.max_geometry_drift is not None and (
            not isfinite(self.max_geometry_drift) or self.max_geometry_drift < 0.0
        ):
            raise ValueError("max_geometry_drift must be finite and non-negative")

    def recommended_faces(self, input_faces: int) -> RecommendedFaceCounts:
        """Return profile min/target counts, never exceeding ``face_cap``."""
        if input_faces < 1:
            raise ValueError("input_faces must be at least 1")
        spec = _PROFILE_SPECS[self.profile]
        minimum = min(self.face_cap, max(1, ceil(input_faces * spec.minimum_face_ratio)))
        target = min(self.face_cap, max(minimum, ceil(input_faces * spec.target_face_ratio)))
        return RecommendedFaceCounts(minimum=minimum, target=target, cap=self.face_cap)


@dataclass(frozen=True, slots=True)
class SurfaceRemeshCandidate:
    """Measured surface-remesh output used solely for policy selection."""

    name: str
    faces: int
    min_triangle_quality: float
    watertight: bool
    manifold: bool
    degenerate_faces: int = 0
    flipped_faces: int = 0
    max_geometry_drift: float | None = None


@dataclass(frozen=True, slots=True)
class SurfaceRemeshDecision:
    """Candidate evaluation plus rank-ready, machine-readable shortfalls."""

    candidate: SurfaceRemeshCandidate
    safety_eligible: bool
    cap_eligible: bool
    eligible: bool
    quality_shortfall: float
    face_cap_excess: int
    recommended_min_shortfall: int
    reasons: tuple[str, ...]

    @property
    def rank_key(self) -> tuple[int, int, int, float, int, str]:
        """Stable lexicographic order: safety, cap, cap excess, quality, then face cost."""
        return (
            0 if self.safety_eligible else 1,
            0 if self.cap_eligible else 1,
            self.face_cap_excess,
            self.quality_shortfall,
            self.candidate.faces if self.candidate.faces >= 0 else 2**63 - 1,
            self.candidate.name,
        )


def surface_remesh_policy(
    profile: SurfaceRemeshProfile | str,
    *,
    face_cap: int,
    minimum_triangle_quality: float | None = None,
    max_geometry_drift: float | None = None,
    require_watertight: bool = True,
    require_manifold: bool = True,
) -> SurfaceRemeshPolicy:
    """Build a policy, using the profile's quality default unless overridden."""
    selected = SurfaceRemeshProfile(profile)
    quality = _PROFILE_SPECS[selected].minimum_triangle_quality
    return SurfaceRemeshPolicy(
        profile=selected,
        face_cap=face_cap,
        minimum_triangle_quality=quality
        if minimum_triangle_quality is None
        else minimum_triangle_quality,
        max_geometry_drift=max_geometry_drift,
        require_watertight=require_watertight,
        require_manifold=require_manifold,
    )


def evaluate_surface_remesh_candidate(
    candidate: SurfaceRemeshCandidate,
    policy: SurfaceRemeshPolicy,
    *,
    input_faces: int,
) -> SurfaceRemeshDecision:
    """Evaluate one candidate without mutating it or invoking a remesher."""
    recommendations = policy.recommended_faces(input_faces)
    reasons: list[str] = []
    quality = candidate.min_triangle_quality
    faces = candidate.faces
    if faces < 1:
        reasons.append("no_faces")
    if candidate.degenerate_faces < 0 or candidate.flipped_faces < 0:
        reasons.append("invalid_diagnostics")
    if candidate.degenerate_faces > 0:
        reasons.append("degenerate_faces")
    if candidate.flipped_faces > 0:
        reasons.append("flipped_faces")
    if policy.require_watertight and not candidate.watertight:
        reasons.append("not_watertight")
    if policy.require_manifold and not candidate.manifold:
        reasons.append("not_manifold")
    if not isfinite(quality) or not 0.0 <= quality <= 1.0:
        reasons.append("invalid_triangle_quality")
    drift = candidate.max_geometry_drift
    if drift is not None and (not isfinite(drift) or drift < 0.0):
        reasons.append("invalid_geometry_drift")
    if policy.max_geometry_drift is not None:
        if drift is None:
            reasons.append("missing_geometry_drift")
        elif drift > policy.max_geometry_drift:
            reasons.append("geometry_drift_exceeded")

    safety_eligible = not reasons
    cap_eligible = faces <= policy.face_cap
    if not cap_eligible:
        reasons.append("face_cap_exceeded")
    quality_shortfall = (
        max(0.0, policy.minimum_triangle_quality - quality) if isfinite(quality) else float("inf")
    )
    return SurfaceRemeshDecision(
        candidate=candidate,
        safety_eligible=safety_eligible,
        cap_eligible=cap_eligible,
        eligible=safety_eligible and cap_eligible,
        quality_shortfall=quality_shortfall,
        face_cap_excess=max(0, faces - policy.face_cap),
        recommended_min_shortfall=max(0, recommendations.minimum - max(0, faces)),
        reasons=tuple(reasons),
    )


def rank_surface_remesh_candidates(
    candidates: Iterable[SurfaceRemeshCandidate],
    policy: SurfaceRemeshPolicy,
    *,
    input_faces: int,
) -> tuple[SurfaceRemeshDecision, ...]:
    """Return the deterministic cap-first order of all measured candidates.

    An eligible candidate always sorts before an unsafe result.  Among safe
    candidates every cap-compliant result sorts before every cap violation;
    quality shortfall and then face count resolve the remaining trade-off.
    """
    decisions = [
        evaluate_surface_remesh_candidate(candidate, policy, input_faces=input_faces)
        for candidate in candidates
    ]
    return tuple(sorted(decisions, key=lambda decision: decision.rank_key))


__all__ = [
    "RecommendedFaceCounts",
    "SurfaceRemeshCandidate",
    "SurfaceRemeshDecision",
    "SurfaceRemeshPolicy",
    "SurfaceRemeshProfile",
    "SurfaceRemeshProfileSpec",
    "evaluate_surface_remesh_candidate",
    "rank_surface_remesh_candidates",
    "surface_remesh_policy",
]
