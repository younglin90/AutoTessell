"""native_ai — AI-driven volume mesh generation (tet/hex/poly/BL).

native_tet / native_hex / native_poly 와 동일한 인터페이스로 AI 기반
볼륨 mesh 생성 진입점. 현재 (2026-04) production-grade volume AI 라이브러리가
없어 mock fallback (기존 native_* 호출) 으로 시작. ML-based smoothing /
generative model 통합은 단계적 추가.

Research direction:
    - MeshGPT (Siddiqui 2024) / MeshAnything V2 (Chen 2024) — surface only.
    - DeepCAD (CAD reconstruction) — CAD-to-mesh, not direct volume.
    - ML-based tet smoothing (Nature Comp Sci 2023) — quality optim.
    - Diffusion mesh generation (research, no production lib).

API:
    generate_native_ai_volume(V, F, work_dir, mesh_type, quality_level)
        → AIVolumeResult
"""
from __future__ import annotations

from .mesher import (
    generate_native_ai_volume,
    AIVolumeResult,
    AIVolumeConfig,
)
from .ml_tet_smoothing import (
    ml_tet_smoothing_apply,
    MLTetSmoothingResult,
    build_quality_predictor_skeleton,
)
from .ml_bl_collision import (
    predict_bl_collision_distances,
    BLCollisionPredictResult,
    build_collision_predictor_skeleton,
)
from .gpu_envelope import (
    gpu_envelope_check,
    GPUEnvelopeResult,
)
from .diffusion_volume import (
    diffusion_generate_volume,
    DiffusionVolumeResult,
    architecture_sketch as diffusion_architecture_sketch,
)
from .training_data import (
    extract_tet_features,
    extract_features_batch,
    generate_dataset_skeleton,
    generate_dataset_from_meshes,
    TetSample,
    DatasetGenResult,
)

__all__ = [
    "generate_native_ai_volume",
    "AIVolumeResult",
    "AIVolumeConfig",
    "ml_tet_smoothing_apply",
    "MLTetSmoothingResult",
    "build_quality_predictor_skeleton",
    "predict_bl_collision_distances",
    "BLCollisionPredictResult",
    "build_collision_predictor_skeleton",
    "gpu_envelope_check",
    "GPUEnvelopeResult",
    "diffusion_generate_volume",
    "DiffusionVolumeResult",
    "diffusion_architecture_sketch",
    "extract_tet_features",
    "extract_features_batch",
    "generate_dataset_skeleton",
    "generate_dataset_from_meshes",
    "TetSample",
    "DatasetGenResult",
]
