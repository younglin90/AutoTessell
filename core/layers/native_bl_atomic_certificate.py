"""Runtime-disconnected atomic acceptance certificates for boundary layers.

This module deliberately does not create boundary-layer geometry.  It accepts
or rejects already-built, JSON-serializable candidates without mutating the
immutable source.  A later runtime card may adapt its artifacts to these
small, deterministic value objects.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal, Mapping, MutableMapping, Sequence


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
ProductType = Literal["pure_tet", "mixed_prism_shell"]
CandidateKind = Literal["volume", "surface"]


class AtomicCertificateError(ValueError):
    """Raised when an artifact cannot be represented deterministically."""


def canonical_bytes(value: Any) -> bytes:
    """Encode a JSON artifact deterministically and reject non-finite values."""
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AtomicCertificateError("artifact must be finite JSON data") from exc


def sha256(value: Any) -> str:
    """Return the SHA-256 of the API's canonical serialized form."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class SourceAuthority:
    """Immutable source identity and the wall entities that may be layered."""

    topology: str
    source: str
    feature: str
    patch: str
    physical_group: str
    provenance: str
    wall_faces: tuple[str, ...] = ()
    wall_edges: tuple[str, ...] = ()
    ambiguous: bool = False
    already_layered: bool = False


@dataclass(frozen=True)
class TopologyChecks:
    """Hard topology failures, all of which must be exactly zero."""

    invalid: int = 0
    inverted: int = 0
    duplicate: int = 0
    non_manifold: int = 0
    self_intersecting: int = 0

    def failures(self) -> tuple[str, ...]:
        values = asdict(self)
        return tuple(name for name, count in values.items() if not isinstance(count, int) or count != 0)


@dataclass(frozen=True)
class GeneratedEntities:
    """Candidate-generated identifiers, separate from source wall identifiers."""

    vertices: tuple[str, ...] = ()
    faces: tuple[str, ...] = ()
    cells: tuple[str, ...] = ()
    cell_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class VolumeLineage:
    """Required provenance link for one volume wall-face layer."""

    source_wall_face: str
    layer: int
    generated_vertices: tuple[str, ...]
    generated_faces: tuple[str, ...]
    generated_cells: tuple[str, ...]


@dataclass(frozen=True)
class SurfaceLineage:
    """Required provenance link for one surface wall-edge layer."""

    source_wall_edge: str
    layer: int
    generated_vertices: tuple[str, ...]
    generated_faces: tuple[str, ...]




@dataclass(frozen=True)
class SharedSurfaceLineage:
    """Provenance link for a wall-edge strip with shared generated vertices."""

    source_wall_edge: str
    layer: int
    generated_vertices: tuple[str, ...]
    generated_face: str
@dataclass(frozen=True)
class QualityTuple:
    """Quality evidence. Count error is intentionally last and report-only."""

    min_jacobian: float | None = None
    min_area: float | None = None
    min_volume: float | None = None
    max_non_orthogonality: float | None = None
    max_skewness: float | None = None
    min_face_weight: float | None = None
    metric_distortion: float | None = None
    metric_aspect_ratio: float | None = None
    count_error: int = 0

    def gate_tuple(self) -> tuple[float | None, ...]:
        """Stable order: all quality values precede report-only count error."""
        return (
            self.min_jacobian,
            self.min_area,
            self.min_volume,
            self.max_non_orthogonality,
            self.max_skewness,
            self.min_face_weight,
            self.metric_distortion,
            self.metric_aspect_ratio,
            self.count_error,
        )


@dataclass(frozen=True)
class BLCandidate:
    """A candidate snapshot; this module neither derives nor edits it."""

    kind: CandidateKind
    requested_layers: int
    actual_layers: int
    first_height: float
    growth_ratio: float
    product_type: ProductType | str
    authority: SourceAuthority
    topology: TopologyChecks
    generated: GeneratedEntities
    output: Mapping[str, JsonValue]
    quality: QualityTuple = QualityTuple()
    volume_lineage: tuple[VolumeLineage, ...] = ()
    surface_lineage: tuple[SurfaceLineage, ...] = ()
    shared_surface_lineage: tuple[SharedSurfaceLineage, ...] = ()


