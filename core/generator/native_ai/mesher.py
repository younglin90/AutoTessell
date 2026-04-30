"""native_ai mesher — AI-assisted volume mesh entry point.

mesh_type 별 dispatch:
    - tet  : ML-smoothing-augmented native_tet
    - hex  : surface AI feature-aware native_hex
    - poly : aniso-CVT (이미 구현, AI tag) native_poly
    - bl   : ML-based prism collision predict + native_bl

현재 (skeleton) — 모든 mesh_type 이 기존 native_* engine 으로 위임.
실제 AI 통합은 단계적 추가.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class AIVolumeConfig:
    """native_ai 설정."""

    # 공통
    mesh_type: Literal["tet", "hex", "poly"] = "tet"
    quality_level: Literal["draft", "standard", "fine"] = "standard"
    seed_density: int = 8
    enable_bl: bool = True
    bl_num_layers: int = 3
    bl_first_thickness: float = 0.0  # 0 = bbox-relative

    # AI-specific (현재 skeleton — 미사용)
    ai_smoothing: bool = False           # ML-based tet smoothing (research)
    ai_surface_repair: bool = False      # MeshGPT/MeshAnything L3 사용
    ai_collision_predict: bool = False   # ML BL collision predict


@dataclass
class AIVolumeResult:
    """native_ai 결과."""

    success: bool
    n_cells: int = 0
    grade: str = "?"
    mesh_type: str = ""
    elapsed: float = 0.0
    message: str = ""
    # 위임된 backend 정보
    backend: str = ""        # "native_tet", "native_hex", etc.
    backend_result: Any = None
    # AI 적용 여부 (skeleton — 현재 모두 False)
    ai_applied: dict[str, bool] = field(default_factory=dict)


def generate_native_ai_volume(
    V: np.ndarray,
    F: np.ndarray,
    work_dir: Path,
    cfg: AIVolumeConfig | None = None,
) -> AIVolumeResult:
    """AI-assisted volume mesh 진입점.

    현재 (skeleton): mesh_type 에 따라 기존 native_* engine 으로 위임.
    AI 통합은 단계적 — 향후 카드:
        AI-V1: ML-based tet smoothing (Klingner §4 swap + ML 결합)
        AI-V2: MeshGPT 기반 surface repair → 후속 native_tet
        AI-V3: ML-based BL collision predict (gap detection)
        AI-V4: Diffusion-based volume generation (research)
    """
    import time

    cfg = cfg or AIVolumeConfig()
    t0 = time.perf_counter()

    log.info(
        "native_ai_dispatch",
        mesh_type=cfg.mesh_type,
        quality_level=cfg.quality_level,
        ai_smoothing=cfg.ai_smoothing,
        ai_surface_repair=cfg.ai_surface_repair,
        ai_collision_predict=cfg.ai_collision_predict,
    )

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    ai_applied = {
        "smoothing": False,
        "surface_repair": False,
        "collision_predict": False,
    }

    # AI-V2 wire: ai_surface_repair=True 시 L3 fallback 자동 시도.
    # GPU 없거나 lib 미설치 시 silently skip (gate_check 가 그대로 통과).
    if cfg.ai_surface_repair:
        try:
            import trimesh as _tm  # noqa: F401
            from core.preprocessor.pipeline import PreprocessPipeline as _PP
            _mesh_in = _tm.Trimesh(vertices=V, faces=F, process=False)
            _pipe = _PP()
            _fixed_mesh, _passed, _rec = _pipe._l3_ai_fix(
                _mesh_in, allow_ai_fallback=True,
            )
            if _passed and _rec is not None and _rec.get("method") in (
                "meshgpt-pytorch", "MeshAnythingV2",
            ):
                V = np.asarray(_fixed_mesh.vertices, dtype=np.float64)
                F = np.asarray(_fixed_mesh.faces, dtype=np.int64)
                ai_applied["surface_repair"] = True
                log.info(
                    "native_ai_surface_repair_applied",
                    method=_rec.get("method"),
                    in_faces=_rec.get("input_faces"),
                    out_faces=_rec.get("output_faces"),
                )
        except Exception as _ai_exc:
            log.warning(
                "native_ai_surface_repair_skipped",
                error=str(_ai_exc)[:120],
            )

    try:
        if cfg.mesh_type == "tet":
            from core.generator.native_tet.mesher import generate_native_tet
            r = generate_native_tet(
                V, F, work_dir,
                seed_density=cfg.seed_density,
                enable_phase_a=True,
                enable_phase_c=True,
                enable_amips_smooth=True,
            )
            n_cells = int(getattr(r, "n_cells", 0) or getattr(r, "n_tets", 0))
            grade = str(getattr(r, "quality_grade", "?"))
            backend = "native_tet"
        elif cfg.mesh_type == "hex":
            from core.generator.native_hex.mesher import generate_native_hex
            r = generate_native_hex(
                V, F, work_dir,
                seed_density=cfg.seed_density * 2,
                snap_boundary=True,
                snap_iterations=2,
            )
            n_cells = int(getattr(r, "n_cells", 0))
            grade = str(getattr(r, "quality_grade", "?"))
            backend = "native_hex"
        elif cfg.mesh_type == "poly":
            from core.generator.native_poly.voronoi import generate_native_poly_voronoi
            r = generate_native_poly_voronoi(
                V, F, work_dir,
                seed_density=cfg.seed_density * 2,
                n_lloyd=2,
                auto_escalate=True,
            )
            n_cells = int(getattr(r, "n_cells", 0))
            grade = str(getattr(r, "quality_grade", "?"))
            backend = "native_poly"
        else:
            return AIVolumeResult(
                success=False,
                message=f"unknown mesh_type: {cfg.mesh_type}",
                elapsed=time.perf_counter() - t0,
            )

        # BL post-step (위임).
        if cfg.enable_bl and getattr(r, "success", False):
            try:
                from core.layers.native_bl import generate_native_bl, BLConfig
                bbox = V.max(axis=0) - V.min(axis=0)
                bbox_diag = float(np.linalg.norm(bbox)) + 1e-30
                ft = (
                    cfg.bl_first_thickness
                    if cfg.bl_first_thickness > 0
                    else 0.001 * bbox_diag
                )
                bl_cfg = BLConfig(
                    num_layers=cfg.bl_num_layers,
                    growth_ratio=1.2,
                    first_thickness=ft,
                    collision_safety=True,
                )
                _ = generate_native_bl(work_dir, bl_cfg, engine_tag=cfg.mesh_type)
            except Exception as bl_exc:
                log.warning("native_ai_bl_failed", error=str(bl_exc)[:120])

        return AIVolumeResult(
            success=bool(getattr(r, "success", False)),
            n_cells=n_cells,
            grade=grade,
            mesh_type=cfg.mesh_type,
            elapsed=time.perf_counter() - t0,
            message=str(getattr(r, "message", "")),
            backend=backend,
            backend_result=r,
            ai_applied=ai_applied,
        )

    except Exception as exc:
        log.error("native_ai_failed", error=str(exc)[:200])
        return AIVolumeResult(
            success=False,
            mesh_type=cfg.mesh_type,
            elapsed=time.perf_counter() - t0,
            message=str(exc)[:200],
            ai_applied=ai_applied,
        )
