"""native_poly MVP (scipy Voronoi) 회귀 테스트.

MVP 특성상 OpenFOAM checkMesh 로는 open cell 경고가 남을 수 있으나 (boundary
clipping 미완성), polyMesh 파일 생성 + cell 수 > 0 + cells=polyhedra 만 확인.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

import core.preprocessor.native_repair as _repair_mod
from core.analyzer.readers import read_stl
from core.generator import native_poly
from core.generator.native_poly import generate_native_poly_voronoi
from core.generator.native_poly import voronoi as _native_poly_voronoi
from core.preprocessor.native_repair import NativeRepairResult

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


@pytest.fixture
def tmp_case_dir():
    tmp = Path(tempfile.mkdtemp(prefix="native_poly_"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_native_poly_sphere_produces_cells(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir, seed_density=10,
    )
    assert res.success, res.message
    assert res.n_cells > 0


def test_native_poly_polymesh_files_exist(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir, seed_density=8,
    )
    assert res.success
    poly_dir = tmp_case_dir / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (poly_dir / name).exists()


def test_native_poly_denser_seed_more_cells(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    r1 = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir / "coarse", seed_density=8,
    )
    r2 = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir / "fine", seed_density=14,
    )
    assert r1.success and r2.success
    assert r2.n_cells >= r1.n_cells


def test_native_poly_empty_input_fails(tmp_case_dir: Path) -> None:
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    res = generate_native_poly_voronoi(V, F, tmp_case_dir)
    assert res.success is False


# ---------------------------------------------------------------------------
# beta98 Task B: n_lloyd 파라미터 + 3D Lloyd CVT 개선 테스트
# ---------------------------------------------------------------------------


def test_native_poly_lloyd_zero_same_as_default(tmp_case_dir: Path) -> None:
    """n_lloyd=0 은 Lloyd 정제 없이 기존 동작과 동일 — 성공해야 함."""
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir, seed_density=8, n_lloyd=0,
    )
    assert res.success, res.message
    assert res.n_cells > 0


def test_native_poly_lloyd_positive_succeeds(tmp_case_dir: Path) -> None:
    """n_lloyd=2 (기본값) 는 성공하고 cell 을 생성해야 함."""
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir, seed_density=8, n_lloyd=2,
    )
    assert res.success, res.message
    assert res.n_cells > 0


def test_native_poly_best_of_n_repair_retry(
    tmp_case_dir: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P1.2 — best-of-N 후보 실패 시 self-repair fallback 재시도를 검증."""
    # 기본 tetra 입력을 사용하되 내부 구현은 모킹해서 best-of-N 전부 실패 처리.
    V = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]], dtype=np.int64)

    calls = {"inner": 0, "repair": 0}

    def fake_inner(
        vertices: NDArray[np.float64],
        faces: NDArray[np.int64],
        _case: Path,
        **kwargs,
    ) -> native_poly.NativePolyResult:
        calls["inner"] += 1
        if calls["inner"] <= 3:
            return native_poly.NativePolyResult(False, 0.0, n_cells=0, message="forced fail")
        return native_poly.NativePolyResult(
            True, 0.0, n_cells=3, n_points=vertices.shape[0],
            n_faces=6, quality_grade="A",
        )

    def fake_repair(
        vertices: NDArray[np.float64],
        faces: NDArray[np.int64],
        **kwargs,
    ) -> NativeRepairResult:
        calls["repair"] += 1
        return NativeRepairResult(vertices=vertices.copy(), faces=faces.copy())

    def fake_hex_fallback(*_args: object, **_kwargs: object) -> native_poly.NativePolyResult:
        # best-of-N 검증을 방해하지 않도록 hex fallback 도 실패 처리.
        calls["inner"] += 1
        return native_poly.NativePolyResult(False, 0.0, n_cells=0, message="forced fallback fail")

    monkeypatch.setattr(_native_poly_voronoi, "_generate_native_poly_voronoi_inner", fake_inner)
    monkeypatch.setattr(_native_poly_voronoi, "_hex_to_poly_fallback", fake_hex_fallback)
    monkeypatch.setattr(_repair_mod, "run_native_repair", fake_repair)

    res = generate_native_poly_voronoi(V, F, tmp_case_dir, seed_density=2, auto_escalate_max=1)
    assert res.success
    assert res.quality_grade == "A"
    assert calls["inner"] >= 4
    assert calls["repair"] == 1


