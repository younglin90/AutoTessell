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
    """
    import numpy as np  # noqa: PLC0415

    if len(faces) == 0 or n_samples <= 0:
        return np.zeros((0, 3), dtype=np.float64)

    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    total = float(areas.sum())
    if total <= 0.0:
        return np.zeros((0, 3), dtype=np.float64)

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
    return (w0[:, None] * p0 + w1[:, None] * p1 + w2[:, None] * p2).astype(np.float64)


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

        # 3. Hausdorff 거리 계산 (점 샘플링 기반)
        hausdorff = self._compute_hausdorff(original, boundary)

        # 4. 표면적 편차
        area_deviation = (
            abs(boundary.area - original.area) / max(original.area, 1e-30) * 100.0
        )

        safe_diagonal = max(diagonal, 1e-30)
        hausdorff_relative = hausdorff / safe_diagonal

        log.info(
            "Geometry fidelity computed",
            hausdorff=hausdorff,
            hausdorff_relative=hausdorff_relative,
            area_deviation_percent=area_deviation,
        )

        return GeometryFidelity(
            hausdorff_distance=hausdorff,
            hausdorff_relative=hausdorff_relative,
            surface_area_deviation_percent=area_deviation,
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

        # 선택된 경계 패치의 face 인덱스 수집
        boundary_face_indices: list[int] = []
        for patch in selected_patches:
            start = int(patch["startFace"])
            n = int(patch["nFaces"])
            boundary_face_indices.extend(range(start, start + n))

        if not boundary_face_indices:
            log.debug("경계 패치 face 없음")
            return None

        # 폴리곤 → 삼각형 fan-triangulation
        triangles: list[list[int]] = []
        for fi in boundary_face_indices:
            if fi >= len(all_faces):
                continue
            verts = all_faces[fi]
            if len(verts) < 3:
                continue
            # fan triangulation: (0,1,2), (0,2,3), ...
            for k in range(1, len(verts) - 1):
                triangles.append([verts[0], verts[k], verts[k + 1]])

        if not triangles:
            return None

        tri_array = np.array(triangles, dtype=int)
        try:
            mesh = trimesh.Trimesh(vertices=vertices, faces=tri_array, process=False)
        except Exception as exc:  # noqa: BLE001
            log.warning("trimesh 생성 실패", error=str(exc))
            return None

        return mesh

    # ------------------------------------------------------------------
    # Hausdorff 거리 계산
    # ------------------------------------------------------------------

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
