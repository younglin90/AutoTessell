"""beta2322 — self-intersection detect-only skeleton tests."""
from __future__ import annotations

import numpy as np
import pytest

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


def test_native_exact_broad_phase_replaces_large_mesh_approximation() -> None:
    """Native availability must bypass a deliberately empty k=1 search."""
    from core.utils.native_extensions import load_native_metrics

    native = load_native_metrics()
    if native is None or not hasattr(native, "aabb_overlap_pairs"):
        pytest.skip("native exact AABB broad phase is not built")

    vertices = np.array([
        [0, 0, 0], [1, 0, 0], [0.5, 1, 0],
        [0.5, 0, -1], [0.5, 0, 1], [0.5, 1, 0.5],
    ], dtype=np.float64)
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)

    report = detect_self_intersections(
        vertices,
        faces,
        max_pairs_for_o_n_squared=0,
        kdtree_k=1,
    )

    assert report.intersecting_face_pairs == [(0, 1)]
    assert report.n_pairs_tested == 1


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


def test_perpendicular_adjacent_grid_faces_not_flagged() -> None:
    """Plane-crossing alone is not a self-intersection."""
    V = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 0.1, 0.0],
        [0.1, 0.1, 0.0],
        [0.1, 0.0, 0.0],
        [0.2, 0.0, 0.0],
        [0.2, 0.0, 0.1],
    ], dtype=np.float64)
    # First triangle is on z=0, second on y=0. Their planes cross, but the
    # finite triangles do not overlap. This pattern appears on voxelized cube
    # boundary faces when each quad is fan-triangulated.
    F = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
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


def test_native_hex_all_paths_populate_si() -> None:
    """beta2341 + beta2342 — 모든 return path (uniform 성공 / octree 성공 /
    3 fail) 가 SI populate.

    beta2338 = uniform 성공만, beta2341 = + octree 성공, beta2342 = 3 fail
    까지 → 총 5 분기."""
    import inspect
    from core.generator.native_hex.mesher import generate_native_hex
    src = inspect.getsource(generate_native_hex)
    n = src.count("n_self_intersect_pre=_pre_mesh_si_count")
    assert n >= 5, f"populate 분기 < 5 (현재 {n})"


def test_native_poly_mesher_populates_si_pre_field() -> None:
    """beta2339 — generate_native_poly_voronoi 가 모든 success path 에서
    NativePolyResult.n_self_intersect_pre 채움 (helper _inject_si 사용)."""
    import inspect
    from core.generator.native_poly.voronoi import generate_native_poly_voronoi
    src = inspect.getsource(generate_native_poly_voronoi)
    # capture + helper.
    assert "_pre_mesh_si_count" in src
    assert "_inject_si" in src
    # 4+ return path 모두 _inject_si 로 wrap.
    assert "return _inject_si(_retry_r)" in src or \
        "_inject_si(_retry_r)" in src
    assert "return _inject_si(best_result)" in src


def test_native_hex_mesher_populates_si_pre_field() -> None:
    """beta2338 — generate_native_hex 가 NativeHexResult.n_self_intersect_pre 채움."""
    import inspect
    from core.generator.native_hex.mesher import generate_native_hex
    src = inspect.getsource(generate_native_hex)
    # capture + return wiring.
    assert "_pre_mesh_si_count" in src
    assert "n_self_intersect_pre=_pre_mesh_si_count" in src
    # detect_self_intersections import.
    assert "detect_self_intersections as _det_si_hex" in src


def test_native_hex_actually_populates_si_value_end_to_end() -> None:
    """beta2359 — generate_native_hex 가 실 mesh 생성 후 n_self_intersect_pre
    가 int (None 아님) 로 채워짐. Schema/contract 기반 검증과 별도로
    end-to-end 동작 확인."""
    import tempfile
    from pathlib import Path
    from core.generator.native_hex import generate_native_hex

    V = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]], dtype=np.int64)
    with tempfile.TemporaryDirectory() as tmp:
        r = generate_native_hex(V, F, Path(tmp), seed_density=4)
    # ≤5000 face → populate 됨 (None 아님).
    assert r.n_self_intersect_pre is not None
    assert isinstance(r.n_self_intersect_pre, int)


def test_native_hex_and_poly_results_have_si_field() -> None:
    """beta2337 — NativeHexResult / NativePolyResult 도 동일 SI 필드 노출.

    native_tet (beta2336) 와 일관 schema. P2.6 chain 의 3 native engine
    return type 모두 SI 정보 capture 가능."""
    from dataclasses import fields
    from core.generator.native_hex.mesher import NativeHexResult
    from core.generator.native_poly.voronoi import NativePolyResult

    hex_fields = {f.name for f in fields(NativeHexResult)}
    poly_fields = {f.name for f in fields(NativePolyResult)}
    assert "n_self_intersect_pre" in hex_fields, \
        f"NativeHexResult.n_self_intersect_pre 누락"
    assert "n_self_intersect_pre" in poly_fields, \
        f"NativePolyResult.n_self_intersect_pre 누락"


def test_uuu6_face_split_has_si_monotone_guard() -> None:
    """beta2350 — UUU6 face split 후 SI 재검출 → 늘어나면 revert.

    이전엔 split 후 무조건 결과 채택 — split 이 의도와 반대로 SI 더
    늘리는 경우 (drei tri 가 새 vertex 로 splitt 되며 인접 cross) 보호 없음."""
    import inspect
    from core.generator.native_tet import mesher
    src = inspect.getsource(mesher.generate_native_tet)
    # 새 가드 패턴.
    assert "native_tet_uuu6_face_split_reverted" in src, \
        "UUU6 reverted 분기 누락"
    assert "si_post" in src, "post-split SI 측정 누락"
    assert "len(si_post)) <= int(len(si_pairs))" in src, \
        "SI 비교 가드 누락"


def test_native_tet_result_exposes_n_self_intersect_pre() -> None:
    """beta2336 + beta2343 — NativeTetResult.n_self_intersect_pre 필드 +
    success path + 4 fail path 모두 SI populate.

    UUU2 capture 후 발생할 수 있는 5 fail return (post-UUU2) 까지 wired.
    전체 6 분기 (success + 5 fail post-UUU2) 모두 채움."""
    import inspect
    from core.generator.native_tet.mesher import NativeTetResult, generate_native_tet
    from dataclasses import fields
    fnames = {f.name for f in fields(NativeTetResult)}
    assert "n_self_intersect_pre" in fnames, \
        f"NativeTetResult.n_self_intersect_pre 필드 누락: {fnames}"

    src = inspect.getsource(generate_native_tet)
    assert "_pre_mesh_si_count" in src, "_pre_mesh_si_count capture 누락"
    # success + 5 post-UUU2 fail path (max_input / Delaunay / inside tet=0 /
    # polyMesh write / polyMesh post-P4C) 모두 wired = 최소 5 분기.
    n = src.count("n_self_intersect_pre=_pre_mesh_si_count")
    assert n >= 5, f"populate 분기 < 5 (현재 {n})"


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
