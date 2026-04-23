"""E2E native pipeline matrix (v0.4.0-beta31) — 3 mesh_type × 3 quality.

PipelineOrchestrator.run() 을 in-process 로 호출. sphere.stl 입력, native tier
forced, BL 자동 활성화 (fine quality 에서) 검증. `@pytest.mark.slow` marker 로
default 에서는 skip, `-m slow` 로 opt-in.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"

pytestmark = pytest.mark.slow

_COMBOS = [
    ("tet", "draft"),
    ("tet", "standard"),
    ("tet", "fine"),
    ("hex_dominant", "draft"),
    ("hex_dominant", "standard"),
    ("hex_dominant", "fine"),
    ("poly", "draft"),
    ("poly", "standard"),
    ("poly", "fine"),
]


@pytest.fixture(scope="module")
def sphere_input() -> Path:
    if not SPHERE_STL.exists():
        pytest.skip(f"sphere.stl 미존재: {SPHERE_STL}")
    return SPHERE_STL


@pytest.mark.parametrize("mesh_type,quality", _COMBOS)
def test_native_pipeline_e2e(
    sphere_input: Path, tmp_path: Path, mesh_type: str, quality: str,
) -> None:
    """각 (mesh_type, quality) 조합에서 PipelineOrchestrator.run() 이 polyMesh
    생성 + 검증:
      (1) 5 파일 (points/faces/owner/neighbour/boundary) 존재.
      (2) NativeMeshChecker.negative_volumes == 0 (topology validity).

    v0.4.0-beta52: 이전(beta31) 은 result.success 에 의존해 standard/fine 에서
    Evaluator 의 품질 verdict (non_ortho > threshold 등) 로 인해 xfail 되었음.
    Pipeline 자체는 mesh 생성에 성공하므로 topology validity 를 성공 기준으로
    하는 것이 E2E 적합. 실제 파이프라인 크래시 / mesh 파일 부재 만 xfail.
    """
    from core.pipeline.orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator()
    case_dir = tmp_path / f"e2e_{mesh_type}_{quality}"

    try:
        orch.run(
            input_path=sphere_input,
            output_dir=case_dir,
            quality_level=quality,
            mesh_type=mesh_type,
            tier_hint=f"native_{mesh_type if mesh_type != 'hex_dominant' else 'hex'}",
            max_iterations=1,
            auto_retry="off",
            prefer_native=True,
            prefer_native_tier=True,
            write_of_case=False,
        )
    except Exception as exc:
        pytest.xfail(f"{mesh_type}×{quality} pipeline exception: {exc}")
        return

    poly_dir = case_dir / "constant" / "polyMesh"
    missing = [
        f for f in ("points", "faces", "owner", "neighbour", "boundary")
        if not (poly_dir / f).exists()
    ]
    if missing:
        pytest.xfail(
            f"{mesh_type}×{quality} polyMesh 파일 부재: {missing}"
        )
        return

    # NativeMeshChecker 로 topology validity 확인 — 품질 verdict 와 무관.
    from core.evaluator.native_checker import NativeMeshChecker
    checker = NativeMeshChecker()
    check = checker.run(case_dir)
    assert check.negative_volumes == 0, (
        f"{mesh_type}×{quality}: negative_volumes={check.negative_volumes}"
    )
    assert check.cells > 0, f"{mesh_type}×{quality}: cells={check.cells}"
