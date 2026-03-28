"""
STL loading, bounding-box extraction, repair, and surface pre-processing.

Dependencies (MIT/LGPL, commercial-safe):
  trimesh  — pip install trimesh         (MIT)  — 로딩·수리·곡률 분석
  pyacvd   — pip install pyacvd          (MIT)  — 균일 surface remeshing
  pyvista  — pip install pyvista         (MIT)  — pyACVD 의존성
  open3d   — pip install open3d          (MIT)  — Poisson 표면 재구성
  (pure-Python fallback if any of the above is unavailable)
"""

import re
import struct
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# BBox
# ---------------------------------------------------------------------------

@dataclass
class BBox:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @property
    def size_x(self) -> float:
        return self.max_x - self.min_x

    @property
    def size_y(self) -> float:
        return self.max_y - self.min_y

    @property
    def size_z(self) -> float:
        return self.max_z - self.min_z

    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2

    @property
    def center_z(self) -> float:
        return (self.min_z + self.max_z) / 2

    @property
    def characteristic_length(self) -> float:
        """최장 bounding-box 치수 — CFD 도메인 크기 기준."""
        return max(self.size_x, self.size_y, self.size_z)

    def __repr__(self) -> str:
        return (
            f"BBox(min=({self.min_x:.4g}, {self.min_y:.4g}, {self.min_z:.4g}) "
            f"max=({self.max_x:.4g}, {self.max_y:.4g}, {self.max_z:.4g}) "
            f"L={self.characteristic_length:.4g})"
        )


# ---------------------------------------------------------------------------
# StlComplexity — 곡률 분석 결과 (snappyHexMesh 적응형 정밀화에 사용)
# ---------------------------------------------------------------------------

@dataclass
class StlComplexity:
    """
    STL 곡률 분석에서 도출된 기하학적 복잡도 지표.

    snappyHexMesh refinement 레벨과 feature angle 자동 설정에 사용.

    complexity_ratio 해석:
      > 10  : 복잡한 기하 (날카로운 엣지, 좁은 곡면, 항공기 trailing edge 등)
      3~10  : 중간 (일반 산업 부품)
      < 3   : 단순 (박스, 실린더, 큰 평면 위주)
    """
    mean_curvature: float
    p95_curvature: float
    complexity_ratio: float        # p95 / mean — 클수록 날카로운 특징이 많음
    resolve_feature_angle: float   # snappy resolveFeatureAngle (도)
    surface_refine_min: int        # refinementSurfaces 최소 레벨
    surface_refine_max: int        # refinementSurfaces 최대 레벨
    feature_refine_level: int      # feature edge 정밀화 레벨


# ---------------------------------------------------------------------------
# BBox extraction
# ---------------------------------------------------------------------------

def get_bbox(stl_path: Path) -> BBox:
    """
    STL 파일에서 bounding box 추출.
    trimesh가 있으면 사용, 없으면 pure-Python 파싱.
    """
    try:
        import trimesh
        mesh = trimesh.load(str(stl_path), force="mesh")
        lo, hi = mesh.bounds
        return BBox(lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])
    except ImportError:
        pass

    content = stl_path.read_bytes()
    if _is_ascii_stl(content):
        return _ascii_bbox(content)
    return _binary_bbox(content)


# ---------------------------------------------------------------------------
# Surface repair
# ---------------------------------------------------------------------------

def repair_stl_to_path(stl_path: Path, output_path: Path) -> bool:
    """
    trimesh로 STL 수리. 결과가 수밀(watertight)이면 True.
    trimesh 없으면 원본 복사 후 False.
    """
    try:
        import trimesh
        from trimesh import repair as tr
        mesh = trimesh.load(str(stl_path), force="mesh")
        tr.fill_holes(mesh)
        tr.fix_winding(mesh)
        tr.fix_normals(mesh)
        mesh.export(str(output_path))
        return mesh.is_watertight
    except ImportError:
        import shutil
        shutil.copy2(stl_path, output_path)
        return False


# ---------------------------------------------------------------------------
# Open3D Poisson 표면 재구성 (MIT)
# ---------------------------------------------------------------------------

def reconstruct_surface_poisson(
    stl_path: Path,
    output_path: Path,
    depth: int = 9,
    bbox: BBox | None = None,
) -> bool:
    """
    Open3D (MIT) Poisson surface reconstruction.

    trimesh 수리로도 해결 안 되는 심각하게 불량한 STL 처리용.
    열린/자기교차 표면을 점군에서 새로 재구성해 수밀 메쉬로 변환.

    depth: Poisson 해상도 (8=보통, 9=기본, 10=고해상도, 메모리 2배씩 증가)

    Returns:
        True  — 재구성 성공, output_path에 STL 저장
        False — open3d 미설치 또는 재구성 실패 (조용히 건너뜀)
    """
    try:
        import numpy as np
        import open3d as o3d
    except ImportError:
        return False

    try:
        mesh_o3d = o3d.io.read_triangle_mesh(str(stl_path))
        if len(mesh_o3d.vertices) == 0:
            return False

        mesh_o3d.compute_vertex_normals()

        # 점군 샘플링 — 원본 정점 수의 3배, 최소 10,000
        n_pts = max(10_000, len(mesh_o3d.vertices) * 3)
        pcd = mesh_o3d.sample_points_poisson_disk(number_of_points=n_pts)

        # 법선 추정 반경: 모델 크기의 1% (bbox 없으면 AABB에서 계산)
        if bbox is not None:
            normal_radius = bbox.characteristic_length * 0.01
        else:
            aabb = mesh_o3d.get_axis_aligned_bounding_box()
            ext = aabb.get_extent()
            normal_radius = float(max(ext)) * 0.01
        normal_radius = max(normal_radius, 1e-6)  # 영(0) 방지

        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(
                radius=normal_radius, max_nn=30
            )
        )
        pcd.orient_normals_consistent_tangent_plane(100)

        # Poisson 재구성
        recon, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=depth
        )

        # 경계 아티팩트 제거 (밀도 하위 10%)
        d = np.asarray(densities)
        recon.remove_vertices_by_mask(d < np.percentile(d, 10))
        recon.remove_degenerate_triangles()
        recon.remove_duplicated_triangles()
        recon.remove_unreferenced_vertices()

        if len(recon.vertices) == 0:
            return False

        o3d.io.write_triangle_mesh(str(output_path), recon)
        return True

    except Exception:
        return False


