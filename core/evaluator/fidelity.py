"""지오메트리 충실도 검증 — Hausdorff 거리 기반."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import trimesh

from core.schemas import GeometryFidelity
from core.utils.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# OpenFOAM polyMesh 파싱 헬퍼
# ---------------------------------------------------------------------------


def _read_foam_list(text: str) -> list[str]:
    """OpenFOAM 딕셔너리 포맷에서 괄호 목록 내용을 추출한다."""
    # 헤더 주석 제거
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    # 첫 번째 '(' ... ')' 블록 추출
    start = text.find("(")
    end = text.rfind(")")
    if start == -1 or end == -1:
        return []
    return text[start + 1 : end].split()


def _parse_foam_points(points_file: Path) -> list[list[float]]:
    """polyMesh/points 파일을 파싱해 좌표 목록으로 반환한다."""

    text = points_file.read_text()
    tokens = _read_foam_list(text)
    # 토큰 형식: (x y z) — 괄호 포함
    coords: list[list[float]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("("):
            # 한 토큰에 "(x" 형식
            x = float(tok.lstrip("(").rstrip(")"))
            y = float(tokens[i + 1].rstrip(")"))
            z = float(tokens[i + 2].rstrip(")"))
            coords.append([x, y, z])
            i += 3
        else:
            i += 1
    return coords


def _parse_foam_faces(faces_file: Path) -> list[list[int]]:
    """polyMesh/faces 파일을 파싱해 face 정점 인덱스 목록으로 반환한다."""
    text = faces_file.read_text()
    tokens = _read_foam_list(text)
    faces: list[list[int]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # 형식: N(v0 v1 ... vN-1)  또는  N (v0 ...)  — 모두 처리
        try:
            # "3(1" 형식 (N과 첫 인덱스가 붙어 있음)
            if "(" in tok:
                n_str, rest = tok.split("(", 1)
                n = int(n_str)
                verts: list[int] = []
                # rest 가 "v0" 또는 ""
                if rest.rstrip(")"):
                    verts.append(int(rest.strip("()")))
                i += 1
                while len(verts) < n:
                    t = tokens[i].strip("()")
                    if t:
                        verts.append(int(t))
                    i += 1
                faces.append(verts)
            else:
                # 순수 숫자 — 다음에 "(" 토큰이 온다
                n = int(tok)
                i += 1
                verts = []
                # 다음 토큰이 "(" 단독이거나 "(v0" 형태
                opening = tokens[i]
                if opening == "(":
                    i += 1
                else:
                    # "(v0" 형태
                    v = opening.lstrip("(").rstrip(")")
                    if v:
                        verts.append(int(v))
                    i += 1
                while len(verts) < n:
                    t = tokens[i].strip("()")
                    if t:
                        verts.append(int(t))
                    i += 1
                faces.append(verts)
        except (ValueError, IndexError):
            i += 1
    return faces


def _parse_foam_boundary(boundary_file: Path) -> list[dict[str, int | str]]:
    """polyMesh/boundary 파일을 파싱해 패치 정보(name, nFaces, startFace)를 반환한다."""
    text = boundary_file.read_text()
    # 주석 제거
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)

    patches: list[dict[str, int | str]] = []
    # 각 패치 블록: patchName { ... nFaces N; startFace M; ... }
    patch_blocks = re.findall(r"(\w[\w\s]*?)\s*\{([^}]+)\}", text, re.DOTALL)
    for name_raw, block in patch_blocks:
        nfaces_m = re.search(r"nFaces\s+(\d+)", block)
        startface_m = re.search(r"startFace\s+(\d+)", block)
        if nfaces_m and startface_m:
            patches.append(
                {
                    "name": name_raw.strip(),
                    "nFaces": int(nfaces_m.group(1)),
                    "startFace": int(startface_m.group(1)),
                }
            )
    return patches


def _select_geometry_patches(
    patches: list[dict[str, int | str]],
) -> list[dict[str, int | str]]:
    """원본 형상과 비교할 경계 패치만 선택한다.

    snappy/cfMesh 외부유동 케이스는 inlet/outlet/walls 같은 도메인 패치가
    함께 존재하므로, 형상 패치(surface/defaultWall/object 계열)를 우선 선택한다.
    """
    if len(patches) <= 1:
        return patches

    preferred_tokens = ("surface", "object", "body", "geom", "model", "solid", "wallobject")
    domain_tokens = (
        "inlet",
        "outlet",
        "farfield",
        "symmetry",
        "front",
        "back",
        "left",
        "right",
        "top",
        "bottom",
        "walls",
        "domain",
    )

    preferred = [
        patch
        for patch in patches
        if any(token in str(patch.get("name", "")).lower() for token in preferred_tokens)
    ]
    if preferred:
        return preferred

    non_domain = [
        patch
        for patch in patches
        if not any(token in str(patch.get("name", "")).lower() for token in domain_tokens)
    ]
    if non_domain:
        return non_domain

    default_wall = [
        patch for patch in patches if str(patch.get("name", "")).strip().lower() == "defaultwall"
    ]
    if default_wall:
        return default_wall

    return patches


# ---------------------------------------------------------------------------
# Native Hausdorff helpers (v0.4.0-beta11) — trimesh.sample / scipy.cKDTree 대체
# ---------------------------------------------------------------------------


def _native_sample_surface(
    vertices,
    faces,
    n_samples: int,
    seed: int = 0,
    return_index: bool = False,
):
    """면적 가중 barycentric sampling.

    trimesh.sample.sample_surface 의 numpy 전용 대체 구현.

    Args:
        vertices: (V, 3) float 배열.
        faces: (F, 3) int 배열 (삼각형).
        n_samples: 샘플 포인트 수.
        seed: numpy RNG seed (결정적 재현성 확보용).

    Returns:
        (n_samples, 3) float64 — 표면 상의 무작위 점.
        If ``return_index`` is true, also returns sampled face indices.
    """
    import numpy as np  # noqa: PLC0415

    if len(faces) == 0 or n_samples <= 0:
        pts = np.zeros((0, 3), dtype=np.float64)
        if return_index:
            return pts, np.zeros((0,), dtype=np.int64)
        return pts

    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    total = float(areas.sum())
    if total <= 0.0:
        pts = np.zeros((0, 3), dtype=np.float64)
        if return_index:
            return pts, np.zeros((0,), dtype=np.int64)
        return pts

    weights = areas / total
    rng = np.random.default_rng(seed)
    face_idx = rng.choice(len(faces), size=n_samples, p=weights)

    # barycentric uniform: (1-sqrt(r1))*v0 + sqrt(r1)*(1-r2)*v1 + sqrt(r1)*r2*v2
    r1 = rng.random(n_samples)
    r2 = rng.random(n_samples)
    sqrt_r1 = np.sqrt(r1)
    w0 = 1.0 - sqrt_r1
    w1 = sqrt_r1 * (1.0 - r2)
    w2 = sqrt_r1 * r2
    p0 = vertices[faces[face_idx, 0]]
    p1 = vertices[faces[face_idx, 1]]
    p2 = vertices[faces[face_idx, 2]]
    samples = (w0[:, None] * p0 + w1[:, None] * p1 + w2[:, None] * p2).astype(np.float64)
    if return_index:
        return samples, face_idx.astype(np.int64)
    return samples


def _native_kdist_chunked(
    query,
    reference,
    pair_limit: int = 10_000_000,
) -> float:
    """Max_{q in query} min_{r in reference} ||q-r|| — brute-force chunked.

    scipy.spatial.cKDTree.query 의 numpy-only 대체. M×N 쌍이 pair_limit 을
    넘지 않도록 query 를 청크로 나눠 반복.

    10M pair → float64 거리 행렬 ≈ 80MB (일시). 50k × 50k (2.5G) 경우에도
    청크 크기 200 으로 잘라 OK.
    """
    import numpy as np  # noqa: PLC0415

    m = len(query)
    n = len(reference)
    if m == 0 or n == 0:
        return 0.0

    chunk = max(1, pair_limit // max(n, 1))
    max_min_d2 = 0.0
    for start in range(0, m, chunk):
        end = min(start + chunk, m)
        diff = query[start:end, None, :] - reference[None, :, :]
        d2 = np.einsum("ijk,ijk->ij", diff, diff)
        local = float(d2.min(axis=1).max())
        if local > max_min_d2:
            max_min_d2 = local
    return float(np.sqrt(max_min_d2))


def _native_knn_chunked(
    query,
    reference,
    pair_limit: int = 10_000_000,
):
    """Return nearest-neighbour distances and reference indices."""
    import numpy as np  # noqa: PLC0415

    query = np.asarray(query, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    m = len(query)
    n = len(reference)
    if m == 0 or n == 0:
        return (
            np.zeros((m,), dtype=np.float64),
            np.zeros((m,), dtype=np.int64),
        )

    chunk = max(1, pair_limit // max(n, 1))
    out_d2 = np.empty((m,), dtype=np.float64)
    out_idx = np.empty((m,), dtype=np.int64)
    for start in range(0, m, chunk):
        end = min(start + chunk, m)
        diff = query[start:end, None, :] - reference[None, :, :]
        d2 = np.einsum("ijk,ijk->ij", diff, diff)
        idx = np.argmin(d2, axis=1)
        out_idx[start:end] = idx
        out_d2[start:end] = d2[np.arange(end - start), idx]
    return np.sqrt(out_d2), out_idx


# ---------------------------------------------------------------------------
# GeometryFidelityChecker
# ---------------------------------------------------------------------------


class GeometryFidelityChecker:
    """원본 STL과 polyMesh 경계면 사이의 Hausdorff 거리를 계산한다."""

    #: 샘플링 포인트 수 (Hausdorff 근사 정밀도와 속도의 균형)
    N_SAMPLES: int = 10_000

    def compute(
        self,
        original_stl: Path,
        case_dir: Path,
        diagonal: float,
    ) -> GeometryFidelity | None:
        """Hausdorff 거리와 표면적 편차를 계산한다.

        Args:
            original_stl: 원본 STL 파일 경로.
            case_dir: OpenFOAM case 디렉터리 경로.
            diagonal: 지오메트리 바운딩박스 대각선 길이 (상대 거리 정규화용).

        Returns:
            GeometryFidelity 객체. polyMesh 파싱 불가 또는 trimesh/scipy
            미설치 시 None 반환.
        """
        try:
            return self._compute_internal(original_stl, case_dir, diagonal)
        except ImportError as exc:
            log.warning("trimesh/scipy 미설치 — geometry fidelity 생략", error=str(exc))
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("geometry fidelity 계산 실패 (무시)", error=str(exc))
            return None

    # ------------------------------------------------------------------

    def _compute_internal(
        self,
        original_stl: Path,
        case_dir: Path,
        diagonal: float,
    ) -> GeometryFidelity:
        import trimesh  # noqa: PLC0415

        # 1. 원본 STL 로드
        original = trimesh.load(str(original_stl), force="mesh")
        if not isinstance(original, trimesh.Trimesh):
            raise ValueError(f"원본 STL 로드 실패: {original_stl}")

        # 2. polyMesh 경계면 추출
        boundary = self._extract_boundary_mesh(case_dir)
        if boundary is None:
            raise ValueError("polyMesh 경계면 추출 실패 — polyMesh 없거나 파싱 불가")

        # 3. Surface distance distribution (점 샘플링 기반)
        distance_stats = self._compute_surface_distance_stats(original, boundary)
        hausdorff = float(distance_stats["hausdorff_distance"])

        # 4. 표면적 편차
        area_deviation = (
            abs(boundary.area - original.area) / max(original.area, 1e-30) * 100.0
        )

        # beta2334 — pre-mesh self-intersect count (P2.6 chain).
        # 원본 STL 입력의 SI 검출. 결과 mesh quality 와 별도로 입력 품질
        # 신호 (사용자가 입력 강건도 평가 가능).
        import numpy as _np_si  # noqa: PLC0415
        n_si_pre: int | None = None
        try:
            if int(original.faces.shape[0]) <= 5000:
                from core.preprocessor.native_repair.self_intersect import (  # noqa: PLC0415
                    detect_self_intersections as _det_si,
                )
                _r_si = _det_si(
                    _np_si.asarray(original.vertices, dtype=_np_si.float64),
                    _np_si.asarray(original.faces, dtype=_np_si.int64),
                )
                n_si_pre = int(_r_si.n_intersections)
        except Exception:
            n_si_pre = None

        safe_diagonal = max(diagonal, 1e-30)
        hausdorff_relative = hausdorff / safe_diagonal

        log.info(
            "Geometry fidelity computed",
            hausdorff=hausdorff,
            hausdorff_relative=hausdorff_relative,
            area_deviation_percent=area_deviation,
            n_self_intersect_pre=n_si_pre,
        )

        return GeometryFidelity(
            hausdorff_distance=hausdorff,
            hausdorff_relative=hausdorff_relative,
            surface_area_deviation_percent=area_deviation,
            distance_rms=float(distance_stats["distance_rms"]),
            distance_p95=float(distance_stats["distance_p95"]),
            distance_p99=float(distance_stats["distance_p99"]),
            normal_deviation_max_deg=float(distance_stats["normal_deviation_max_deg"]),
            feature_preservation_score=float(distance_stats["feature_preservation_score"]),
            n_self_intersect_pre=n_si_pre,
        )

    # ------------------------------------------------------------------
    # polyMesh 경계면 추출
    # ------------------------------------------------------------------

    def _extract_boundary_mesh(self, case_dir: Path) -> trimesh.Trimesh | None:
        """polyMesh에서 경계면 삼각형 메쉬를 추출한다.

        constant/polyMesh/points, faces, boundary 파일을 읽어 경계 패치에
        해당하는 faces만 모아 trimesh.Trimesh를 생성한다.
        """
        import numpy as np  # noqa: PLC0415
        import trimesh  # noqa: PLC0415

        poly_mesh_dir = case_dir / "constant" / "polyMesh"
        if not poly_mesh_dir.is_dir():
            log.debug("polyMesh 디렉터리 없음", path=str(poly_mesh_dir))
            return None

        points_file = poly_mesh_dir / "points"
        faces_file = poly_mesh_dir / "faces"
        boundary_file = poly_mesh_dir / "boundary"

        for f in (points_file, faces_file, boundary_file):
            if not f.exists():
                log.debug("polyMesh 파일 없음", path=str(f))
                return None

        try:
            coords = _parse_foam_points(points_file)
            all_faces = _parse_foam_faces(faces_file)
            patches = _parse_foam_boundary(boundary_file)
        except Exception as exc:  # noqa: BLE001
            log.warning("polyMesh 파싱 오류", error=str(exc))
            return None

        if not coords or not patches:
            return None

        vertices = np.array(coords, dtype=float)

        selected_patches = _select_geometry_patches(patches)
        selected_names = [str(p.get("name", "")) for p in selected_patches]
        all_names = [str(p.get("name", "")) for p in patches]
        log.debug(
            "fidelity_patch_selection",
            total_patches=len(patches),
            selected_patches=len(selected_patches),
            all_patch_names=all_names,
            selected_patch_names=selected_names,
        )

        # 선택된 경계 패치의 face 인덱스 수집 (vectorized via numpy arange)
        index_parts: list[np.ndarray] = []
        for patch in selected_patches:
            start = int(patch["startFace"])
            n = int(patch["nFaces"])
            if n > 0:
                index_parts.append(np.arange(start, start + n, dtype=np.intp))
        if not index_parts:
            log.debug("경계 패치 face 없음")
            return None
        boundary_face_indices_arr = np.concatenate(index_parts)
        n_all = len(all_faces)
        boundary_face_indices_arr = boundary_face_indices_arr[
            boundary_face_indices_arr < n_all
        ]
        if boundary_face_indices_arr.size == 0:
            log.debug("경계 패치 face 없음")
            return None

        # 폴리곤 → 삼각형 fan-triangulation (size-grouped vectorize)
        # 폴리곤 크기별로 그룹화하여 numpy로 일괄 처리 (inner loop 제거).
        valid_faces = [all_faces[fi] for fi in boundary_face_indices_arr if len(all_faces[fi]) >= 3]
        tri_parts: list[np.ndarray] = []
        if valid_faces:
            from itertools import groupby  # noqa: PLC0415
            # 크기별 그룹
            sorted_faces = sorted(valid_faces, key=len)
            for poly_len, group in groupby(sorted_faces, key=len):
                group_list = list(group)
                # (M, poly_len) 배열로 stack
                face_arr = np.array(group_list, dtype=np.intp)  # (M, poly_len)
                # fan: k in 1..poly_len-2 → (poly_len-2) triangles per face
                v0 = face_arr[:, 0]  # (M,)
                for k in range(1, poly_len - 1):
                    tris = np.stack([v0, face_arr[:, k], face_arr[:, k + 1]], axis=1)
                    tri_parts.append(tris)
        if not tri_parts:
            return None

        tri_array = np.concatenate(tri_parts, axis=0)
        try:
            mesh = trimesh.Trimesh(vertices=vertices, faces=tri_array, process=False)
        except Exception as exc:  # noqa: BLE001
            log.warning("trimesh 생성 실패", error=str(exc))
            return None

        return mesh

    # ------------------------------------------------------------------
    # Hausdorff 거리 계산
    # ------------------------------------------------------------------

    def _compute_surface_distance_stats(
        self,
        mesh_a: trimesh.Trimesh,
        mesh_b: trimesh.Trimesh,
    ) -> dict[str, float]:
        """Sample bidirectional distances and normal deviation statistics."""
        import numpy as np  # noqa: PLC0415

        n = self.N_SAMPLES
        if mesh_a.area <= 0 or mesh_b.area <= 0:
            return {
                "hausdorff_distance": 0.0,
                "distance_rms": 0.0,
                "distance_p95": 0.0,
                "distance_p99": 0.0,
                "normal_deviation_max_deg": 0.0,
                "feature_preservation_score": 1.0,
            }

        try:
            samples_a, face_idx_a = _native_sample_surface(
                np.asarray(mesh_a.vertices, dtype=np.float64),
                np.asarray(mesh_a.faces, dtype=np.int64),
                n_samples=n,
                seed=0,
                return_index=True,
            )
            samples_b, face_idx_b = _native_sample_surface(
                np.asarray(mesh_b.vertices, dtype=np.float64),
                np.asarray(mesh_b.faces, dtype=np.int64),
                n_samples=n,
                seed=1,
                return_index=True,
            )
            d_ab, nn_ab = _native_knn_chunked(samples_a, samples_b)
            d_ba, nn_ba = _native_knn_chunked(samples_b, samples_a)
        except Exception as exc:  # noqa: BLE001
            log.info("surface_distance_native_failed_falling_back", error=str(exc))
            from scipy.spatial import cKDTree  # noqa: PLC0415

            samples_a, face_idx_a = mesh_a.sample(n, return_index=True)
            samples_b, face_idx_b = mesh_b.sample(n, return_index=True)
            samples_a = np.asarray(samples_a, dtype=np.float64)
            samples_b = np.asarray(samples_b, dtype=np.float64)
            face_idx_a = np.asarray(face_idx_a, dtype=np.int64)
            face_idx_b = np.asarray(face_idx_b, dtype=np.int64)
            tree_b = cKDTree(samples_b)
            d_ab, nn_ab = tree_b.query(samples_a)
            tree_a = cKDTree(samples_a)
            d_ba, nn_ba = tree_a.query(samples_b)

        all_d = np.concatenate([np.asarray(d_ab), np.asarray(d_ba)])
        if all_d.size == 0:
            all_d = np.zeros((1,), dtype=np.float64)

        normal_angles: list[np.ndarray] = []
        try:
            normals_a = np.asarray(mesh_a.face_normals, dtype=np.float64)
            normals_b = np.asarray(mesh_b.face_normals, dtype=np.float64)
            if normals_a.size and normals_b.size and len(face_idx_a) and len(face_idx_b):
                na = normals_a[np.asarray(face_idx_a, dtype=np.int64)]
                nb = normals_b[np.asarray(face_idx_b, dtype=np.int64)[np.asarray(nn_ab, dtype=np.int64)]]
                dot_ab = np.clip(np.abs(np.einsum("ij,ij->i", na, nb)), 0.0, 1.0)
                normal_angles.append(np.degrees(np.arccos(dot_ab)))

                nb2 = normals_b[np.asarray(face_idx_b, dtype=np.int64)]
                na2 = normals_a[np.asarray(face_idx_a, dtype=np.int64)[np.asarray(nn_ba, dtype=np.int64)]]
                dot_ba = np.clip(np.abs(np.einsum("ij,ij->i", nb2, na2)), 0.0, 1.0)
                normal_angles.append(np.degrees(np.arccos(dot_ba)))
        except Exception:
            normal_angles = []

        if normal_angles:
            all_angles = np.concatenate(normal_angles)
            normal_max = float(np.nanmax(all_angles)) if all_angles.size else 0.0
            normal_p95 = float(np.nanpercentile(all_angles, 95)) if all_angles.size else 0.0
        else:
            normal_max = 0.0
            normal_p95 = 0.0

        feature_score = float(np.clip(1.0 - normal_p95 / 90.0, 0.0, 1.0))
        return {
            "hausdorff_distance": float(np.nanmax(all_d)),
            "distance_rms": float(np.sqrt(np.nanmean(all_d * all_d))),
            "distance_p95": float(np.nanpercentile(all_d, 95)),
            "distance_p99": float(np.nanpercentile(all_d, 99)),
            "normal_deviation_max_deg": normal_max,
            "feature_preservation_score": feature_score,
        }

    def _compute_hausdorff(
        self,
        mesh_a: trimesh.Trimesh,
        mesh_b: trimesh.Trimesh,
    ) -> float:
        """두 메쉬 사이의 양방향 Hausdorff 거리를 계산한다.

        v0.4.0-beta11: trimesh.sample / scipy.cKDTree 의존 제거.
        numpy 기반 면적 가중 barycentric sampling + chunked brute-force kNN 으로
        교체. 결과값은 기존 대비 ±5% 드리프트 수준 (sampling seed 차이 때문).

        우선 자체 구현 시도 → ImportError 혹은 예외 시 기존 trimesh+scipy
        경로로 graceful fallback.
        """
        import numpy as np  # noqa: PLC0415

        n = self.N_SAMPLES
        if mesh_a.area <= 0 or mesh_b.area <= 0:
            return 0.0

        try:
            samples_a = _native_sample_surface(
                np.asarray(mesh_a.vertices, dtype=np.float64),
                np.asarray(mesh_a.faces, dtype=np.int64),
                n_samples=n,
            )
            samples_b = _native_sample_surface(
                np.asarray(mesh_b.vertices, dtype=np.float64),
                np.asarray(mesh_b.faces, dtype=np.int64),
                n_samples=n,
            )
            d_ab = _native_kdist_chunked(samples_a, samples_b)
            d_ba = _native_kdist_chunked(samples_b, samples_a)
            return float(max(d_ab, d_ba))
        except Exception as exc:  # noqa: BLE001
            # trimesh + scipy fallback (환경 문제 대비).
            log.info(
                "hausdorff_native_failed_falling_back",
                error=str(exc),
            )
            from scipy.spatial import cKDTree  # noqa: PLC0415
            samples_a, _ = mesh_a.sample(n, return_index=True)
            samples_b, _ = mesh_b.sample(n, return_index=True)
            samples_a = np.asarray(samples_a)
            samples_b = np.asarray(samples_b)
            tree_b = cKDTree(samples_b)
            dists_a, _ = tree_b.query(samples_a)
            tree_a = cKDTree(samples_a)
            dists_b, _ = tree_a.query(samples_b)
            return float(max(dists_a.max(), dists_b.max()))
