"""Tier 0.5 (Netgen) — 목표 셀 수 N 반영 검증.

Netgen tier 는 예전에 ``strategy.tier_specific_params`` 의 ``target_cells`` /
``max_cells`` 를 완전히 무시하고 Strategist 의 auto 표면 크기
(``surface_mesh.target_cell_size``) 만 사용했다. 그 결과 작은 N 요청이
100x+ 로 폭증했다 (cube N=2000 → 364,722 cells, 182x — Advisor 측정).

수정 후: N 이 주어지면 ``_edge_from_target_cells`` (native tier 공용 로직) 로
maxh 를 유도해 실제 셀 수가 N 근처에 오도록 한다.

측정 (real tier, cube.stl, auto maxh=0.05):
    baseline(no-N) = 37,196 tets  (target 대비 ~21-24x — 폭증)
    N=1500 → 1715  (ratio 1.14)
    N=3000 → 2992  (ratio 1.00)
    N=6000 → 5411  (ratio 0.90)

관측 ratio 대역 [0.90, 1.14]. Netgen 버전 차이 / 형상별 변동을 감안해 정직하게
넓은 대역 ``[0.5, 1.6]`` 로 검증한다 — 이는 수정 전 폭증(>20x)과 명확히 구분되고,
a-priori 보정만으로 도달 가능한 정확도를 정직하게 반영한다 (수정 전에는 반드시
FAIL, 수정 후 PASS).

pre-fix 대비 검증: SCOPED ``git stash push -- core/generator/tier05_netgen.py
core/generator/_tier_native_common.py`` 후 이 파일 실행 시 반드시 FAIL 해야 한다.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("netgen")
pytest.importorskip("netgen.stl")
meshio = pytest.importorskip("meshio")

from core.schemas import (  # noqa: E402
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    QualityLevel,
    SurfaceMeshConfig,
)

_CUBE = Path(__file__).parent / "benchmarks" / "cube.stl"

# 관측 대역 [0.90, 1.14] → 정직한 넓은 대역.
_RATIO_LO = 0.5
_RATIO_HI = 1.6


def _has_stl_geometry() -> bool:
    try:
        from netgen.stl import STLGeometry  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = [
    pytest.mark.skipif(not _CUBE.exists(), reason="cube.stl 벤치마크 없음"),
    pytest.mark.skipif(not _has_stl_geometry(), reason="netgen.stl.STLGeometry 미지원 빌드"),
]


def _make_strategy(
    target_cell_size: float,
    min_cell_size: float,
    target_cells: int | None = None,
) -> MeshStrategy:
    """cube 내부 (internal) flow 용 Netgen 전략. N 지정 시 tier_specific_params 주입."""
    tsp: dict[str, object] = {
        "netgen_grading": 0.3,
        "netgen_curvaturesafety": 2.0,
        "netgen_segmentsperedge": 1.0,
    }
    if target_cells is not None:
        tsp["target_cells"] = target_cells
    return MeshStrategy(
        strategy_version=3,
        iteration=1,
        selected_tier="tier05_netgen",
        fallback_tiers=[],
        flow_type="internal",
        quality_level=QualityLevel.STANDARD,
        domain=DomainConfig(
            type="box",
            min=[-0.5, -0.5, -0.5],
            max=[0.5, 0.5, 0.5],
            base_cell_size=0.1,
            location_in_mesh=[0.0, 0.0, 0.0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file=str(_CUBE),
            target_cell_size=target_cell_size,
            min_cell_size=min_cell_size,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False,
            num_layers=0,
            first_layer_thickness=0.001,
            growth_ratio=1.2,
            max_total_thickness=0.01,
            min_thickness_ratio=0.1,
        ),
        tier_specific_params=tsp,
    )


def _count_tets(case_dir: Path) -> int:
    """Netgen 이 export 한 netgen_mesh.msh 의 tetra 셀 수."""
    msh = case_dir / "netgen_mesh.msh"
    assert msh.exists(), "netgen_mesh.msh 가 생성되지 않았습니다"
    mesh = meshio.read(str(msh))
    return sum(len(cb.data) for cb in mesh.cells if cb.type == "tetra")


def _run_netgen(strategy: MeshStrategy, case_dir: Path) -> int:
    """Netgen tier 실행 (OpenFOAM 없이 PolyMeshWriter fallback) 후 tet 수 반환."""
    from core.generator.tier05_netgen import Tier05NetgenGenerator

    gen = Tier05NetgenGenerator()
    # gmshToFoam 을 강제로 실패시켜 OpenFOAM 미설치 환경에서도 폴리메시 생성 진행.
    with patch(
        "core.generator.tier05_netgen.run_openfoam",
        side_effect=FileNotFoundError("gmshToFoam: command not found"),
    ):
        attempt = gen.run(strategy, _CUBE, case_dir)
    assert attempt.status == "success", f"tier 실패: {attempt.error_message}"
    return _count_tets(case_dir)


# auto maxh=0.05 (min 0.0125) — N 이 없으면 cube 에서 ~37k tets 로 폭증하는 크기.
_AUTO_MAXH = 0.05
_AUTO_MINH = 0.0125


@pytest.mark.parametrize("n_target", [1500, 4000])
def test_target_cells_controls_count(n_target: int, tmp_path: Path) -> None:
    """target_cells=N 지정 시 실제 tet 수가 N 의 [0.5, 1.6]x 대역 안에 들어온다.

    수정 전 코드에서는 auto maxh=0.05 만 사용해 N 과 무관하게 ~37k tets 를
    생성하므로 이 assert 는 반드시 실패한다 (>20x).
    """
    strategy = _make_strategy(_AUTO_MAXH, _AUTO_MINH, target_cells=n_target)
    n_tets = _run_netgen(strategy, tmp_path)

    lo = int(_RATIO_LO * n_target)
    hi = int(_RATIO_HI * n_target)
    assert lo <= n_tets <= hi, (
        f"N={n_target} 요청인데 {n_tets} tets 생성 "
        f"(허용 대역 [{lo}, {hi}], ratio={n_tets / n_target:.2f})"
    )


def test_absent_target_cells_keeps_auto_size(tmp_path: Path) -> None:
    """N 부재 시 기존 동작 유지 — auto maxh 를 그대로 사용해 폭증(수천 tet 초과).

    N-driven 경로가 켜지지 않았음을 보이는 회귀 가드. auto maxh=0.05 는 cube 에서
    수만 개 tet 를 낳으므로, N=4000 상한(6400)을 크게 초과해야 한다.
    """
    strategy = _make_strategy(_AUTO_MAXH, _AUTO_MINH, target_cells=None)
    n_tets = _run_netgen(strategy, tmp_path)
    assert (
        n_tets > 20000
    ), f"N 부재 auto-size 인데 {n_tets} tets — 기존 auto 동작이 바뀐 것으로 의심"


def test_env_gate_disables_target_cells(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AUTO_TESSELL_NETGEN_TARGET_CELLS=0 → N 무시, auto 크기로 폭증."""
    monkeypatch.setenv("AUTO_TESSELL_NETGEN_TARGET_CELLS", "0")
    strategy = _make_strategy(_AUTO_MAXH, _AUTO_MINH, target_cells=1500)
    n_tets = _run_netgen(strategy, tmp_path)
    assert (
        n_tets > 20000
    ), f"env gate OFF 인데 N=1500 이 적용된 듯 ({n_tets} tets) — 게이트 무력화 실패"
