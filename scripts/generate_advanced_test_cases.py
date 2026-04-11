#!/usr/bin/env python3
"""고급 테스트 케이스 생성: Self-intersecting, 복합 CAD 형상 등."""

import numpy as np
from pathlib import Path
import trimesh


def ensure_benchmarks_dir():
    """벤치마크 디렉터리 생성."""
    bench_dir = Path(__file__).parent.parent / "tests" / "benchmarks"
    bench_dir.mkdir(parents=True, exist_ok=True)
    return bench_dir


def create_self_intersecting():
    """Self-intersecting 메시: 표면이 자기 자신과 교차.

    Generator의 manifold 검사와 fallback 로직 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 두 개의 교차하는 판
    vertices = np.array([
        # 판 1 (XY 평면)
        [-1, -1, 0],
        [1, -1, 0],
        [1, 1, 0],
        [-1, 1, 0],
        # 판 2 (XZ 평면, 교차)
        [-1, 0, -1],
        [1, 0, -1],
        [1, 0, 1],
        [-1, 0, 1],
    ], dtype=float)

    faces = np.array([
        # 판 1
        [0, 1, 2],
        [0, 2, 3],
        # 판 2
        [4, 5, 6],
        [4, 6, 7],
    ])

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    output = bench_dir / "self_intersecting_crossed_planes.stl"
    mesh.export(str(output))
    print(f"✓ {output.name} — Self-intersecting (교차하는 판)")
    return output


def create_sharp_angle_features():
    """매우 날카로운 피처: 각도 < 5도.

    Strategist의 feature angle 처리 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 날카로운 융기(ridge)
    vertices = np.array([
        # 하단 베이스
        [-2, 0, 0],
        [2, 0, 0],
        [2, 1, 0],
        [-2, 1, 0],
        # 날카로운 피크 (거의 2도 각도)
        [0, 0.5, 0.05],
        [0, 0.5, 0.1],
    ], dtype=float)

    faces = np.array([
        # 베이스
        [0, 1, 2],
        [0, 2, 3],
        # 왼쪽 슬로프
        [0, 3, 4],
        [0, 4, 5],
        # 오른쪽 슬로프
        [1, 5, 4],
        [1, 2, 5],
    ])

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    output = bench_dir / "sharp_features_micro_ridge.stl"
    mesh.export(str(output))
    print(f"✓ {output.name} — 날카로운 피처 (각도 < 5도)")
    return output


def create_multi_scale_features():
    """다중 스케일: 마이크로 피처 + 매크로 형상.

    Analyzer의 feature detection과 remesh 강도 선택 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 큰 구
    base = trimesh.creation.icosphere(radius=2.0, subdivisions=2)

    # 표면에 마이크로 스파이크 추가
    # face_centers 대신 직접 계산
    triangles = base.vertices[base.faces]
    face_centers = triangles.mean(axis=1)

    spikes = []
    for i in range(min(8, len(face_centers))):  # 처음 8개 면에만 스파이크
        center = face_centers[i]
        normal = base.face_normals[i]

        # 마이크로 원뿔
        spike = trimesh.creation.cone(radius=0.05, height=0.1, sections=6)
        spike.apply_translation(center + normal * 0.1)
        spikes.append(spike)

    combined = trimesh.util.concatenate([base] + spikes)

    output = bench_dir / "multi_scale_sphere_with_micro_spikes.stl"
    combined.export(str(output))
    print(f"✓ {output.name} — 다중 스케일 (큰 구 + 미세 스파이크)")
    return output


def create_highly_skewed_mesh():
    """고도로 skewed 메시: 매우 납작한 삼각형들.

    Evaluator의 skewness 검사와 Generator fallback 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 매우 납작한 삼각형들
    vertices = np.array([
        [0, 0, 0],
        [10, 0, 0],
        [5, 0.1, 0],  # 매우 높은 aspect ratio
        [0, 0.1, 1],
        [10, 0.1, 1],
        [5, 0, 1],
    ], dtype=float)

    faces = np.array([
        [0, 1, 2],
        [3, 5, 4],
        [0, 2, 5],
        [0, 5, 3],
        [1, 4, 2],
        [2, 4, 5],
    ])

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    output = bench_dir / "highly_skewed_mesh_flat_triangles.stl"
    mesh.export(str(output))
    print(f"✓ {output.name} — 고도로 skewed 메시 (납작한 삼각형)")
    return output


