"""각 tier가 실제로 mesh를 생성하는지 확인하는 스크립트."""
from __future__ import annotations

import sys
import time
import tempfile
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    ExecutionSummary,
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
            "robust_hex_n_cells": 3,
            "octree_max_depth": 2,
            # algohex: 빠른 테스트용 (큰 tet → 적은 셀 → 빠름)
            "algohex_tet_size": 0.3,
        },
    )


# 테스트할 tier 목록 (클래스 import 경로 포함)
TIERS = [
    ("tier2_tetwild",       "core.generator.tier2_tetwild",       "Tier2TetWildGenerator"),
    ("tier05_netgen",       "core.generator.tier05_netgen",       "Tier05NetgenGenerator"),
    ("tier1_snappy",        "core.generator.tier1_snappy",        "Tier1SnappyGenerator"),
    ("tier15_cfmesh",       "core.generator.tier15_cfmesh",       "Tier15CfMeshGenerator"),
    ("tier_meshpy",         "core.generator.tier_meshpy",         "TierMeshPyGenerator"),
    ("tier_wildmesh",       "core.generator.tier_wildmesh",       "TierWildMeshGenerator"),
    ("tier_gmsh_hex",       "core.generator.tier_gmsh_hex",       "TierGmshHexGenerator"),
    ("tier_cinolib_hex",    "core.generator.tier_cinolib_hex",    "TierCinolibHexGenerator"),
    ("tier_voro_poly",      "core.generator.tier_voro_poly",      "TierVoroPolyGenerator"),
    ("tier_mmg3d",          "core.generator.tier_mmg3d",          "TierMMG3DGenerator"),
    ("tier_robust_hex",     "core.generator.tier_robust_hex",     "TierRobustHexGenerator"),
    ("tier_algohex",        "core.generator.tier_algohex",        "TierAlgoHexGenerator"),
    ("tier_jigsaw",         "core.generator.tier_jigsaw",         "TierJigsawGenerator"),
    ("tier_jigsaw_fallback","core.generator.tier_jigsaw_fallback","TierJigsawFallbackGenerator"),
    ("tier0_core",          "core.generator.tier0_core",          "Tier0CoreGenerator"),
    ("tier_hohqmesh",       "core.generator.tier_hohqmesh",       "TierHOHQMeshGenerator"),
    ("tier_hex_classy_blocks","core.generator.tier_hex_classy_blocks","TierHexClassyBlocksGenerator"),
    ("tier_classy_blocks",  "core.generator.tier_classy_blocks",  "TierClassyBlocksGenerator"),
    ("tier_polyhedral",     "core.generator.polyhedral",          "PolyhedralGenerator"),
    ("tier0_2d_meshpy",     "core.generator.tier0_2d_meshpy",     "Tier2DMeshPyGenerator"),
]

# 타임아웃이 긴 tier
LONG_TIERS = {"tier_robust_hex", "tier_algohex", "tier_mmg3d"}
# 타임아웃 설정 (초)
TIMEOUT_MAP = {
    "tier_robust_hex": 300,
    "tier_algohex": 120,
    "tier_mmg3d": 60,
}
DEFAULT_TIMEOUT = 30


def run_tier(tier_name: str, module_path: str, class_name: str) -> tuple[str, float, str]:
    """
    Returns: (status, elapsed, error_msg)
    status: "success" | "failed" | "import_error" | "timeout" | "exception"
    """
    import importlib
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
    except (ImportError, AttributeError) as e:
        return "import_error", 0.0, str(e)[:120]

    strategy = make_strategy(tier_name)
    timeout_sec = TIMEOUT_MAP.get(tier_name, DEFAULT_TIMEOUT)

    def _run(case_dir: Path) -> tuple[str, str]:
        result = cls().run(
            strategy=strategy,
            preprocessed_path=SPHERE_STL,
            case_dir=case_dir,
        )
        return result.status, (result.error_message or "")

    with tempfile.TemporaryDirectory() as tmp:
        case_dir = Path(tmp) / "case"
        case_dir.mkdir()

        # tier_polyhedral은 기존 polyMesh가 필요 → meshpy로 기반 메쉬 먼저 생성
        if tier_name == "tier_polyhedral":
            try:
                import importlib as _il
                _mod = _il.import_module("core.generator.tier_meshpy")
                _gen = _mod.TierMeshPyGenerator()
                _strat = make_strategy("tier_meshpy")
                _gen.run(strategy=_strat, preprocessed_path=SPHERE_STL, case_dir=case_dir)
            except Exception:
                pass

        t0 = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_run, case_dir)
                status, err = fut.result(timeout=timeout_sec)
            elapsed = time.monotonic() - t0
            return status, elapsed, err[:120]
        except FuturesTimeout:
            elapsed = time.monotonic() - t0
            return "timeout", elapsed, f"exceeded {timeout_sec}s"
        except Exception as e:
            elapsed = time.monotonic() - t0
            return "exception", elapsed, str(e)[:120]


def main() -> None:
    print(f"\n{'Tier':<28} {'Status':<14} {'Time':>8}  Error")
    print("-" * 90)

    results = []
    for tier_name, module_path, class_name in TIERS:
        sys.stdout.write(f"  Testing {tier_name} ... ")
        sys.stdout.flush()

        status, elapsed, err = run_tier(tier_name, module_path, class_name)
        results.append((tier_name, status, elapsed, err))

        status_str = status.upper()
        print(f"\r{tier_name:<28} {status_str:<14} {elapsed:>7.1f}s  {err[:60]}")

    print("\n" + "=" * 90)
    success_count = sum(1 for _, s, _, _ in results if s == "success")
    fail_count = len(results) - success_count
    print(f"Summary: {success_count} success / {fail_count} failed (total {len(results)})")

    print("\n[MARKDOWN TABLE]")
    print(f"| {'Tier':<28} | {'Status':<14} | {'Time':>8} | Error |")
    print(f"|{'-'*30}|{'-'*16}|{'-'*10}|{'-'*40}|")
    for tier_name, status, elapsed, err in results:
        flag = "success" if status == "success" else ("no_binary/lib" if status in ("import_error", "failed") else status)
        print(f"| {tier_name:<28} | {status:<14} | {elapsed:>7.1f}s | {err[:38]} |")


if __name__ == "__main__":
    main()
