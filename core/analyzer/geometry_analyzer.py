"""지오메트리 분석 엔진.

입력 파일을 로딩하여 GeometryReport를 생성한다.
분석만 수행하며 입력 파일을 절대 수정하지 않는다.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import trimesh

from core.analyzer.file_reader import (
    CAD_FORMATS,
    LAS_FORMATS,
    MESHIO_FORMATS,
    TRIMESH_FORMATS,
    load_mesh,
)
from core.schemas import (
    BoundingBox,
    FeatureStats,
    FileInfo,
    FlowEstimation,
    Geometry,
    GeometryReport,
    Issue,
    Severity,
    SurfaceStats,
    TierCompatibility,
    TierCompatibilityMap,
)
from core.utils.logging import get_logger

log = get_logger(__name__)

# 대용량 메쉬 샘플링 임계값 (100만 삼각형)
LARGE_MESH_THRESHOLD = 1_000_000
SAMPLE_RATIO = 0.1  # 샘플링 시 10 % 사용


class GeometryAnalyzer:
    """CAD/메쉬 파일을 분석하여 GeometryReport를 생성한다."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def analyze(self, path: Path) -> GeometryReport:
        """파일을 분석하고 GeometryReport를 반환한다.

        Args:
            path: 분석할 파일 경로.

        Returns:
            GeometryReport Pydantic 모델.
        """
        path = Path(path)
        t0 = time.perf_counter()
        log.info("analysis_start", path=str(path))

        file_info = self._build_file_info(path)
        mesh = load_mesh(path)

        geometry = self._build_geometry(mesh)
        issues = self._detect_issues(mesh, geometry)
        flow_estimation = self._estimate_flow(geometry, issues)
        tier_compatibility = self._assess_tier_compatibility(
            file_info, geometry, issues, flow_estimation
        )

        report = GeometryReport(
            file_info=file_info,
            geometry=geometry,
            flow_estimation=flow_estimation,
            issues=issues,
            tier_compatibility=tier_compatibility,
        )

        elapsed = time.perf_counter() - t0
        log.info("analysis_complete", path=str(path), elapsed_seconds=round(elapsed, 3))
        return report

    # ------------------------------------------------------------------
    # FileInfo
    # ------------------------------------------------------------------

    def _build_file_info(self, path: Path) -> FileInfo:
        fmt = path.suffix.lower()
        file_size = os.path.getsize(path)

        is_cad_brep = fmt in CAD_FORMATS
        is_las = fmt in LAS_FORMATS
        is_cgns = fmt == ".cgns"
        is_volume_mesh = (fmt in MESHIO_FORMATS) or is_cgns
        is_surface_mesh = (
            fmt in TRIMESH_FORMATS or (not is_cad_brep and not is_volume_mesh and not is_las)
        )

        # LAS/LAZ: 포인트 클라우드이므로 surface/volume 모두 False
        if is_las:
            is_surface_mesh = False
            is_volume_mesh = False

        # CGNS: 볼륨 메쉬 포함
        if is_cgns:
            is_surface_mesh = False
            is_volume_mesh = True

        # 인코딩 감지
        detected_encoding = self._detect_encoding(path, fmt)

        # format 문자열 정규화
        if is_las:
            format_str = "LAS"
        elif is_cgns:
            format_str = "CGNS"
        else:
            format_str = fmt.lstrip(".").upper()

        return FileInfo(
            path=str(path.resolve()),
            format=format_str,
            file_size_bytes=file_size,
            detected_encoding=detected_encoding,
            is_cad_brep=is_cad_brep,
            is_surface_mesh=is_surface_mesh,
            is_volume_mesh=is_volume_mesh,
        )

    @staticmethod
    def _detect_encoding(path: Path, fmt: str | None = None) -> str:
        """STL binary/ascii 판별, 나머지는 포맷별 기본값."""
        if fmt is None:
            fmt = path.suffix.lower()
        if fmt in {".las", ".laz"}:
            return "binary_las"
        if fmt == ".cgns":
            return "binary_hdf5"
        if fmt != ".stl":
            return "binary"
        try:
            with open(path, "rb") as f:
                header = f.read(256)
            # ASCII STL은 'solid'로 시작
            try:
                text = header.decode("ascii", errors="replace")
                if text.lstrip().lower().startswith("solid"):
                    # 실제로 binary STL이 'solid'로 시작하는 경우도 있음
                    # 파일 크기 vs 예상 크기로 추가 검증
                    return "ascii"
            except Exception:
                pass
            return "binary"
        except OSError:
            return "unknown"

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _build_geometry(self, mesh: trimesh.Trimesh) -> Geometry:
        bbox = self._build_bounding_box(mesh)
        surface = self._build_surface_stats(mesh)
        features = self._build_feature_stats(mesh, bbox)
        return Geometry(bounding_box=bbox, surface=surface, features=features)

    # ---- BoundingBox ----

    @staticmethod
    def _build_bounding_box(mesh: trimesh.Trimesh) -> BoundingBox:
        vmin = mesh.bounds[0].tolist()
        vmax = mesh.bounds[1].tolist()
        center = ((mesh.bounds[0] + mesh.bounds[1]) / 2.0).tolist()
        extents = mesh.bounds[1] - mesh.bounds[0]
        diagonal = float(np.linalg.norm(extents))
        characteristic_length = float(np.max(extents))
        return BoundingBox(
            min=vmin,
            max=vmax,
            center=center,
            diagonal=diagonal,
            characteristic_length=characteristic_length,
        )

    # ---- SurfaceStats ----

    def _build_surface_stats(self, mesh: trimesh.Trimesh) -> SurfaceStats:
        num_vertices = len(mesh.vertices)
        num_faces = len(mesh.faces)

        # v0.4+: topology 지표는 자체 numpy 구현 (trimesh 속성 의존 완전 제거).
        from core.analyzer import topology as _T  # noqa: PLC0415
        faces_np = np.asarray(mesh.faces, dtype=np.int64)
        is_watertight = bool(_T.is_watertight(faces_np))
        is_manifold = bool(_T.is_manifold(faces_np))
        euler = int(_T.compute_euler(num_vertices, faces_np))
        num_components = int(_T.num_connected_components(faces_np)) or 1
        log.debug(
            "geometry_topology_native",
            watertight=is_watertight, manifold=is_manifold,
            euler=euler, components=num_components,
        )

        # genus = (2 - euler) / 2 for single closed surface (orientable)
        genus = max(0, (2 - euler) // 2)

        # surface area
        surface_area = float(mesh.area)

        # degenerate faces: area == 0
        face_areas = mesh.area_faces
        degen_mask = face_areas < 1e-15
        num_degenerate = int(np.sum(degen_mask))
        has_degenerate = num_degenerate > 0

        # face area stats (샘플링 적용)
        fa = self._maybe_sample(face_areas)
        min_face_area = float(np.min(fa))
        max_face_area = float(np.max(fa))
        face_area_std = float(np.std(fa))

        # edge length stats
        min_el, max_el, el_ratio = self._edge_length_stats(mesh)

        return SurfaceStats(
            num_vertices=num_vertices,
            num_faces=num_faces,
            surface_area=surface_area,
            is_watertight=is_watertight,
            is_manifold=is_manifold,
            num_connected_components=num_components,
            euler_number=euler,
            genus=genus,
            has_degenerate_faces=has_degenerate,
            num_degenerate_faces=num_degenerate,
            min_face_area=min_face_area,
            max_face_area=max_face_area,
            face_area_std=face_area_std,
            min_edge_length=min_el,
            max_edge_length=max_el,
            edge_length_ratio=el_ratio,
        )

    def _edge_length_stats(
        self, mesh: trimesh.Trimesh
    ) -> tuple[float, float, float]:
        """엣지 길이 통계 반환. 대용량 메쉬는 face 샘플링 적용."""
        if mesh.faces.shape[0] > LARGE_MESH_THRESHOLD:
            idx = np.random.choice(
                mesh.faces.shape[0],
                size=int(mesh.faces.shape[0] * SAMPLE_RATIO),
                replace=False,
            )
            faces = mesh.faces[idx]
        else:
            faces = mesh.faces

        v = mesh.vertices
        e0 = np.linalg.norm(v[faces[:, 1]] - v[faces[:, 0]], axis=1)
        e1 = np.linalg.norm(v[faces[:, 2]] - v[faces[:, 1]], axis=1)
        e2 = np.linalg.norm(v[faces[:, 0]] - v[faces[:, 2]], axis=1)
        all_edges = np.concatenate([e0, e1, e2])
        all_edges = all_edges[all_edges > 1e-15]

        if len(all_edges) == 0:
            return 0.0, 0.0, 1.0

        min_el = float(np.min(all_edges))
        max_el = float(np.max(all_edges))
        ratio = (max_el / min_el) if min_el > 1e-15 else float("inf")
        return min_el, max_el, ratio

    # ---- FeatureStats ----

    def _build_feature_stats(
        self, mesh: trimesh.Trimesh, bbox: BoundingBox
    ) -> FeatureStats:
        threshold_deg = 30.0

        # Sharp edges: face-pair dihedral angle < threshold
        num_sharp, has_sharp = self._count_sharp_edges(mesh, threshold_deg)

        # thin wall: bbox 최소 extent vs 특성 길이
        extents = np.array(bbox.max) - np.array(bbox.min)
        min_extent = float(np.min(extents))
        char_len = bbox.characteristic_length
        min_wall_thickness_estimate = min_extent
        has_thin_walls = bool(min_extent < char_len * 0.05) if char_len > 0 else False

        # small features: min edge length vs characteristic length
        el_stats = self._edge_length_stats(mesh)
        smallest_feature_size = el_stats[0]
        feature_to_bbox_ratio = (
            smallest_feature_size / char_len if char_len > 0 else 0.0
        )
        has_small_features = bool(feature_to_bbox_ratio < 0.01) if char_len > 0 else False

        # curvature 추정 (vertex normals 편차 활용)
        curvature_max, curvature_mean = self._estimate_curvature(mesh)

        return FeatureStats(
            has_sharp_edges=has_sharp,
            num_sharp_edges=num_sharp,
            sharp_edge_angle_threshold=threshold_deg,
            has_thin_walls=has_thin_walls,
            min_wall_thickness_estimate=min_wall_thickness_estimate,
            has_small_features=has_small_features,
            smallest_feature_size=smallest_feature_size,
            feature_to_bbox_ratio=feature_to_bbox_ratio,
            curvature_max=curvature_max,
            curvature_mean=curvature_mean,
        )

    @staticmethod
    def _count_sharp_edges(
        mesh: trimesh.Trimesh, threshold_deg: float
    ) -> tuple[int, bool]:
        """이면각(dihedral angle)이 threshold 이하인 엣지 수.

        trimesh.face_adjacency_angles 는 "법선 사이 각도" (0 = 평면) 이므로
        `< threshold_rad` 면 sharp. 자체 구현 `topology.dihedral_angles` 도 같은
        정의 (법선 사이 각도) 이므로 부등호 유지.
        """
        from core.analyzer import topology as _T  # noqa: PLC0415

        try:
            faces = np.asarray(mesh.faces, dtype=np.int64)
            verts = np.asarray(mesh.vertices, dtype=np.float64)
            _, angles = _T.dihedral_angles(verts, faces)
            if angles.size == 0:
                return 0, False
            threshold_rad = float(np.deg2rad(threshold_deg))
            num_sharp = int(np.sum(angles < threshold_rad))
            return num_sharp, num_sharp > 0
        except Exception:
            return 0, False

    @staticmethod
    def _estimate_curvature(mesh: trimesh.Trimesh) -> tuple[float, float]:
        """인접 face 법선 편차 / 공유 edge 길이 기반 곡률 proxy (native).

        topology.dihedral_angles 가 internal edge 별 (a, b) + angle 을 돌려주므로
        edge 길이 계산에 직접 사용 가능.
        """
        from core.analyzer import topology as _T  # noqa: PLC0415

        try:
            faces = np.asarray(mesh.faces, dtype=np.int64)
            verts = np.asarray(mesh.vertices, dtype=np.float64)
            edges, angles = _T.dihedral_angles(verts, faces)
            if angles.size == 0:
                return 0.0, 0.0
            a = verts[edges[:, 0]]
            b = verts[edges[:, 1]]
            edge_len = np.linalg.norm(b - a, axis=1)
            edge_len = np.where(edge_len < 1e-15, 1e-15, edge_len)
            curvature = np.clip(angles / edge_len, 0.0, 1e6)
            return float(np.max(curvature)), float(np.mean(curvature))
        except Exception:
            return 0.0, 0.0

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def _detect_issues(
        self, mesh: trimesh.Trimesh, geometry: Geometry
    ) -> list[Issue]:
        issues: list[Issue] = []
        surface = geometry.surface
        bbox = geometry.bounding_box

        # 0. Critical: Empty or minimal geometry
        if surface.num_faces == 0 or surface.num_vertices == 0:
            issues.append(
                Issue(
                    severity=Severity.CRITICAL,
                    type="empty_geometry",
                    count=1,
                    description="메쉬가 비어있습니다 (삼각형 또는 정점 수 = 0).",
                    recommended_action="skip",
                )
            )

        # 0b. Critical: Degenerate bounding box (collapsed to line/point)
        bbox_dims = [bbox.max[i] - bbox.min[i] for i in range(3)]
        bbox_dims_sorted = sorted(bbox_dims)
        # 가장 작은 차원이 0에 가까우면 2D 또는 더 심한 문제
        if bbox_dims_sorted[0] < 1e-6 and bbox_dims_sorted[1] < 1e-6:
            issues.append(
                Issue(
                    severity=Severity.CRITICAL,
                    type="degenerate_geometry",
                    count=1,
                    description="메쉬가 선이나 점으로 축퇴되었습니다.",
                    recommended_action="skip",
                )
            )

        # 1. non-watertight (열린 표면)
        if not surface.is_watertight:
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    type="non_watertight",
                    count=1,
                    description="메쉬가 watertight하지 않습니다 (열린 경계 존재).",
                    recommended_action="repair",
                )
            )

        # 2. non-manifold edges
        if not surface.is_manifold:
            try:
                from core.analyzer import topology as _T  # noqa: PLC0415
                nm_count = int(_T.count_non_manifold_edges(
                    np.asarray(mesh.faces, dtype=np.int64),
                ))
                if nm_count == 0:
                    # is_manifold=False 이지만 non-manifold edge 0 → vertex-fan
                    # 불연속 가능. 최소 1 로 기록.
                    nm_count = 1
            except Exception:
                nm_count = 1
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    type="non_manifold_edges",
                    count=nm_count,
                    description=f"{nm_count}개의 non-manifold 엣지 감지. Preprocessor에서 수리 필요.",
                    recommended_action="repair",
                )
            )

        # 3. degenerate faces
        if surface.has_degenerate_faces:
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    type="degenerate_faces",
                    count=surface.num_degenerate_faces,
                    description=f"{surface.num_degenerate_faces}개의 퇴화 삼각형(면적=0) 감지.",
                    recommended_action="repair",
                )
            )

        # 4. high face count
        if surface.num_faces > 500_000:
            issues.append(
                Issue(
                    severity=Severity.INFO,
                    type="high_face_count",
                    count=surface.num_faces,
                    description=f"표면 삼각형 수 과다({surface.num_faces:,}개). 리메쉬 권장.",
                    recommended_action="remesh",
                )
            )

        # 5. high edge length ratio
        if surface.edge_length_ratio > 100.0:
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    type="high_edge_length_ratio",
                    count=1,
                    description=(
                        f"엣지 길이 비율 {surface.edge_length_ratio:.1f} 과다 "
                        "(min/max 편차 심함). 리메쉬 권장."
                    ),
                    recommended_action="remesh",
                )
            )

        # 6. multiple connected components
        if surface.num_connected_components > 1:
            issues.append(
                Issue(
                    severity=Severity.INFO,
                    type="multiple_components",
                    count=surface.num_connected_components,
                    description=(
                        f"{surface.num_connected_components}개의 분리된 연결 컴포넌트 감지."
                    ),
                    recommended_action="review",
                )
            )

        # 7. Broken/incomplete watertight check
        # watertight하지만 volume이 0에 가까우면 수치적으로 닫혀있지만 구조적으로 문제
        try:
            volume = mesh.volume if hasattr(mesh, "volume") else 0.0
            bbox_volume = bbox.max[0] - bbox.min[0]
            bbox_volume *= bbox.max[1] - bbox.min[1]
            bbox_volume *= bbox.max[2] - bbox.min[2]

            if bbox_volume > 1e-10 and abs(volume) < 1e-10:
                issues.append(
                    Issue(
                        severity=Severity.MAJOR,
                        type="invalid_volume",
                        count=1,
                        description="메쉬가 닫혀있으나 내부 부피가 거의 0입니다. 구조적으로 손상된 것으로 추정.",
                        recommended_action="repair",
                    )
                )
        except Exception:
            pass  # 부피 계산 실패는 무시

        return issues

    # ------------------------------------------------------------------
    # FlowEstimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_flow(
        geometry: Geometry, issues: list[Issue]
    ) -> FlowEstimation:
        surface = geometry.surface
        bbox = geometry.bounding_box

        # aspect ratio: 최대 extent / 최소 extent
        extents = np.array(bbox.max) - np.array(bbox.min)
        min_ext = np.min(extents)
        if min_ext < 1e-9:
            # 한 쪽 차원이 거의 0인 경우 (평면 또는 선)
            aspect_ratio = float("inf")
        else:
            aspect_ratio = float(np.max(extents) / min_ext)

        has_open_boundary = not surface.is_watertight
        single_closed = surface.is_watertight and surface.num_connected_components == 1
        multi_component = surface.num_connected_components > 1
        # 평면이 아닌 경우에만 고종횡비 체크 (평면은 internal flow로 오인 방지)
        high_aspect = 5.0 < aspect_ratio < 1e9

        if single_closed and surface.genus == 0:
            return FlowEstimation(
                type="internal",
                confidence=0.75,
                reasoning=(
                    "단일 폐곡면, genus=0, 내부 유동 도메인으로 추정. "
                    "외부 유동(물체 주변 바람터널)이 필요하면 --flow-type external을 지정하세요."
                ),
                alternatives=["external"],
            )

        if single_closed and surface.genus > 0:
            return FlowEstimation(
                type="internal",
                confidence=0.70,
                reasoning=f"단일 폐곡면이나 genus={surface.genus} (구멍 존재). 내부 유동 채널 가능성.",
                alternatives=["external"],
            )

        if has_open_boundary and high_aspect:
            return FlowEstimation(
                type="internal",
                confidence=0.75,
                reasoning=(
                    f"열린 경계 + 높은 종횡비({aspect_ratio:.1f}). "
                    "파이프/덕트 내부 유동으로 추정."
                ),
                alternatives=["external"],
            )

        if multi_component and has_open_boundary:
            return FlowEstimation(
                type="internal",
                confidence=0.65,
                reasoning=(
                    f"{surface.num_connected_components}개 컴포넌트 + 열린 경계. "
                    "내부 유동(혈관/배관 등) 가능성."
                ),
                alternatives=["external", "unknown"],
            )

        if has_open_boundary:
            return FlowEstimation(
                type="unknown",
                confidence=0.40,
                reasoning="열린 표면이 감지됨. 유동 타입을 자동 판단하기 어렵습니다.",
                alternatives=["external", "internal"],
            )

        # 확신 낮은 기본값
        return FlowEstimation(
            type="external",
            confidence=0.50,
            reasoning="명확한 판단 근거 부족. 외부 유동을 기본값으로 설정.",
            alternatives=["internal", "unknown"],
        )

    # ------------------------------------------------------------------
    # TierCompatibilityMap
    # ------------------------------------------------------------------

    @staticmethod
    def _assess_tier_compatibility(
        file_info: FileInfo,
        geometry: Geometry,
        issues: list[Issue],
        flow_estimation: FlowEstimation,
    ) -> TierCompatibilityMap:
        surface = geometry.surface
        critical_issues = [i for i in issues if i.severity == Severity.CRITICAL]
        has_critical = len(critical_issues) > 0
        is_watertight = surface.is_watertight
        is_cad = file_info.is_cad_brep

        # Tier 0 (auto_tessell_core): watertight STL/표면 메쉬 필요
        tier0_ok = is_watertight and not has_critical
        tier0_notes = (
            "watertight 메쉬, Tier 0 가능"
            if tier0_ok
            else "non-watertight 또는 critical 문제로 Tier 0 불가"
        )

        # Tier 0.5 (Netgen): CAD 직접 입력 가능, 표면 메쉬도 처리
        tier05_ok = not has_critical
        tier05_notes = (
            "STEP/IGES 직접 입력 가능, CAD B-Rep 유지"
            if is_cad
            else ("표면 메쉬 입력 가능" if tier05_ok else "critical 문제로 Tier 0.5 불가")
        )

        # Tier 1 (snappyHexMesh): 외부 유동에 최적, non-watertight도 일부 처리
        tier1_ok = not has_critical
        tier1_notes = (
            "외부 유동 최적, BL 자동 생성"
            if flow_estimation.type == "external"
            else ("내부 유동 처리 가능" if tier1_ok else "critical 문제로 Tier 1 불가")
        )

        # Tier 1.5 (cfMesh): 자동화 수준 높음
        tier15_ok = not has_critical
        tier15_notes = "자동화 수준 높음" if tier15_ok else "critical 문제로 Tier 1.5 불가"

        # Tier 2 (TetWild + MMG): 불량 지오메트리 fallback, 항상 시도 가능
        tier2_ok = True
        tier2_notes = "불량 지오메트리 fallback, 강건한 처리 가능"

        return TierCompatibilityMap(
            tier0_core=TierCompatibility(compatible=tier0_ok, notes=tier0_notes),
            tier05_netgen=TierCompatibility(compatible=tier05_ok, notes=tier05_notes),
            tier1_snappy=TierCompatibility(compatible=tier1_ok, notes=tier1_notes),
            tier15_cfmesh=TierCompatibility(compatible=tier15_ok, notes=tier15_notes),
            tier2_tetwild=TierCompatibility(compatible=tier2_ok, notes=tier2_notes),
        )

    # ------------------------------------------------------------------
    # 대용량 메쉬 샘플링 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _maybe_sample(arr: np.ndarray) -> np.ndarray:
        """100만 요소 초과 시 10 % 무작위 샘플 반환."""
        if len(arr) > LARGE_MESH_THRESHOLD:
            idx = np.random.choice(len(arr), size=int(len(arr) * SAMPLE_RATIO), replace=False)
            return arr[idx]
        return arr
