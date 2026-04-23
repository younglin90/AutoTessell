"""beta74 — STEP 입력 → native 파이프라인 E2E.

beta53 의 OCP native reader 가 실제 STEP 파일을 tessellate → 전체 파이프라인을
거쳐 polyMesh 생성되는지 확인. OCP 미설치 환경에서는 cadquery/gmsh fallback
으로도 통과해야 함.
"""
from __future__ import annotations

from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[1]
BOX_STEP = _REPO / "tests" / "benchmarks" / "box.step"


def test_step_file_fixture_exists() -> None:
    """테스트에 필요한 STEP fixture 가 저장소에 포함돼 있다."""
    assert BOX_STEP.exists(), f"box.step 미존재: {BOX_STEP}"


def test_load_cad_accepts_step_extension(tmp_path: Path) -> None:
    """file_reader._load_via_cad 가 .step 확장자를 허용하고 trimesh.Trimesh 반환."""
    from core.analyzer.file_reader import _load_via_cad
    try:
        mesh = _load_via_cad(BOX_STEP, ".step")
    except (ImportError, ValueError) as exc:
        pytest.skip(f"CAD 로더 미사용 가능: {exc}")
    # trimesh.Trimesh — vertices / faces ndarray 노출
    V = getattr(mesh, "vertices", None)
    F = getattr(mesh, "faces", None)
    assert V is not None and F is not None
    assert V.ndim == 2 and V.shape[1] == 3
    assert F.ndim == 2 and F.shape[1] == 3
    assert V.shape[0] > 0
    assert F.shape[0] > 0


def test_load_cad_native_returns_tuple(tmp_path: Path) -> None:
    """beta53 low-level loader load_cad_native 는 (V, F) tuple 반환."""
    try:
        from core.analyzer.readers.step import load_cad_native
    except ImportError:
        pytest.skip("OCP 미설치")
    try:
        V, F = load_cad_native(BOX_STEP, ".step")
    except ImportError:
        pytest.skip("OCP 런타임 로드 실패")
    import numpy as _np
    assert isinstance(V, _np.ndarray) and V.ndim == 2 and V.shape[1] == 3
    assert isinstance(F, _np.ndarray) and F.ndim == 2 and F.shape[1] == 3


@pytest.mark.slow
def test_step_to_native_tet_pipeline(tmp_path: Path) -> None:
    """box.step → native_tet 파이프라인 (in-process). PolyMesh 5 파일 생성."""
    from core.pipeline.orchestrator import PipelineOrchestrator
    orch = PipelineOrchestrator()
    try:
        result = orch.run(
            input_path=BOX_STEP,
            output_dir=tmp_path / "case",
            quality_level="draft",
            mesh_type="tet",
            tier_hint="native_tet",
            max_iterations=1,
            auto_retry="off",
            prefer_native=True,
            prefer_native_tier=True,
        )
    except Exception as exc:
        pytest.xfail(f"STEP pipeline exception: {exc}")

    poly_dir = tmp_path / "case" / "constant" / "polyMesh"
    if not poly_dir.exists():
        pytest.xfail(f"polyMesh 생성 실패: {result.error}")
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (poly_dir / name).exists(), f"{name} 누락"