# ---------------------------------------------------------------------------
# pyACVD 균일 surface remeshing (MIT)
# ---------------------------------------------------------------------------

def remesh_surface_uniform(
    stl_path: Path,
    output_path: Path,
    target_points: int = 5000,
) -> bool:
    """
    pyACVD (MIT) Voronoi 기반 균일 surface remeshing.

    불규칙한 삼각형 분포 → 균일하고 잘 정형된 삼각형.
    모든 tier의 입력 품질을 향상시키는 공통 전처리.

    Returns:
        True  — remeshing 적용됨
        False — pyacvd/pyvista 미설치 또는 실패
    """
    try:
        import pyacvd
        import pyvista as pv
    except ImportError:
        return False

    try:
        mesh = pv.read(str(stl_path))
        clus = pyacvd.Clustering(mesh)
        clus.subdivide(3)
        clus.cluster(target_points)
        remeshed = clus.create_mesh()
        remeshed.save(str(output_path))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 곡률 기반 복잡도 분석 (trimesh)
# ---------------------------------------------------------------------------

def analyze_stl_complexity(stl_path: Path) -> StlComplexity:
    """
    STL 표면 곡률을 분석하여 snappyHexMesh 적응형 정밀화 파라미터 도출.

    trimesh discrete mean curvature + face adjacency angle을 사용.
    trimesh 미설치 시 안전한 기본값 반환.

    반환되는 StlComplexity는 openfoam_config.snappy_hex_mesh_dict()에 전달.
    """
    try:
        import numpy as np
        import trimesh

        mesh = trimesh.load(str(stl_path), force="mesh")

        # Discrete mean curvature (vertex-level)
        curv = trimesh.curvature.discrete_mean_curvature_measure(
            mesh, mesh.vertices, mesh.scale * 0.01
        )
        abs_c = np.abs(curv)
        mean_c = float(np.mean(abs_c))
        p95_c = float(np.percentile(abs_c, 95))
        ratio = p95_c / (mean_c + 1e-10)

        # Feature angle: 인접 face 간 dihedral angle 하위 10th percentile
        if len(mesh.face_adjacency_angles) > 0:
            angles_deg = np.degrees(mesh.face_adjacency_angles)
            feat_angle = float(np.clip(np.percentile(angles_deg, 10), 15.0, 60.0))
        else:
            feat_angle = 30.0

        # 복잡도 → 정밀화 레벨 매핑
        if ratio > 10:     # 복잡 (항공기 날개, 터빈 블레이드 등)
            s_min, s_max, feat = 2, 4, 4
            feat_angle = min(feat_angle, 20.0)
        elif ratio > 3:    # 중간 (일반 산업 부품)
            s_min, s_max, feat = 1, 3, 3
            feat_angle = min(feat_angle, 30.0)
        else:              # 단순 (박스, 실린더)
            s_min, s_max, feat = 1, 2, 2
            feat_angle = min(feat_angle, 40.0)

        return StlComplexity(
            mean_curvature=mean_c,
            p95_curvature=p95_c,
            complexity_ratio=ratio,
            resolve_feature_angle=feat_angle,
            surface_refine_min=s_min,
            surface_refine_max=s_max,
            feature_refine_level=feat,
        )

    except Exception:
        return StlComplexity(
            mean_curvature=0.0,
            p95_curvature=0.0,
            complexity_ratio=1.0,
            resolve_feature_angle=30.0,
            surface_refine_min=1,
            surface_refine_max=3,
            feature_refine_level=3,
        )


# ---------------------------------------------------------------------------
# Pure-Python STL parsers (no dependencies)
# ---------------------------------------------------------------------------

def _is_ascii_stl(content: bytes) -> bool:
    try:
        header = content[:256].decode("ascii", errors="strict").strip().lower()
        return header.startswith("solid")
    except (UnicodeDecodeError, ValueError):
        return False


def _ascii_bbox(content: bytes) -> BBox:
    text = content.decode("ascii", errors="replace")
    coords = re.findall(
        r"vertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)", text
    )
    if not coords:
        raise ValueError("ASCII STL에서 vertex를 찾을 수 없음")
    xs = [float(c[0]) for c in coords]
    ys = [float(c[1]) for c in coords]
    zs = [float(c[2]) for c in coords]
    return BBox(min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _binary_bbox(content: bytes) -> BBox:
    num_tri = struct.unpack_from("<I", content, 80)[0]
    inf = float("inf")
    min_x = min_y = min_z = inf
    max_x = max_y = max_z = -inf

    for i in range(num_tri):
        base = 84 + i * 50 + 12  # normal 12바이트 skip
        for v in range(3):
            x, y, z = struct.unpack_from("<3f", content, base + v * 12)
            if x < min_x: min_x = x
            if y < min_y: min_y = y
            if z < min_z: min_z = z
            if x > max_x: max_x = x
            if y > max_y: max_y = y
            if z > max_z: max_z = z

    return BBox(min_x, min_y, min_z, max_x, max_y, max_z)