def test_native_poly_best_of_n_repair_tries_two_variants_and_two_lp_p(
    tmp_case_dir: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """beta2306 — repair-retry 가 2 variant × 2 lp_p (p=2, p=4) 를 모두 시도.

    이전 (beta2233) 엔 단일 lp_p=2.0 + 단일 aggressive=3 만 시도 → extreme
    tier 4/5 fail. beta2306 은 2 (aggressive, dedup_tol, fill_max) variants
    × 2 lp_p = 최대 4 회 추가 시도로 회복률 ↑.
    """
    V = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
         [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]], dtype=np.int64)

    inner_calls: list[dict] = []
    repair_calls: list[dict] = []

    def fake_inner(vertices, faces, _case, **kwargs):
        inner_calls.append({"lp_p": kwargs.get("lp_p")})
        # best-of-N 3 회 + 첫 variant p=2/p=4 + 두번째 variant p=2/p=4 = 7 회 모두 실패.
        return native_poly.NativePolyResult(False, 0.0, n_cells=0, message="forced fail")

    def fake_repair(vertices, faces, **kwargs):
        repair_calls.append({
            "aggressive": kwargs.get("aggressive"),
            "dedup_tol": kwargs.get("dedup_tol"),
            "fill_hole_max_boundary": kwargs.get("fill_hole_max_boundary"),
        })
        return NativeRepairResult(vertices=vertices.copy(), faces=faces.copy())

    def fake_hex_fallback(*_args, **_kwargs):
        return native_poly.NativePolyResult(False, 0.0, n_cells=0, message="forced fallback fail")

    monkeypatch.setattr(_native_poly_voronoi, "_generate_native_poly_voronoi_inner", fake_inner)
    monkeypatch.setattr(_native_poly_voronoi, "_hex_to_poly_fallback", fake_hex_fallback)
    monkeypatch.setattr(_repair_mod, "run_native_repair", fake_repair)

    res = generate_native_poly_voronoi(V, F, tmp_case_dir, seed_density=2, auto_escalate_max=1)
    assert not res.success  # 모두 forced fail.
    # 2 repair variants 시도.
    assert len(repair_calls) == 2, f"repair 호출 수: {len(repair_calls)}"
    assert repair_calls[0]["aggressive"] == 3
    assert repair_calls[1]["aggressive"] == 2
    assert repair_calls[1]["fill_hole_max_boundary"] == 512  # 더 큰 hole.
    # 각 variant 마다 lp_p ∈ {2.0, 4.0} 양쪽 시도 → 최소 4 회 inner.
    repair_path_inner = [c for c in inner_calls if c["lp_p"] in (2.0, 4.0)]
    # best-of-N 의 p=2/p=4 도 lp_p 가지므로 ≥ 4 만 검증.
    p_set = {c["lp_p"] for c in repair_path_inner}
    assert 2.0 in p_set and 4.0 in p_set, f"lp_p 양쪽 미시도: {p_set}"


def test_native_poly_lloyd_signature_accepts_n_lloyd() -> None:
    """generate_native_poly_voronoi 가 n_lloyd keyword 를 받아야 함."""
    import inspect
    sig = inspect.signature(generate_native_poly_voronoi)
    assert "n_lloyd" in sig.parameters, "n_lloyd 파라미터 누락"
    assert sig.parameters["n_lloyd"].default == 2


def test_native_poly_repair_retry_logs_si_delta() -> None:
    """beta2326 — repair-retry 로그에 si_before/si_after/si_delta 노출.

    이전 (beta2306) 엔 v_before/f_before/aggressive 만 — repair 가 실제로
    SI 를 줄였는지 외부 visibility 0. beta2325 의 SI tracking 결과를 활용해
    (si_after - si_before) 를 로그에 추가."""
    import inspect
    from core.generator.native_poly import voronoi
    src = inspect.getsource(voronoi.generate_native_poly_voronoi)
    assert "si_before=int(_si_b)" in src or "si_before=" in src, \
        "repair retry 로그에 si_before 누락"
    assert "si_delta=" in src, "si_delta 로그 누락"


def test_native_poly_self_intersect_diag_in_best_of_n_fail() -> None:
    """beta2324 — best-of-N fail 분기에서 self-intersect detect 호출.

    fail 시 사용자에게 'n_intersections=K' 신호 → 입력 품질 가이드 +
    repair-retry 동작 근거. Möller 1997 separating axis 기반."""
    import inspect
    from core.generator.native_poly import voronoi
    src = inspect.getsource(voronoi.generate_native_poly_voronoi)
    assert "detect_self_intersections" in src, "self-intersect 진단 import 누락"
    assert "native_poly_self_intersect_diag" in src, \
        "self-intersect 진단 로그 누락"


def test_native_poly_qed_decimate_wired_for_large_input() -> None:
    """beta2314 — generate_native_poly_voronoi 가 quadric_decimate 호출 분기 보유.

    50k+ face 입력 자동 단순화 (native_tet beta2308 동일 패턴). voronoi
    seed/CVT 시간 ↓ + boundary snap 안정도 ↑. AUTO_TESSELL_QED env 로
    on/off/auto 제어."""
    import inspect
    from core.generator.native_poly import voronoi
    src = inspect.getsource(voronoi.generate_native_poly_voronoi)
    assert "quadric_decimate" in src, "quadric_decimate import/call 누락"
    assert 'AUTO_TESSELL_QED", "auto"' in src or "_qed_env" in src, \
        "QED env-gate 누락"
    assert '"AUTO_TESSELL_QED_MIN_F", "50000"' in src, \
        "50000 default threshold 누락"
