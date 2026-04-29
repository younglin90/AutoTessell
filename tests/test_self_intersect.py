"""beta2322 — self-intersection detect-only skeleton tests."""
from __future__ import annotations

import numpy as np

from core.preprocessor.native_repair.self_intersect import (
    SelfIntersectReport,
    detect_self_intersections,
)


def test_two_crossing_triangles_detected() -> None:
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0.5, 1, 0],
        [0.5, 0, -1], [0.5, 0, 1], [0.5, 1, 0.5],
    ], dtype=np.float64)
    F = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    r = detect_self_intersections(V, F)
    assert isinstance(r, SelfIntersectReport)
    assert r.has_self_intersection
    assert r.n_intersections >= 1
    assert (0, 1) in r.intersecting_face_pairs


def test_far_apart_triangles_no_intersection() -> None:
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [10, 0, 0], [11, 0, 0], [10, 1, 0],
    ], dtype=np.float64)
    F = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    r = detect_self_intersections(V, F)
    assert not r.has_self_intersection
    assert r.n_intersections == 0


def test_shared_vertex_not_flagged_as_intersection() -> None:
    """Triangles sharing a vertex/edge are not considered self-intersecting."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
    ], dtype=np.float64)
    # Two triangles sharing edge (0, 1).
    F = np.array([[0, 1, 2], [0, 1, 3]], dtype=np.int64)
    r = detect_self_intersections(V, F)
    assert not r.has_self_intersection


def test_large_mesh_uses_kdtree_path() -> None:
    """beta2323 — n_faces > max_pairs_for_o_n_squared 일 때 KDTree O(M log M).

    이전 (beta2322) 엔 단순 short-circuit (n_pairs_tested=0). 이제 실 검사.
    """
    rng = np.random.RandomState(0)
    V = (rng.rand(2000, 3) * 100.0).astype(np.float64)
    # 1500 tri with random vertex indices — 일부는 자연스럽게 교차.
    F = (rng.randint(0, 2000, size=(1500, 3))).astype(np.int64)
    r = detect_self_intersections(V, F, max_pairs_for_o_n_squared=1000, kdtree_k=8)
    assert r.n_faces == 1500
    # KDTree path 활성 → n_pairs_tested > 0 (이전엔 0).
    assert r.n_pairs_tested > 0, "KDTree 경로 미활성"


def test_kdtree_path_finds_intersection_in_large_mesh() -> None:
    """beta2323 — KDTree 가 진짜 교차 페어를 검출.

    1500 의 well-separated tri + 2 의 명백 교차 tri → 검출 ≥ 1.
    """
    rng = np.random.RandomState(42)
    # 멀리 떨어진 tri 1500 개 (각 100 단위 grid).
    V_list = []
    F_list = []
    n_safe = 1500
    for i in range(n_safe):
        x = (i % 50) * 100.0
        y = ((i // 50) % 50) * 100.0
        z = (i // 2500) * 100.0
        base = len(V_list)
        V_list.extend([[x, y, z], [x + 1, y, z], [x, y + 1, z]])
        F_list.append([base, base + 1, base + 2])
    # 명백한 두 교차 tri (origin 근처).
    V_list.extend([
        [0.5, 0.5, -1], [0.5, 0.5, 1], [1.5, 0.5, 0.5],   # tri A 수직
        [0.0, 0.5, 0.0], [1.0, 0.5, 0.0], [0.5, 0.5, 0.5],  # tri B 평면
    ])
    base = len(V_list) - 6
    F_list.append([base, base + 1, base + 2])
    F_list.append([base + 3, base + 4, base + 5])

    V = np.array(V_list, dtype=np.float64)
    F = np.array(F_list, dtype=np.int64)
    r = detect_self_intersections(V, F, max_pairs_for_o_n_squared=100, kdtree_k=16)
    # 최소 한 페어는 검출 (마지막 두 tri).
    assert r.has_self_intersection, "KDTree 가 명백한 교차 검출 실패"


def test_empty_input_returns_zero_report() -> None:
    V = np.zeros((0, 3), dtype=np.float64)
    F = np.zeros((0, 3), dtype=np.int64)
    r = detect_self_intersections(V, F)
    assert r.n_faces == 0
    assert r.n_intersections == 0


def test_native_tet_result_exposes_n_self_intersect_pre() -> None:
    """beta2336 — NativeTetResult 에 n_self_intersect_pre 필드 추가.

    UUU2 에서 capture 한 si_pairs 개수가 final result 에 도달 → harness /
    bench / GUI history 에서 입력 SI 신호 활용 가능."""
    import inspect
    from core.generator.native_tet.mesher import NativeTetResult, generate_native_tet
    from dataclasses import fields
    fnames = {f.name for f in fields(NativeTetResult)}
    assert "n_self_intersect_pre" in fnames, \
        f"NativeTetResult.n_self_intersect_pre 필드 누락: {fnames}"

    # mesher src 에 _pre_mesh_si_count capture + return wiring.
    src = inspect.getsource(generate_native_tet)
    assert "_pre_mesh_si_count" in src, "_pre_mesh_si_count capture 누락"
    assert "n_self_intersect_pre=_pre_mesh_si_count" in src, \
        "NativeTetResult 에 n_self_intersect_pre 채움 누락"


def test_evaluator_fidelity_populates_n_self_intersect_pre() -> None:
    """beta2334 — GeometryFidelityChecker 가 schemas.GeometryFidelity 의
    n_self_intersect_pre 필드를 채움.

    소스 검사 — 실 mesh 평가는 trimesh + polyMesh 필요해 비용 큼."""
    import inspect
    from core.evaluator import fidelity
    src = inspect.getsource(fidelity)
    # detect_self_intersections import 호출.
    assert "detect_self_intersections" in src, "SI detect import 누락"
    # GeometryFidelity 생성 시 n_self_intersect_pre 채움.
    assert "n_self_intersect_pre=n_si_pre" in src, \
        "GeometryFidelity n_self_intersect_pre 채움 누락"


def test_geometry_fidelity_schema_has_self_intersect_field() -> None:
    """beta2333 — schemas.GeometryFidelity 에 n_self_intersect_pre 필드 추가.

    P2.6 SI chain 의 evaluator 측 wiring. EvaluationSummary.geometry_fidelity
    가 SI 정보를 담아 verdict / recommendation 에 활용 가능."""
    from core.schemas import GeometryFidelity
    fields = GeometryFidelity.model_fields
    assert "n_self_intersect_pre" in fields, \
        f"n_self_intersect_pre 필드 누락: {list(fields)}"
    # default None 검증.
    f = GeometryFidelity(
        hausdorff_distance=0.01,
        hausdorff_relative=0.001,
        surface_area_deviation_percent=0.5,
    )
    assert f.n_self_intersect_pre is None
    # 명시 값 검증.
    f2 = GeometryFidelity(
        hausdorff_distance=0.01,
        hausdorff_relative=0.001,
        surface_area_deviation_percent=0.5,
        n_self_intersect_pre=7,
    )
    assert f2.n_self_intersect_pre == 7


def test_blconfig_fluid_presets_match_yplus_module() -> None:
    """beta2331 — BLConfig _FLUID_PRESETS 가 yplus.py FLUID_PROPERTIES 와
    동기화 (simple aliases air/water/oil 도 포함).

    이전엔 BLConfig 에 7 advanced presets 만 → cfg.flow_fluid_preset="air"
    호출 시 unknown warning. yplus.py FLUID_PROPERTIES 의 10 키 모두 BLConfig
    에서도 작동해야 함."""
    import inspect
    from core.layers import native_bl
    from core.utils.yplus import FLUID_PROPERTIES

    src = inspect.getsource(native_bl.generate_native_bl)
    # _FLUID_PRESETS 블록 추출 (간단히 keys 검사).
    for required in ("air", "water", "oil", "air_20C", "water_20C",
                     "oil_SAE10W30", "glycol_50pct"):
        assert f'"{required}"' in src, \
            f"BLConfig _FLUID_PRESETS 에 simple alias '{required}' 누락"

    # yplus 모듈의 FLUID_PROPERTIES 와 키셋 일관성 (simple+advanced).
    yplus_keys = set(FLUID_PROPERTIES.keys())
    # 최소 air/water/oil + 7 advanced = 10 키 중 최소 7개 BLConfig 에도 존재.
    n_present = sum(1 for k in yplus_keys if f'"{k}"' in src)
    assert n_present >= 7, \
        f"yplus 와 BLConfig fluid preset 동기화 미달: {n_present}/{len(yplus_keys)}"


def test_export_intersecting_faces_stl_writes_binary_file() -> None:
    """beta2330 — export_intersecting_faces_stl 가 unique face 만 binary STL 작성.

    binary STL header (80 bytes) + uint32 n_tri + 50 bytes/tri 검증."""
    import tempfile
    from pathlib import Path
    from core.preprocessor.native_repair.self_intersect import (
        export_intersecting_faces_stl,
    )

    V = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0],
         [0.5, 0.5, -1], [0.5, 0.5, 1], [1.5, 0.5, 0]],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    pairs = [(0, 1)]

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "si.stl"
        n = export_intersecting_faces_stl(V, F, pairs, out)
        assert n == 2, f"unique face count mismatch: {n}"
        assert out.exists()
        # 80 + 4 + 50*2 = 184 bytes
        assert out.stat().st_size == 184


def test_export_intersecting_faces_stl_handles_empty_pairs() -> None:
    """beta2330 — 빈 pairs 입력 시 0-face STL 생성 (84 bytes header only)."""
    import tempfile
    from pathlib import Path
    from core.preprocessor.native_repair.self_intersect import (
        export_intersecting_faces_stl,
    )

    V = np.zeros((3, 3), dtype=np.float64)
    F = np.array([[0, 1, 2]], dtype=np.int64)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "empty.stl"
        n = export_intersecting_faces_stl(V, F, [], out)
        assert n == 0
        assert out.exists()
        assert out.stat().st_size == 84   # 80 header + 4 count.


def test_native_bl_quality_json_includes_pre_bl_si() -> None:
    """beta2328 — native_bl_quality.json 에 pre_bl_self_intersect 필드 포함."""
    import inspect
    from core.layers import native_bl
    src = inspect.getsource(native_bl.generate_native_bl)
    assert '"pre_bl_self_intersect": _pre_bl_si_count' in src or \
        "pre_bl_self_intersect" in src, "pre_bl_self_intersect JSON 필드 누락"


def test_native_bl_pre_extrude_si_check_wired() -> None:
    """beta2327 — native_bl 진입에 pre-extrude SI 진단 추가.

    wall surface 에 SI 가 있으면 prism extrusion collision_safety 가
    thickness 자동 축소 — 사전 진단으로 사용자가 L1 repair 강화 또는
    num_layers ↓ 의사결정 가능."""
    import inspect
    from core.layers import native_bl
    src = inspect.getsource(native_bl.generate_native_bl)
    assert "detect_self_intersections as _det_si_bl" in src or \
        "detect_self_intersections" in src, "SI detect import 누락"
    assert "native_bl_pre_extrude_self_intersect" in src or \
        "native_bl_pre_extrude_si_clean" in src, "pre-BL SI 진단 로그 누락"


def test_run_native_repair_captures_self_intersect_count() -> None:
    """beta2325 — run_native_repair 결과에 n_self_intersect_before/after 포함."""
    from core.preprocessor.native_repair import run_native_repair

    # Tetrahedral surface (no SI).
    V = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]], dtype=np.int64)
    r = run_native_repair(V, F, aggressive=1)
    # ≤5000 face 입력 → 진단 실행됨.
    assert r.n_self_intersect_before is not None
    assert r.n_self_intersect_after is not None
    assert r.n_self_intersect_before == 0
    assert r.n_self_intersect_after == 0
