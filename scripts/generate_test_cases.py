#!/usr/bin/env python3
"""도전적인 테스트 케이스 생성 스크립트.

색다르고 힘든 메시/형상들을 STL/STEP 포맷으로 생성해서
실제 메쉬 생성 파이프라인의 견고성을 검증한다.
"""

import numpy as np
from pathlib import Path

import trimesh
import meshio


def ensure_benchmarks_dir():
    """벤치마크 디렉터리 생성."""
    bench_dir = Path(__file__).parent.parent / "tests" / "benchmarks"
    bench_dir.mkdir(parents=True, exist_ok=True)
    return bench_dir


def create_nonmanifold_mesh():
    """Non-manifold 메시: 두 삼각형이 엣지를 공유하지 않는 경우.

    Preprocessor의 L1 수리 로직을 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 두 개의 분리된 삼각형
    vertices = np.array([
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0],
        [2, 0, 0],
        [3, 0, 0],
        [2, 1, 0],
    ], dtype=float)

    faces = np.array([
        [0, 1, 2],  # 첫 삼각형
        [3, 4, 5],  # 두 번째 삼각형 (분리됨)
    ])

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    output = bench_dir / "nonmanifold_disconnected.stl"
    mesh.export(str(output))
    print(f"✓ {output.name} — 분리된 두 삼각형 (non-manifold)")
    return output


def create_high_genus_torus():
    """고 genus 형상: 다중 구멍 토러스.

    복잡한 위상을 가진 형상으로 Tier 선택 로직 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # trimesh에서 torus 생성
    mesh = trimesh.creation.torus(major_radius=2.0, minor_radius=0.5)

    # 더 복잡하게: 두 개의 토러스를 연결
    mesh2 = trimesh.creation.torus(major_radius=2.0, minor_radius=0.5)
    mesh2.apply_translation([5, 0, 0])

    # 두 메시 병합
    combined = trimesh.util.concatenate([mesh, mesh2])

    output = bench_dir / "high_genus_dual_torus.stl"
    combined.export(str(output))
    print(f"✓ {output.name} — 이중 토러스 (높은 위상복잡도, genus=2)")
    return output


def create_thin_wall_cavity():
    """얇은 벽 내부 공동: 내부 유동 테스트.

    내부에 얇은 슬릿이 있는 상자 형상.
    Strategist의 internal flow 로직 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 큰 상자
    outer = trimesh.creation.box(extents=[4, 4, 4])

    # 작은 내부 상자 (구멍)
    inner = trimesh.creation.box(extents=[2, 2, 2])
    inner.apply_translation([0, 0, 0])

    # Boolean 차집합 (외부 - 내부)
    try:
        cavity = trimesh.boolean.difference(outer, inner)
        output = bench_dir / "internal_cavity_thin_wall.stl"
        cavity.export(str(output))
        print(f"✓ {output.name} — 내부 공동 (internal flow 테스트)")
        return output
    except Exception as e:
        print(f"⚠ cavity 생성 실패: {e}")
        return None


def create_degenerate_faces():
    """Degenerate faces: 매우 작은 면적/얇은 면.

    L1 repair와 L2 remesh 로직 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 기본 구
    base = trimesh.creation.icosphere(subdivisions=2, radius=1.0)

    # 일부 꼭짓점을 매우 가깝게 이동 (degenerate 면 생성)
    vertices = base.vertices.copy()
    # 몇 개의 근처 꼭짓점들을 매우 가까이 이동
    vertices[1] = vertices[0] + np.array([1e-4, 0, 0])
    vertices[2] = vertices[0] + np.array([0, 1e-4, 0])

    mesh = trimesh.Trimesh(vertices=vertices, faces=base.faces)

    output = bench_dir / "degenerate_faces_sliver_triangles.stl"
    mesh.export(str(output))
    print(f"✓ {output.name} — Degenerate 면들 (매우 작은 면적)")
    return output