@dataclass(frozen=True)
class AtomicCertificate:
    """Serializable result of a one-sided acceptance decision."""

    accepted: bool
    reasons: tuple[str, ...]
    source_sha256: str
    candidate_sha256: str
    output_sha256: str | None
    requested_layers: int
    actual_layers: int
    product_type: str
    quality_tuple: tuple[float | None, ...]
    rolled_back: bool = False

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "source_sha256": self.source_sha256,
            "candidate_sha256": self.candidate_sha256,
            "output_sha256": self.output_sha256,
            "requested_layers": self.requested_layers,
            "actual_layers": self.actual_layers,
            "product_type": self.product_type,
            "quality_tuple": list(self.quality_tuple),
            "rolled_back": self.rolled_back,
        }

    def serialized(self) -> bytes:
        return canonical_bytes(self.as_dict())


def _candidate_snapshot(candidate: BLCandidate) -> dict[str, JsonValue]:
    """Produce the deterministic pre-decision candidate representation."""
    return {
        "kind": candidate.kind,
        "requested_layers": candidate.requested_layers,
        "actual_layers": candidate.actual_layers,
        "first_height": candidate.first_height,
        "growth_ratio": candidate.growth_ratio,
        "product_type": candidate.product_type,
        "authority": asdict(candidate.authority),
        "topology": asdict(candidate.topology),
        "generated": asdict(candidate.generated),
        "output": candidate.output,
        "quality": asdict(candidate.quality),
        "volume_lineage": [asdict(item) for item in candidate.volume_lineage],
        "shared_surface_lineage": [asdict(item) for item in candidate.shared_surface_lineage],
        "surface_lineage": [asdict(item) for item in candidate.surface_lineage],
    }


def _same_authority(source: SourceAuthority, candidate: SourceAuthority) -> bool:
    return source == candidate
def _has_exact_shared_generated_lineage(candidate: BLCandidate, source: SourceAuthority) -> bool:
    """Validate a shared surface front without expanding shared vertices."""
    if candidate.surface_lineage or not candidate.shared_surface_lineage or candidate.generated.cells:
        return False
    vertices: list[str] = []
    faces: list[str] = []
    for item in candidate.shared_surface_lineage:
        if item.source_wall_edge not in source.wall_edges or not 1 <= item.layer <= candidate.actual_layers:
            return False
        if not item.generated_vertices or item.generated_face in faces:
            return False
        vertices.extend(item.generated_vertices)
        faces.append(item.generated_face)
    return (
        set(vertices) == set(candidate.generated.vertices)
        and tuple(faces) == candidate.generated.faces
        and len(set(candidate.generated.vertices)) == len(candidate.generated.vertices)
        and len(set(candidate.generated.faces)) == len(candidate.generated.faces)
    )


def _known(values: Sequence[str], allowed: Sequence[str]) -> bool:
    return all(value in allowed for value in values)


def _has_exact_generated_lineage(candidate: BLCandidate, source: SourceAuthority) -> bool:
    generated = candidate.generated
    if candidate.kind == "volume":
        if candidate.surface_lineage or not candidate.volume_lineage:
            return False
        vertices: list[str] = []
        faces: list[str] = []
        cells: list[str] = []
        for item in candidate.volume_lineage:
            if item.source_wall_face not in source.wall_faces or not 1 <= item.layer <= candidate.actual_layers:
                return False
            vertices.extend(item.generated_vertices)
            faces.extend(item.generated_faces)
            cells.extend(item.generated_cells)
        return (
            tuple(vertices) == generated.vertices
            and tuple(faces) == generated.faces
            and tuple(cells) == generated.cells
            and len(set(vertices)) == len(vertices)
            and len(set(faces)) == len(faces)
            and len(set(cells)) == len(cells)
        )
    if candidate.volume_lineage or generated.cells:
        return False
    if candidate.shared_surface_lineage:
        return _has_exact_shared_generated_lineage(candidate, source)
    if not candidate.surface_lineage:
        return False
    vertices = []
    faces = []
    for item in candidate.surface_lineage:
        if item.source_wall_edge not in source.wall_edges or not 1 <= item.layer <= candidate.actual_layers:
            return False
        vertices.extend(item.generated_vertices)
        faces.extend(item.generated_faces)
    return (
        tuple(vertices) == generated.vertices
        and tuple(faces) == generated.faces
        and len(set(vertices)) == len(vertices)
        and len(set(faces)) == len(faces)
    )


def _positive_supplied_quality(quality: QualityTuple) -> tuple[str, ...]:
    reasons: list[str] = []
    for name in ("min_jacobian", "min_area", "min_volume"):
        value = getattr(quality, name)
        if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.0):
            reasons.append(f"non_positive_{name}")
    return tuple(reasons)


