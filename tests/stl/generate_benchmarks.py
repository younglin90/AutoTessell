"""WildMesh 난이도별 벤치마크 STL 생성기.

5단계 난이도:
    1) 하 (easy)       : 단순 Convex 박스 — baseline
    2) 중 (medium)     : 곡면 실린더 + 큰 관통 홀 — 곡률 + genus-1
    3) 상 (hard)       : L-브래킷 + 다중 홀 + 얇은 벽 — 날카로운 feature
    4) 극상 (extreme)  : 톱니 기어 + 원통 hub — 많은 sharp edge + 좁은 간극
    5) 초극상 (ultra)  : 트레포일 매듭 (고해상도) — 고곡률 + 꼬임 + 고 genus

사용법::

    python tests/stl/generate_benchmarks.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Polygon

OUT_DIR = Path(__file__).parent


def _save(mesh: trimesh.Trimesh, name: str) -> Path:
    """메시를 다각형 수와 함께 저장하고 정보를 출력."""
    path = OUT_DIR / name
    mesh.export(path)
    print(
        f"  ✓ {name:32s} faces={len(mesh.faces):>6d} "
        f"vertices={len(mesh.vertices):>6d} "
        f"watertight={mesh.is_watertight} "
        f"genus={int(mesh.body_count)}body"
    )
    return path


# ---------------------------------------------------------------------------
# 1. 하 — 단순 박스
# ---------------------------------------------------------------------------
def make_easy() -> trimesh.Trimesh:
    """1x1x1 육면체. 12 triangles. Pure convex, sharp edges 90°만."""
    return trimesh.creation.box(extents=(1.0, 1.0, 1.0))


# ---------------------------------------------------------------------------
# 2. 중 — 곡면 실린더 + 관통 홀
# ---------------------------------------------------------------------------
def make_medium() -> trimesh.Trimesh:
    """외경 1, 내경 0.3 의 중공 실린더 (annulus extrude). 곡면 + genus-1."""
    n = 64
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    outer = [(0.5 * np.cos(a), 0.5 * np.sin(a)) for a in angles]
    inner = [(0.15 * np.cos(-a), 0.15 * np.sin(-a)) for a in angles]
    ring = Polygon(outer, holes=[inner])
    return trimesh.creation.extrude_polygon(ring, height=1.0)


# ---------------------------------------------------------------------------
# 3. 상 — L-브래킷 + 다중 홀 + 얇은 벽
# ---------------------------------------------------------------------------
def make_hard() -> trimesh.Trimesh:
    """L자 브래킷 (X-Y 평면 L-형상 extrude) + 원형 볼트홀 3개.

    날카로운 내각(90°) + 다중 관통 홀 + 얇은 벽(0.15).
    평면에서 L-형 polygon + 3개 circular hole → extrude.
    """
    # L-형 외곽 (수평부 2×1 + 수직부 1×0.15 가 겹침)
    outer = [
        (0.0, 0.0), (2.0, 0.0), (2.0, 0.15),
        (0.15, 0.15), (0.15, 1.0), (0.0, 1.0),
    ]
    # 수평부 볼트홀 3개 — (cx, 0.075 의 원을 approximate)
    def circle_hole(cx: float, cy: float, r: float, n: int = 32) -> list[tuple[float, float]]:
        # 시계방향 (외곽은 반시계, 홀은 시계)
        return [
            (cx + r * np.cos(-2 * np.pi * i / n),
             cy + r * np.sin(-2 * np.pi * i / n))
            for i in range(n)
        ]

    holes = [
        circle_hole(0.5, 0.075, 0.035),
        circle_hole(1.0, 0.075, 0.035),
        circle_hole(1.5, 0.075, 0.035),
    ]
    l_profile = Polygon(outer, holes=holes)
    mesh = trimesh.creation.extrude_polygon(l_profile, height=1.2)
    return mesh


# ---------------------------------------------------------------------------
# 4. 극상 — 톱니 기어 + 중심 허브 + 키홈
# ---------------------------------------------------------------------------
def make_extreme() -> trimesh.Trimesh:
    """20-톱니 평기어 + 샤프트홀 + 허브 구멍 4개.

    sharp edge 80+ 개 (each tooth), 좁은 dedendum 간극, 얇은 림.
    """
    n_teeth = 20
    pitch_r = 1.0
    addendum = 0.15
    dedendum = 0.12
    outer_r = pitch_r + addendum
    root_r = pitch_r - dedendum
    thickness = 0.3

    # 기어 2D 프로파일 (사다리꼴 톱니)
    pts: list[tuple[float, float]] = []
    for i in range(n_teeth):
        base = 2 * np.pi * i / n_teeth
        tooth_w = np.pi / n_teeth * 0.45
        gap_w = np.pi / n_teeth * 0.55
        ang = [
            base - gap_w,
            base - tooth_w * 0.6,
            base - tooth_w * 0.3,
            base + tooth_w * 0.3,
            base + tooth_w * 0.6,
            base + gap_w,
        ]
        rad = [root_r, pitch_r, outer_r, outer_r, pitch_r, root_r]
        for a, r in zip(ang, rad):
            pts.append((r * np.cos(a), r * np.sin(a)))

    # 내부 홀들: 중심 샤프트 + 허브 4개 (각도 균등)
    def hole(cx: float, cy: float, r: float, n: int = 24) -> list[tuple[float, float]]:
        return [
            (cx + r * np.cos(-2 * np.pi * i / n),
             cy + r * np.sin(-2 * np.pi * i / n))
            for i in range(n)
        ]

    holes = [hole(0, 0, 0.18, 40)]
    for k in range(4):
        ang = 2 * np.pi * k / 4 + np.pi / 4
        holes.append(hole(0.5 * np.cos(ang), 0.5 * np.sin(ang), 0.08))

    gear_poly = Polygon(pts, holes=holes)
    gear = trimesh.creation.extrude_polygon(gear_poly, height=thickness)
    return gear


# ---------------------------------------------------------------------------
# 5. 초극상 — 트레포일 매듭 (high-res)
# ---------------------------------------------------------------------------
def make_ultra() -> trimesh.Trimesh:
    """(p,q)-torus knot. 고곡률 + 꼬임 + 고 resolution."""
    p, q = 3, 2  # trefoil knot
    n_spine = 512       # spine resolution
    n_section = 16      # tube 단면 해상도
    tube_r = 0.18

    t = np.linspace(0, 2 * np.pi, n_spine, endpoint=False)
    # parametric knot
    x = np.sin(t) + 2 * np.sin(p * t)
    y = np.cos(t) - 2 * np.cos(p * t)
    z = -np.sin(q * t)
    spine = np.column_stack([x, y, z])

    # Frenet frame — 접선/법선/종법선
    tangent = np.gradient(spine, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1, keepdims=True) + 1e-12
    # 임의의 up 벡터로 부터 normal
    up = np.array([0.0, 0.0, 1.0])
    normal = np.cross(tangent, np.tile(up, (n_spine, 1)))
    nm = np.linalg.norm(normal, axis=1, keepdims=True)
    nm[nm < 1e-9] = 1.0
    normal /= nm
    binorm = np.cross(tangent, normal)

    # 단면 원
    theta = np.linspace(0, 2 * np.pi, n_section, endpoint=False)
    circ = np.column_stack([np.cos(theta), np.sin(theta)])

    # 스윕
    verts = np.zeros((n_spine * n_section, 3), dtype=np.float64)
    for i in range(n_spine):
        center = spine[i]
        offs = (
            tube_r * circ[:, 0:1] * normal[i]
            + tube_r * circ[:, 1:2] * binorm[i]
        )
        verts[i * n_section:(i + 1) * n_section] = center + offs

    # 인덱스 (tube 토폴로지, spine은 closed loop)
    faces = []
    for i in range(n_spine):
        i2 = (i + 1) % n_spine
        for j in range(n_section):
            j2 = (j + 1) % n_section
            a = i * n_section + j
            b = i2 * n_section + j
            c = i2 * n_section + j2
            d = i * n_section + j2
            # two triangles per quad
            faces.append([a, b, c])
            faces.append([a, c, d])

    mesh = trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=True)
    # fix winding / fill (knot surface는 genus-1)
    mesh.fix_normals()
    return mesh


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"출력 디렉토리: {OUT_DIR}")
    print("─" * 72)

    builders = [
        ("01_easy_cube.stl",       "하 — 단순 박스",                make_easy),
        ("02_medium_cylinder.stl", "중 — 중공 실린더 (관통 홀)",    make_medium),
        ("03_hard_bracket.stl",    "상 — L-브래킷 + 볼트홀 3개",    make_hard),
        ("04_extreme_gear.stl",    "극상 — 20톱니 기어 + 샤프트홀", make_extreme),
        ("05_ultra_knot.stl",      "초극상 — 트레포일 매듭 (hi-res)", make_ultra),
    ]
    for fname, label, fn in builders:
        print(f"\n[{label}]")
        try:
            mesh = fn()
            _save(mesh, fname)
        except Exception as exc:
            print(f"  ✗ 실패: {exc}")

    print("\n─" * 72)
    print("완료. WildMesh 엔진으로 테스트하려면:")
    print(
        "  auto-tessell run tests/stl/01_easy_cube.stl "
        "-o out_case --quality draft --tier wildmesh"
    )


if __name__ == "__main__":
    main()
