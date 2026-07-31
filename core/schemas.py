"""Auto-Tessell 에이전트 간 통신 Pydantic 스키마."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 공통 타입
# ---------------------------------------------------------------------------


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Verdict(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"


class QualityLevel(StrEnum):
    DRAFT = "draft"
    STANDARD = "standard"
    FINE = "fine"


class SurfaceQualityLevel(StrEnum):
    L1_REPAIR = "l1_repair"
    L2_REMESH = "l2_remesh"
    L3_AI = "l3_ai"


class MeshType(StrEnum):
    """사용자가 1차로 선택하는 볼륨 메쉬 대분류.

    - AUTO: Strategist 가 geometry/quality 기반 자동 선택 (기본값, 하위호환용)
    - TET: 순수 tetrahedral. 복잡 형상 강건.
    - HEX_DOMINANT: 대부분 hex, 코너/곡면만 poly. CFD BL 품질 우수.
    - POLY: Voronoi dual 기반 polyhedral. 셀 수 최소, gradient 해소 우수.
    """

    AUTO = "auto"
    TET = "tet"
    HEX_DOMINANT = "hex_dominant"
    POLY = "poly"


class UserDecision(StrEnum):
    """Evaluator FAIL 시 사용자가 선택한 다음 행동."""

    RETRY = "retry"
    ACCEPT = "accept"


class AutoRetryMode(StrEnum):
    """Generator ⇄ Evaluator 자동 재시도 모드.

    - OFF   (기본): 1 회 시도 후 FAIL 이어도 루프 없이 종료, recommendation 만 리포트.
    - ONCE: FAIL 시 1 회만 재시도 (max_iterations=2 와 등가).
    - CONTINUE: 예전 max_iterations 기반 루프 동작 (하위호환).
    """

    OFF = "off"
    ONCE = "once"
    CONTINUE = "continue"


# ---------------------------------------------------------------------------
# GeometryReport  (agents/specs/analyzer.md)
# ---------------------------------------------------------------------------


class BoundingBox(BaseModel):
    min: list[float] = Field(..., min_length=3, max_length=3)
    max: list[float] = Field(..., min_length=3, max_length=3)
    center: list[float] = Field(..., min_length=3, max_length=3)
    diagonal: float
    characteristic_length: float


class SurfaceStats(BaseModel):
    num_vertices: int
    num_faces: int
    surface_area: float
    is_watertight: bool
    is_manifold: bool
    num_connected_components: int
    euler_number: int
    genus: int
    has_degenerate_faces: bool
    num_degenerate_faces: int
    min_face_area: float
    max_face_area: float
    face_area_std: float
    min_edge_length: float
    max_edge_length: float
    edge_length_ratio: float


class FeatureStats(BaseModel):
    has_sharp_edges: bool
    num_sharp_edges: int
    sharp_edge_angle_threshold: float = 30.0
    has_thin_walls: bool
    min_wall_thickness_estimate: float
    has_small_features: bool
    smallest_feature_size: float
    feature_to_bbox_ratio: float
    curvature_max: float
    curvature_mean: float


class Geometry(BaseModel):
    bounding_box: BoundingBox
    surface: SurfaceStats
    features: FeatureStats


class FileInfo(BaseModel):
    path: str
    format: str
    file_size_bytes: int
    detected_encoding: str
    is_cad_brep: bool
    is_surface_mesh: bool
    is_volume_mesh: bool


class FlowEstimation(BaseModel):
    type: str  # "external" | "internal" | "unknown"
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    alternatives: list[str] = Field(default_factory=list)


class Issue(BaseModel):
    severity: Severity
    type: str
    count: int
    description: str
    recommended_action: str


class TierCompatibility(BaseModel):
    compatible: bool
    notes: str


class TierCompatibilityMap(BaseModel):
    tier0_core: TierCompatibility
    tier05_netgen: TierCompatibility
    tier1_snappy: TierCompatibility
    tier15_cfmesh: TierCompatibility
    tier2_tetwild: TierCompatibility


class GeometryReport(BaseModel):
    file_info: FileInfo
    geometry: Geometry
    flow_estimation: FlowEstimation
    issues: list[Issue] = Field(default_factory=list)
    tier_compatibility: TierCompatibilityMap


# ---------------------------------------------------------------------------
# PreprocessedReport  (agents/specs/preprocessor.md)
# ---------------------------------------------------------------------------


class PreprocessStep(BaseModel):
    step: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    input_faces: int | None = None
    output_faces: int | None = None
    time_seconds: float
    gate_passed: bool | None = None


class FinalValidation(BaseModel):
    is_watertight: bool
    is_manifold: bool
    num_faces: int
    num_connected_components: int | None = None
    min_face_area: float
    max_edge_length_ratio: float


class PreprocessingSummary(BaseModel):
    input_file: str
    input_format: str
    output_file: str
    passthrough_cad: bool
    total_time_seconds: float
    steps_performed: list[PreprocessStep] = Field(default_factory=list)
    final_validation: FinalValidation
    surface_quality_level: str | None = None


class PreprocessedReport(BaseModel):
    preprocessing_summary: PreprocessingSummary
    surface_quality_level: str | None = None


# ---------------------------------------------------------------------------
# MeshStrategy  (agents/specs/strategist.md)
# ---------------------------------------------------------------------------


class DomainConfig(BaseModel):
    type: str = "box"
    min: list[float] = Field(..., min_length=3, max_length=3)
    max: list[float] = Field(..., min_length=3, max_length=3)
    base_cell_size: float
    location_in_mesh: list[float] = Field(..., min_length=3, max_length=3)


class SurfaceMeshConfig(BaseModel):
    input_file: str
    target_cell_size: float
    min_cell_size: float
    feature_angle: float = 150.0
    feature_extract_level: int = 1


class BoundaryLayerConfig(BaseModel):
    enabled: bool
    num_layers: int
    first_layer_thickness: float
    growth_ratio: float
    max_total_thickness: float
    min_thickness_ratio: float
    feature_angle: float = 130.0


class RefinementRegion(BaseModel):
    type: str  # "surface" | "box"
    name: str
    level: int | list[int]
    cell_size: float
    bounds: dict[str, list[float]] | None = None


class QualityTargets(BaseModel):
    max_non_orthogonality: float = 70.0
    max_skewness: float = 6.0
    max_aspect_ratio: float = 200.0
    min_determinant: float = 0.001
    target_y_plus: float | None = None


class PreviousAttempt(BaseModel):
    tier: str
    quality_level: str = ""
    failure_reason: str
    evaluator_recommendation: str
    modifications: list[str] = Field(default_factory=list)


class MeshStrategy(BaseModel):
    strategy_version: int = 3
    iteration: int = 1
    quality_level: QualityLevel = QualityLevel.STANDARD
    mesh_type: MeshType = MeshType.AUTO
    surface_quality_level: SurfaceQualityLevel = SurfaceQualityLevel.L1_REPAIR
    selected_tier: str
    fallback_tiers: list[str] = Field(default_factory=list)
    strict_tier: bool = False
    flow_type: str  # "external" | "internal"
    domain: DomainConfig
    surface_mesh: SurfaceMeshConfig
    boundary_layers: BoundaryLayerConfig
    refinement_regions: list[RefinementRegion] = Field(default_factory=list)
    quality_targets: QualityTargets = Field(default_factory=QualityTargets)
    tier_specific_params: dict[str, Any] = Field(default_factory=dict)
    previous_attempt: PreviousAttempt | None = None


# ---------------------------------------------------------------------------
# GeneratorLog  (agents/specs/generator.md)
# ---------------------------------------------------------------------------


class GeneratorStep(BaseModel):
    name: str
    status: str  # "success" | "failed"
    time: float


class BoundaryPatch(BaseModel):
    name: str
    type: str
    num_faces: int


class MeshStats(BaseModel):
    num_cells: int
    num_points: int
    num_faces: int
    num_internal_faces: int
    num_boundary_patches: int
    boundary_patches: list[BoundaryPatch] = Field(default_factory=list)


class TierAttempt(BaseModel):
    tier: str
    status: str  # "success" | "failed"
    time_seconds: float
    steps: list[GeneratorStep] = Field(default_factory=list)
    mesh_stats: MeshStats | None = None
    error_message: str | None = None
    # Native tier wrappers annotate the route actually dispatched by the
    # wrapper.  These remain optional for legacy and external tiers.
    route: str | None = None
    contract: str | None = None
    contract_details: dict[str, Any] = Field(default_factory=dict)
    fallback_reason: str | None = None
    native_bl_phase2: "NativeBLPhase2Stats | None" = None  # beta76
    # C-GUI-3 / beta2413 — mesh_integrity_suspect (3-engine catastrophic flag).
    mesh_integrity_suspect: bool = False


class ExecutionSummary(BaseModel):
    selected_tier: str
    tiers_attempted: list[TierAttempt] = Field(default_factory=list)
    output_dir: str
    total_time_seconds: float
    quality_level: str | None = None
    # C-GUI-3 / beta2413 — mesh_integrity_suspect (3-engine catastrophic flag).
    # native engine 의 NativeTetResult / NativeHexResult / NativePolyResult 의
    # mesh_integrity_suspect 를 pipeline result 까지 propagate.
    mesh_integrity_suspect: bool = False


class GeneratorLog(BaseModel):
    execution_summary: ExecutionSummary


# ---------------------------------------------------------------------------
# QualityReport  (agents/specs/evaluator.md)
# ---------------------------------------------------------------------------


class CheckMeshResult(BaseModel):
    cells: int
    faces: int
    points: int
    max_non_orthogonality: float
    avg_non_orthogonality: float
    max_skewness: float
    max_aspect_ratio: float
    min_face_area: float
    min_cell_volume: float
    min_determinant: float
    negative_volumes: int
    severely_non_ortho_faces: int
    failed_checks: int
    mesh_ok: bool
    # OpenFOAM checkMesh-style supplementary quality fields.  Defaults keep
    # older tests/fixtures valid; NativeMeshChecker populates them for real
    # polyMesh evaluations.
    max_boundary_skewness: float | None = None
    max_internal_skewness: float | None = None
    max_concavity: float | None = None
    min_face_weight: float | None = None
    min_vol_ratio: float | None = None
    max_adjacent_volume_ratio: float | None = None
    max_face_warpage: float | None = None
    max_cell_size_growth_ratio: float | None = None
    # Native-poly Phase 0 calibration metrics.  These are report-only and do
    # not participate in evaluator gate decisions.
    max_face_planar_deviation: float | None = None
    mean_face_planar_deviation: float | None = None
    p95_face_planar_deviation: float | None = None
    max_face_normal_spread_deg: float | None = None
    mean_face_normal_spread_deg: float | None = None
    p95_face_normal_spread_deg: float | None = None
    max_juretic_psi: float | None = None
    mean_juretic_psi: float | None = None
    p95_juretic_psi: float | None = None
    skewness_formula_audit: str | None = None
    juretic_psi_definition: str | None = None
    min_cell_h: float | None = None
    mean_cell_h: float | None = None
    p95_cell_h: float | None = None
    max_cell_h: float | None = None
    min_circle_ratio: float | None = None
    mean_circle_ratio: float | None = None
    p95_circle_ratio: float | None = None
    max_circle_ratio: float | None = None
    min_sphericity: float | None = None
    mean_sphericity: float | None = None
    p95_sphericity: float | None = None
    max_sphericity: float | None = None
    min_uniformity_factor: float | None = None
    mean_uniformity_factor: float | None = None
    p95_uniformity_factor: float | None = None
    max_uniformity_factor: float | None = None
    min_face_pairing_residual: float | None = None
    mean_face_pairing_residual: float | None = None
    p95_face_pairing_residual: float | None = None
    max_face_pairing_residual: float | None = None


class CellVolumeStats(BaseModel):
    min: float
    max: float
    mean: float
    std: float
    ratio_max_min: float


class BoundaryLayerStats(BaseModel):
    bl_coverage_percent: float
    avg_first_layer_height: float
    min_first_layer_height: float
    max_first_layer_height: float


class NativeBLPhase2Stats(BaseModel):
    """beta76 — native_bl Phase 2 (beta63-65) 에서 생성된 BL 품질 메트릭."""

    n_prism_cells: int = 0
    n_wall_faces: int = 0
    n_wall_verts: int = 0
    total_thickness: float = 0.0
    n_degenerate_prisms: int = 0
    max_aspect_ratio: float = 0.0
    collision_safety_triggered: bool = False
    collision_scale_factor: float = 1.0
    feature_lock_triggered: bool = False
    n_feature_verts_locked: int = 0
    # C2.3 / C-GUI-4 / beta2414 — Pointwise T-Rex 동등 LCR 통계 (NativeBLResult 와 동일).
    lcr_n_reduced_verts: int = 0
    lcr_max_reduction: int = 0
    lcr_min_layers_used: int = 0
    lcr_n_safe_full_layers: int = 0
    # C3.3 / beta2377 — cfMesh splitInternalLayers diagnostic.
    aniso_split_n_examined: int = 0
    aniso_split_n_would_split: int = 0
    aniso_split_max_aspect_in: float = 0.0


class AdditionalMetrics(BaseModel):
    cell_volume_stats: CellVolumeStats | None = None
    boundary_layer: BoundaryLayerStats | None = None
    native_bl_phase2: NativeBLPhase2Stats | None = None
    max_cell_size_growth_ratio: float | None = None
    max_expansion_ratio: float | None = None


class GeometryFidelity(BaseModel):
    hausdorff_distance: float
    hausdorff_relative: float
    surface_area_deviation_percent: float
    distance_rms: float | None = None
    distance_p95: float | None = None
    distance_p99: float | None = None
    normal_deviation_max_deg: float | None = None
    feature_preservation_score: float | None = None
    # beta2333 — Möller 1997 self-intersect count (P2.6 chain). None = 측정
    # 안 됨 (>5000 face). 0 = clean. >0 = 입력 wall surface 에 SI 존재.
    n_self_intersect_pre: int | None = None


class Gate4SourceIdentity(BaseModel):
    """Exact caller-source snapshot identity for non-promoting Gate-4 evidence."""

    original_path: str
    snapshot_path: str
    byte_count: int
    sha256: str


class Gate4OutputArtifactIdentity(BaseModel):
    """Required OpenFOAM polyMesh artifact identity for Gate-4 evidence."""

    poly_mesh_path: str
    file_sha256: dict[str, str]
    sha256: str


class Gate4SurfaceTopologyEvidence(BaseModel):
    """Fail-closed combinatorial output-surface evidence for Gate 4."""

    status: str
    artifact: Gate4OutputArtifactIdentity | None = None
    topology_valid: bool
    self_intersection_status: str
    boundary_face_count: int | None = None
    component_count: int | None = None
    boundary_loop_count: int | None = None
    euler_characteristic: int | None = None
    genus: int | None = None
    open_edge_count: int | None = None
    nonmanifold_edge_count: int | None = None
    nonmanifold_vertex_count: int | None = None
    duplicate_face_count: int | None = None
    orientation_mismatch_count: int | None = None
    malformed_reason: str | None = None


class Gate4DirectedSurfaceDistanceEvidence(BaseModel):
    """Controlled deterministic samples with exact point-to-triangle queries."""

    rms: float
    p95: float
    p99: float
    maximum: float


class Gate4ActualSurfaceMetricEvidence(BaseModel):
    """Non-promoting actual-surface observations bound to Gate-4 identities."""

    status: str
    sample_count: int
    method: str
    source_to_output: Gate4DirectedSurfaceDistanceEvidence | None = None
    output_to_source: Gate4DirectedSurfaceDistanceEvidence | None = None
    symmetric_sampled_max: float | None = None
    normal_status: str
    normal_p95_deg: float | None = None
    normal_p99_deg: float | None = None
    normal_flipped: int | None = None
    source_sha256: str | None = None
    output_sha256: str | None = None
    source_self_intersection_status: str = "unverified_not_checked"
    output_self_intersection_status: str = "unverified_not_checked"
    signed_status: str = "unverified_not_measured"
    signed_mean_source_to_output: float | None = None
    signed_mean_output_to_source: float | None = None
    integral_status: str = "unverified_not_measured"
    source_signed_volume: float | None = None
    output_signed_volume: float | None = None
    volume_error_pct: float | None = None
    centroid_shift_rel: float | None = None
    available_fields: tuple[str, ...] = ()
    unverified_fields: tuple[str, ...]
    gate4_pass: bool = False


class Gate4MetricCompletenessEvidence(BaseModel):
    """Fail-closed inventory of unavailable Gate-4 metric fields."""

    status: str
    source: Gate4SourceIdentity | None = None
    output: Gate4OutputArtifactIdentity | None = None
    available_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    gate4_pass: bool = False


class Gate4FidelityEvidence(BaseModel):
    """Fail-closed substrate record; it never promotes a Gate verdict."""

    status: str
    source: Gate4SourceIdentity | None = None
    output: Gate4OutputArtifactIdentity | None = None
    metric_status: str
    geometry_fidelity: GeometryFidelity | None = None
    surface_topology: Gate4SurfaceTopologyEvidence | None = None
    actual_surface_metrics: Gate4ActualSurfaceMetricEvidence | None = None
    metric_completeness: Gate4MetricCompletenessEvidence | None = None
    gate4_pass: bool = False


class FailCriterion(BaseModel):
    criterion: str
    value: float
    threshold: float
    location_hint: str = ""


class Recommendation(BaseModel):
    priority: int
    action: str
    current_value: Any
    suggested_value: Any
    rationale: str


class EvaluationSummary(BaseModel):
    verdict: Verdict
    iteration: int
    tier_evaluated: str
    evaluation_time_seconds: float
    checkmesh: CheckMeshResult
    additional_metrics: AdditionalMetrics = Field(default_factory=AdditionalMetrics)
    geometry_fidelity: GeometryFidelity | None = None
    gate4_evidence: Gate4FidelityEvidence | None = None
    hard_fails: list[FailCriterion] = Field(default_factory=list)
    soft_fails: list[FailCriterion] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    quality_level: str | None = None
    mesh_type: str | None = None
    checker_engine_used: str | None = None
    user_decision: UserDecision | None = None
    verdict_reasoning: str = ""
    checkmesh_note: str = (
        "mesh_ok/failed_checks는 OpenFOAM checkMesh raw 출력값. "
        "verdict는 AutoTessell quality_level별 임계값으로 독립 계산됨."
    )


class QualityReport(BaseModel):
    evaluation_summary: EvaluationSummary