def certify(source_output: Mapping[str, JsonValue], source: SourceAuthority, candidate: BLCandidate) -> AtomicCertificate:
    """Validate one candidate without mutating source output or candidate data."""
    source_bytes = canonical_bytes(source_output)
    candidate_bytes = canonical_bytes(_candidate_snapshot(candidate))
    reasons: list[str] = []

    if candidate.kind not in {"volume", "surface"}:
        reasons.append("invalid_candidate_kind")
    if not _same_authority(source, candidate.authority):
        reasons.append("source_authority_mismatch")
    topology_failures = candidate.topology.failures()
    if topology_failures:
        reasons.extend(f"topology_{name}" for name in topology_failures)
    if candidate.requested_layers < 0 or candidate.actual_layers < 0:
        reasons.append("negative_layer_count")

    zero_layer = candidate.requested_layers == 0
    if zero_layer:
        if candidate.actual_layers != 0:
            reasons.append("layer_count_mismatch")
        if source.ambiguous or source.already_layered:
            reasons.append("zero_layer_ambiguous_or_pre_layered_source")
        if (
            candidate.generated.vertices
            or candidate.generated.faces
            or candidate.generated.cells
            or candidate.generated.cell_types
            or candidate.volume_lineage
            or candidate.surface_lineage
        ):
            reasons.append("zero_layer_generated_entities")
        if canonical_bytes(candidate.output) != source_bytes:
            reasons.append("zero_layer_not_byte_identical")
    else:
        if candidate.requested_layers < 1 or candidate.actual_layers != candidate.requested_layers:
            reasons.append("layer_count_mismatch")
        if not isinstance(candidate.first_height, (int, float)) or not math.isfinite(candidate.first_height) or candidate.first_height <= 0.0:
            reasons.append("invalid_first_height")
        if not isinstance(candidate.growth_ratio, (int, float)) or not math.isfinite(candidate.growth_ratio) or candidate.growth_ratio < 1.0:
            reasons.append("invalid_growth_ratio")
        if not _has_exact_generated_lineage(candidate, source):
            reasons.append("incomplete_or_invalid_lineage")
        if candidate.product_type not in {"pure_tet", "mixed_prism_shell"}:
            reasons.append("missing_or_invalid_product_type")
        elif candidate.kind == "volume":
            if candidate.product_type == "pure_tet" and any(kind != "tet" for kind in candidate.generated.cell_types):
                reasons.append("false_pure_tet_claim")
            if candidate.product_type == "mixed_prism_shell" and "prism" not in candidate.generated.cell_types:
                reasons.append("mixed_prism_shell_without_prism")

    reasons.extend(_positive_supplied_quality(candidate.quality))
    accepted = not reasons
    return AtomicCertificate(
        accepted=accepted,
        reasons=tuple(reasons),
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        output_sha256=sha256(candidate.output) if accepted else None,
        requested_layers=candidate.requested_layers,
        actual_layers=candidate.actual_layers,
        product_type=str(candidate.product_type),
        quality_tuple=candidate.quality.gate_tuple(),
    )


PersistenceHook = Callable[[Mapping[str, JsonValue]], None]


def certify_and_persist(
    source_output: Mapping[str, JsonValue],
    source: SourceAuthority,
    candidate: BLCandidate,
    destination: MutableMapping[str, JsonValue],
    *,
    persist: PersistenceHook | None = None,
) -> AtomicCertificate:
    """Certify then atomically replace ``destination`` from a copied candidate.

    ``persist`` is an injectable durability boundary.  It receives a deep-copied
    staging value; an exception rejects the certificate and restores destination
    byte-for-byte to its prior JSON state.
    """
    certificate = certify(source_output, source, candidate)
    if not certificate.accepted:
        return certificate
    before = copy.deepcopy(dict(destination))
    staged = copy.deepcopy(dict(candidate.output))
    try:
        if persist is not None:
            persist(copy.deepcopy(staged))
        destination.clear()
        destination.update(staged)
    except Exception:
        destination.clear()
        destination.update(before)
        return AtomicCertificate(
            accepted=False,
            reasons=("persistence_failure",),
            source_sha256=certificate.source_sha256,
            candidate_sha256=certificate.candidate_sha256,
            output_sha256=None,
            requested_layers=certificate.requested_layers,
            actual_layers=certificate.actual_layers,
            product_type=certificate.product_type,
            quality_tuple=certificate.quality_tuple,
            rolled_back=True,
        )
    return certificate