def create_large_mesh():
    """대용량 메시: 성능 & 샘플링 테스트.

    200k+ 면으로 구성된 고해상도 구.
    Analyzer의 대용량 샘플링 로직 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 고해상도 구 (약 250k 면)
    mesh = trimesh.creation.icosphere(subdivisions=6, radius=1.0)

    output = bench_dir / "large_mesh_250k_faces.stl"
    mesh.export(str(output))
    print(f"✓ {output.name} — 대용량 메시 ({len(mesh.faces):,} 면)")
    return output


def create_complex_cad_like():
    """복잡한 CAD 스타일 형상: 피처 많음.

    여러 개의 boolean 연산으로 생성한 형상.
    Generator의 다양한 Tier 호환성 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 기본 원기둥
    base = trimesh.creation.cylinder(radius=1.0, height=3.0)

    # 구멍 (boolean cut)
    hole = trimesh.creation.cylinder(radius=0.3, height=4.0)
    hole.apply_translation([0.5, 0.5, -2])

    try:
        result = trimesh.boolean.difference(base, hole)

        # 추가 구멍
        hole2 = trimesh.creation.cylinder(radius=0.3, height=4.0)
        hole2.apply_translation([-0.5, -0.5, -2])
        result = trimesh.boolean.difference(result, hole2)

        output = bench_dir / "complex_cad_cylinder_with_holes.stl"
        result.export(str(output))
        print(f"✓ {output.name} — 복합 형상 (구멍 2개, CAD 스타일)")
        return output
    except Exception as e:
        print(f"⚠ complex 형상 생성 실패: {e}")
        return None


def create_mixed_features():
    """혼합 피처: 큰 면 + 작은 디테일.

    Strategist의 flow_type 추정과 Tier 선택 로직 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 기본: 비행기 날개 형상 (판)
    wing_vertices = np.array([
        [0, 0, 0],
        [3, 0, 0],
        [3, 0.1, 0.5],
        [0, 0.1, 0.5],
        [1.5, 0.05, 0.3],  # 작은 언덕
    ], dtype=float)

    wing_faces = np.array([
        [0, 1, 2],
        [0, 2, 3],
        [1, 4, 2],
        [0, 4, 3],
    ])

    mesh = trimesh.Trimesh(vertices=wing_vertices, faces=wing_faces)

    # 작은 스파이크 추가 (디테일)
    spike = trimesh.creation.cone(radius=0.1, height=0.2, sections=8)
    spike.apply_translation([1.5, 0.1, 0.3])

    combined = trimesh.util.concatenate([mesh, spike])

    output = bench_dir / "mixed_features_wing_with_spike.stl"
    combined.export(str(output))
    print(f"✓ {output.name} — 혼합 피처 (판 + 스파이크 디테일)")
    return output


def create_very_thin_structure():
    """극도로 얇은 구조: 숨겨진 엣지/충돌 테스트.

    표면이 거의 자기 자신과 교차하는 구조.
    Generator fallback 로직 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 매우 납작한 원기둥 (너비 0.01)
    thin = trimesh.creation.cylinder(radius=1.0, height=0.01, sections=32)

    output = bench_dir / "very_thin_disk_0_01mm.stl"
    thin.export(str(output))
    print(f"✓ {output.name} — 극도로 얇은 구조 (높이=0.01)")
    return output


