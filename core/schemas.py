"""Auto-Tessell 에이전트 간 통신 Pydantic 스키마."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 공통 타입
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Verdict(str, Enum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"


class QualityLevel(str, Enum):
    DRAFT = "draft"
    STANDARD = "standard"
    FINE = "fine"


class SurfaceQualityLevel(str, Enum):
    L1_REPAIR = "l1_repair"
    L2_REMESH = "l2_remesh"
    L3_AI = "l3_ai"


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
    gate_passed: Optional[bool] = None


class FinalValidation(BaseModel):
    is_watertight: bool
    is_manifold: bool
    num_faces: int
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
    surface_quality_level: Optional[str] = None


class PreprocessedReport(BaseModel):
    preprocessing_summary: PreprocessingSummary
    surface_quality_level: Optional[str] = None


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
    target_y_plus: Optional[float] = None


class PreviousAttempt(BaseModel):
    tier: str
    failure_reason: str
    evaluator_recommendation: str


class MeshStrategy(BaseModel):
    strategy_version: int = 2
    iteration: int = 1
    quality_level: QualityLevel = QualityLevel.STANDARD
    surface_quality_level: SurfaceQualityLevel = SurfaceQualityLevel.L1_REPAIR
    selected_tier: str
    fallback_tiers: list[str] = Field(default_factory=list)
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


class ExecutionSummary(BaseModel):
    selected_tier: str
    tiers_attempted: list[TierAttempt] = Field(default_factory=list)
    output_dir: str
    total_time_seconds: float
    quality_level: Optional[str] = None


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


class AdditionalMetrics(BaseModel):
    cell_volume_stats: CellVolumeStats | None = None
    boundary_layer: BoundaryLayerStats | None = None


class GeometryFidelity(BaseModel):
    hausdorff_distance: float
    hausdorff_relative: float
    surface_area_deviation_percent: float


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
    hard_fails: list[FailCriterion] = Field(default_factory=list)
    soft_fails: list[FailCriterion] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    quality_level: Optional[str] = None


class QualityReport(BaseModel):
    evaluation_summary: EvaluationSummary
