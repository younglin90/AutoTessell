"""각 tier가 실제로 mesh를 생성하는지 확인하는 스크립트 — 결과만 stdout."""
from __future__ import annotations

import importlib
import os
import sys
import time
import tempfile
import logging
import contextlib
from pathlib import Path
from io import StringIO

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

# structlog/logging 억제
import logging
logging.disable(logging.CRITICAL)

# structlog 억제 시도
try:
    import structlog
    structlog.configure(
        processors=[],
        logger_factory=structlog.PrintLoggerFactory(file=open(os.devnull, "w")),
    )
except Exception:
    pass

from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    QualityLevel,
    QualityTargets,
    SurfaceMeshConfig,
)

SPHERE_STL = Path(__file__).parent / "benchmarks" / "sphere.stl"


def make_strategy(tier_name: str) -> MeshStrategy:
    return MeshStrategy(
        strategy_version=2,
        iteration=1,
        selected_tier=tier_name,
        fallback_tiers=[],
        quality_level=QualityLevel.DRAFT,
        flow_type="external",
        domain=DomainConfig(
            type="box",
            min=[-2.0, -2.0, -2.0],
            max=[2.0, 2.0, 2.0],
            base_cell_size=0.5,
            location_in_mesh=[0.0, 0.0, 0.0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file=str(SPHERE_STL),
            target_cell_size=0.1,
            min_cell_size=0.01,
            feature_angle=150.0,
            feature_extract_level=1,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False,
            num_layers=3,
            first_layer_thickness=0.001,
            growth_ratio=1.2,
            max_total_thickness=0.01,
            min_thickness_ratio=0.1,
            feature_angle=130.0,
        ),
        quality_targets=QualityTargets(
            max_non_orthogonality=65.0,
            max_skewness=4.0,
            max_aspect_ratio=100.0,
            min_determinant=0.001,
        ),
        tier_specific_params={
            # robust_hex: 셀 수 최소화
            "n_cells": 2,
            "octree_max_depth": 2,
            # algohex: 작게
            "hex_scale": 0.5,
        },
    )


TIERS = [
    ("tier2_tetwild",           "core.generator.tier2_tetwild",          "Tier2TetWildGenerator"),
    ("tier05_netgen",           "core.generator.tier05_netgen",          "Tier05NetgenGenerator"),
    ("tier1_snappy",            "core.generator.tier1_snappy",           "Tier1SnappyGenerator"),
    ("tier15_cfmesh",           "core.generator.tier15_cfmesh",          "Tier15CfMeshGenerator"),
    ("tier_meshpy",             "core.generator.tier_meshpy",            "TierMeshPyGenerator"),
    ("tier_wildmesh",           "core.generator.tier_wildmesh",          "TierWildMeshGenerator"),
    ("tier_gmsh_hex",           "core.generator.tier_gmsh_hex",          "TierGmshHexGenerator"),
    ("tier_cinolib_hex",        "core.generator.tier_cinolib_hex",       "TierCinolibHexGenerator"),
    ("tier_voro_poly",          "core.generator.tier_voro_poly",         "TierVoroPolyGenerator"),
    ("tier_mmg3d",              "core.generator.tier_mmg3d",             "TierMMG3DGenerator"),
    ("tier_robust_hex",         "core.generator.tier_robust_hex",        "TierRobustHexGenerator"),
    ("tier_algohex",            "core.generator.tier_algohex",           "TierAlgoHexGenerator"),
    ("tier_jigsaw",             "core.generator.tier_jigsaw",            "TierJigsawGenerator"),
    ("tier_jigsaw_fallback",    "core.generator.tier_jigsaw_fallback",   "TierJigsawFallbackGenerator"),
    ("tier0_core",              "core.generator.tier0_core",             "Tier0CoreGenerator"),
    ("tier_hohqmesh",           "core.generator.tier_hohqmesh",          "TierHOHQMeshGenerator"),
    ("tier_hex_classy_blocks",  "core.generator.tier_hex_classy_blocks", "TierHexClassyBlocksGenerator"),
    ("tier_classy_blocks",      "core.generator.tier_classy_blocks",     "TierClassyBlocksGenerator"),
    ("tier_polyhedral",         "core.generator.polyhedral",             "PolyhedralGenerator"),
    ("tier0_2d_meshpy",         "core.generator.tier0_2d_meshpy",        "Tier2DMeshPyGenerator"),
]


def run_tier(tier_name: str, module_path: str, class_name: str) -> tuple[str, float, str]:
    """Returns (status, elapsed, error_msg)."""
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
    except (ImportError, AttributeError) as e:
        return "import_error", 0.0, str(e)[:150]

    strategy = make_strategy(tier_name)

    with tempfile.TemporaryDirectory() as tmp:
        case_dir = Path(tmp) / "case"
        case_dir.mkdir()

        generator = cls()
        t0 = time.monotonic()
        # stderr 억제
        devnull = open(os.devnull, "w")
        old_stderr = sys.stderr
        sys.stderr = devnull
        try:
            result = generator.run(
                strategy=strategy,
                preprocessed_path=SPHERE_STL,
                case_dir=case_dir,
            )
            elapsed = time.monotonic() - t0
            status = result.status
            err = (result.error_message or "")[:150]
            return status, elapsed, err
        except Exception as e:
            elapsed = time.monotonic() - t0
            return "exception", elapsed, str(e)[:150]
        finally:
            sys.stderr = old_stderr
            devnull.close()


def main() -> None:
    results = []
    total = len(TIERS)

    for i, (tier_name, module_path, class_name) in enumerate(TIERS, 1):
        print(f"[{i:02d}/{total}] Testing {tier_name} ...", flush=True)
        status, elapsed, err = run_tier(tier_name, module_path, class_name)
        results.append((tier_name, status, elapsed, err))
        print(f"       -> {status.upper()} in {elapsed:.1f}s  {err[:80] if err else ''}", flush=True)

    print("\n")
    print("=" * 95)
    print(f"{'Tier':<28} | {'Status':<14} | {'Time':>8} | Note")
    print("=" * 95)
    for tier_name, status, elapsed, err in results:
        icon = "OK " if status == "success" else ("NO_BIN" if "import" in status else "FAIL")
        note = err[:50] if err else ""
        print(f"{tier_name:<28} | {status:<14} | {elapsed:>7.1f}s | {note}")

    print("=" * 95)
    success = [r for r in results if r[1] == "success"]
    failed  = [r for r in results if r[1] != "success"]
    print(f"\nTotal: {len(results)}  |  Success: {len(success)}  |  Failed/Error: {len(failed)}")
    print("\nFailed tiers:")
    for tier_name, status, elapsed, err in failed:
        print(f"  {tier_name:<28}  {status}  {err[:80]}")


if __name__ == "__main__":
    main()