def create_multiple_disconnected_parts():
    """다중 분리 객체: 연결성 테스트.

    5개의 분리된 구체.
    Preprocessor의 connected component 처리 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    meshes = []
    for i in range(5):
        sphere = trimesh.creation.icosphere(subdivisions=2, radius=0.3)
        sphere.apply_translation([i * 1.5, 0, 0])
        meshes.append(sphere)

    combined = trimesh.util.concatenate(meshes)

    output = bench_dir / "five_disconnected_spheres.stl"
    combined.export(str(output))
    print(f"✓ {output.name} — 5개 분리 구체 (component 테스트)")
    return output


def create_watertight_vs_open():
    """두 가지: watertight 구 + open 메시.

    Analyzer의 watertight 판별 로직 검증.
    """
    bench_dir = ensure_benchmarks_dir()

    # Watertight: 닫힌 구
    closed = trimesh.creation.icosphere(radius=1.0)
    output1 = bench_dir / "sphere_watertight.stl"
    closed.export(str(output1))
    print(f"✓ {output1.name} — Watertight 구")

    # Open: 반구 (열린 끝) — 직접 정의로 생성
    try:
        # 반구 좌표 (z >= 0)
        vertices = []
        faces = []

        base = trimesh.creation.icosphere(radius=1.0, subdivisions=2)
        # z < 0 정점들을 제거하고 재인덱싱
        mask = base.vertices[:, 2] >= -0.05  # 약간 여유
        old_to_new = {}
        new_idx = 0
        for old_idx, keep in enumerate(mask):
            if keep:
                old_to_new[old_idx] = new_idx
                vertices.append(base.vertices[old_idx])
                new_idx += 1

        for face in base.faces:
            if all(mask[idx] for idx in face):
                new_face = [old_to_new[idx] for idx in face]
                faces.append(new_face)

        if len(faces) > 0:
            open_mesh = trimesh.Trimesh(vertices=np.array(vertices), faces=np.array(faces))
            output2 = bench_dir / "hemisphere_open_partial.stl"
            open_mesh.export(str(output2))
            print(f"✓ {output2.name} — Open 메시 (반구, 열린 끝)")
            return output1, output2
        else:
            print(f"⚠ 반구 생성 실패: 유효한 면 없음")
            return output1, None
    except Exception as e:
        print(f"⚠ 반구 생성 실패: {e}")
        return output1, None


def create_external_vs_internal_flow():
    """외부/내부 유동 형상들.

    Strategist의 flow_type 추정과 Tier 선택 로직 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # External: 고립된 객체 (주변에 유동)
    external_obj = trimesh.creation.box(extents=[1, 1, 1])
    output_ext = bench_dir / "external_flow_isolated_box.stl"
    external_obj.export(str(output_ext))
    print(f"✓ {output_ext.name} — External flow (고립 객체)")

    # Internal: 내부 파이프
    outer_pipe = trimesh.creation.cylinder(radius=1.0, height=3.0)
    inner_pipe = trimesh.creation.cylinder(radius=0.7, height=3.5)
    try:
        internal_obj = trimesh.boolean.difference(outer_pipe, inner_pipe)
        output_int = bench_dir / "internal_flow_pipe.stl"
        internal_obj.export(str(output_int))
        print(f"✓ {output_int.name} — Internal flow (파이프)")
        return output_ext, output_int
    except Exception as e:
        print(f"⚠ internal flow 생성 실패: {e}")
        return output_ext, None


def main():
    """모든 테스트 케이스 생성."""
    print("\n" + "=" * 60)
    print("색다르고 힘든 테스트 케이스 생성 시작")
    print("=" * 60 + "\n")

    results = {
        "nonmanifold": create_nonmanifold_mesh(),
        "high_genus": create_high_genus_torus(),
        "cavity": create_thin_wall_cavity(),
        "degenerate": create_degenerate_faces(),
        "large": create_large_mesh(),
        "complex_cad": create_complex_cad_like(),
        "mixed": create_mixed_features(),
        "thin": create_very_thin_structure(),
        "disconnected": create_multiple_disconnected_parts(),
        "watertight": create_watertight_vs_open(),
        "flow": create_external_vs_internal_flow(),
    }

    print("\n" + "=" * 60)
    success = sum(1 for v in results.values() if v and (isinstance(v, Path) or isinstance(v, tuple)))
    print(f"✅ 완료: {success}/{len(results)} 케이스 생성됨")
    print("=" * 60)

    print("\n📋 사용 방법:")
    print("  auto-tessell run tests/benchmarks/sphere_watertight.stl -o ./case --quality draft")
    print("  auto-tessell run tests/benchmarks/large_mesh_250k_faces.stl -o ./case --quality fine")
    print("  auto-tessell run tests/benchmarks/complex_cad_cylinder_with_holes.stl -o ./case")
    print("\n💡 각 케이스별 테스트 목적:")
    print("  • nonmanifold: L1 repair 강건성")
    print("  • high_genus: 복잡한 위상 처리")
    print("  • cavity: internal flow 감지")
    print("  • degenerate: 슬릿 면 처리")
    print("  • large: 대용량 샘플링")
    print("  • complex_cad: 다양한 Tier 호환성")
    print("  • mixed: feature 감지")
    print("  • thin: fallback 강제")
    print("  • disconnected: component 병합")
    print("  • watertight: 폐곡면 판별")
    print("  • flow: external vs internal 감지\n")


if __name__ == "__main__":
    main()
