"""단일 tier를 cube.stl (draft) 로 실행하고 결과를 JSON으로 출력."""
from __future__ import annotations

import importlib
import json
import sys
import time
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.utils.logging import configure_logging
configure_logging(verbose=False, json=False)

from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    QualityLevel,
    QualityTargets,
    SurfaceMeshConfig,
)

CUBE_STL = ROOT / "tests" / "benchmarks" / "cube.stl"


def make_strategy(tier_name: str) -> MeshStrategy:
    return MeshStrategy(
        strategy_version=2,
        iteration=1,
        selected_tier=tier_name,
        fallback_tiers=[],
        quality_level=QualityLevel.DRAFT,
        flow_type="internal",
        domain=DomainConfig(
            type="box",
            min=[-2.0, -2.0, -2.0],
            max=[2.0, 2.0, 2.0],
            base_cell_size=0.5,
            location_in_mesh=[0.0, 0.0, 0.0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file=str(CUBE_STL),
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
        tier_specific_params={},
    )


def main() -> None:
    tier_name = sys.argv[1]
    module_path = sys.argv[2]
    class_name = sys.argv[3]

    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
    except (ImportError, AttributeError) as e:
        print(json.dumps({"status": "import_error", "elapsed": 0.0, "error": str(e)[:200]}))
        return

    strategy = make_strategy(tier_name)

    with tempfile.TemporaryDirectory() as tmp:
        case_dir = Path(tmp) / "case"
        case_dir.mkdir()
        generator = cls()
        t0 = time.monotonic()
        try:
            result = generator.run(
                strategy=strategy,
                preprocessed_path=CUBE_STL,
                case_dir=case_dir,
            )
            elapsed = time.monotonic() - t0
            print(json.dumps({
                "status": result.status,
                "elapsed": elapsed,
                "error": (result.error_message or "")[:200],
            }))
        except Exception as e:
            elapsed = time.monotonic() - t0
            print(json.dumps({"status": "exception", "elapsed": elapsed, "error": str(e)[:200]}))


if __name__ == "__main__":
    main()