def create_many_small_features():
    """많은 작은 피처: 수십 개의 구멍.

    Generator와 Evaluator의 성능 및 강건성 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 기본 상자
    base = trimesh.creation.box(extents=[5, 5, 2])

    # 많은 작은 구멍들
    meshes = [base]
    for i in range(8):
        for j in range(8):
            hole = trimesh.creation.cylinder(radius=0.15, height=3)
            hole.apply_translation([
                -2 + i * 0.6,
                -2 + j * 0.6,
                0
            ])
            meshes.append(hole)

    combined = trimesh.util.concatenate(meshes)

    # 직접 Union 대신 단순 병합 (boolean 피하기)
    output = bench_dir / "many_small_features_perforated_plate.stl"
    combined.export(str(output))
    print(f"✓ {output.name} — 많은 작은 피처 (천공판, 64개 구멍)")
    return output


def create_coarse_to_fine_gradation():
    """조잡 → 미세 점진적 변화: LOD 테스트.

    Generator의 locally refined mesh 생성 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 큰 구(조잡) + 작은 구(미세)
    coarse = trimesh.creation.icosphere(radius=2.0, subdivisions=1)
    fine = trimesh.creation.icosphere(radius=0.5, subdivisions=4)
    fine.apply_translation([3, 0, 0])

    combined = trimesh.util.concatenate([coarse, fine])

    output = bench_dir / "coarse_to_fine_gradation_two_spheres.stl"
    combined.export(str(output))
    print(f"✓ {output.name} — 점진적 해상도 변화 (조잡 + 미세)")
    return output


def create_extreme_aspect_ratio():
    """극단적 aspect ratio: 가느다란 형상.

    Strategist의 aspect ratio 기반 BL 파라미터 결정 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # 기다란 원기둥 (aspect ratio 100:1)
    needle = trimesh.creation.cylinder(radius=0.01, height=10.0, sections=8)

    output = bench_dir / "extreme_aspect_ratio_needle.stl"
    needle.export(str(output))
    print(f"✓ {output.name} — 극단적 aspect ratio (길이 100배)")
    return output


def create_mixed_watertight_open():
    """혼합: watertight + open 부분.

    분석기의 watertight 판별과 repair 로직 테스트.
    """
    bench_dir = ensure_benchmarks_dir()

    # Watertight 구
    sphere = trimesh.creation.icosphere(radius=1.0, subdivisions=2)

    # Open 판 (닫히지 않은 부분)
    vertices = np.array([
        [2, -0.5, -0.5],
        [4, -0.5, -0.5],
        [4, 0.5, 0.5],
        [2, 0.5, 0.5],
    ], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    plate = trimesh.Trimesh(vertices=vertices, faces=faces)

    combined = trimesh.util.concatenate([sphere, plate])

    output = bench_dir / "mixed_watertight_and_open.stl"
    combined.export(str(output))
    print(f"✓ {output.name} — 혼합 (폐곡면 구 + 열린 판)")
    return output


def main():
    """모든 고급 테스트 케이스 생성."""
    print("\n" + "=" * 60)
    print("고급 테스트 케이스 생성")
    print("=" * 60 + "\n")

    cases = [
        create_self_intersecting(),
        create_sharp_angle_features(),
        create_multi_scale_features(),
        create_highly_skewed_mesh(),
        create_many_small_features(),
        create_coarse_to_fine_gradation(),
        create_extreme_aspect_ratio(),
        create_mixed_watertight_open(),
    ]

    print("\n" + "=" * 60)
    success = sum(1 for c in cases if c)
    print(f"✅ 고급 케이스: {success}/{len(cases)} 생성됨")
    print("=" * 60)

    print("\n📊 테스트 케이스 총합:")
    print("  • 기본 케이스: 9개 (draft부터 fine까지)")
    print("  • 고급 케이스: 8개 (edge case)")
    print("  • 합계: 17개 도전적인 테스트 입력\n")


if __name__ == "__main__":
    main()
