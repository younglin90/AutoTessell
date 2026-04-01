"""지오메트리 충실도 검증 — Hausdorff 거리 기반."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

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


def _parse_foam_points(points_file: Path) -> "list[list[float]]":
    """polyMesh/points 파일을 파싱해 좌표 목록으로 반환한다."""
    import numpy as np  # noqa: PLC0415

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


def _parse_foam_faces(faces_file: Path) -> "list[list[int]]":
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


def _parse_foam_boundary(boundary_file: Path) -> list[dict]:
    """polyMesh/boundary 파일을 파싱해 패치 정보(nFaces, startFace)를 반환한다."""
    text = boundary_file.read_text()
    # 주석 제거
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)

    patches: list[dict] = []
    # 각 패치 블록: patchName\n{\n ... nFaces N; startFace M; ... \n}
    patch_blocks = re.findall(
        r"\w[\w\s]*?\{([^}]+)\}",
        text,
        re.DOTALL,
    )
    for block in patch_blocks:
        nfaces_m = re.search(r"nFaces\s+(\d+)", block)
        startface_m = re.search(r"startFace\s+(\d+)", block)
        if nfaces_m and startface_m:
            patches.append(
                {
                    "nFaces": int(nfaces_m.group(1)),
                    "startFace": int(startface_m.group(1)),
                }
            )
    return patches


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

    def _extract_boundary_mesh(self, case_dir: Path) -> "trimesh.Trimesh | None":
        """polyMesh에서 경계면 삼각형 메쉬를 추출한다.

        constant/polyMesh/points, faces, boundary 파일을 읽어 경계 패치에
        해당하는 faces만 모아 trimesh.Trimesh를 생성한다.
        """
        import trimesh  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

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

        # 경계 패치의 face 인덱스 수집
        boundary_face_indices: list[int] = []
        for patch in patches:
            start = patch["startFace"]
            n = patch["nFaces"]
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
        mesh_a: "trimesh.Trimesh",
        mesh_b: "trimesh.Trimesh",
    ) -> float:
        """두 메쉬 사이의 양방향 Hausdorff 거리를 계산한다.

        trimesh.sample.sample_surface로 포인트를 샘플링한 뒤
        scipy.spatial.cKDTree로 최근접 거리를 구한다.
        """
        from scipy.spatial import cKDTree  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        n = self.N_SAMPLES

        # 면적이 0이면 샘플링 불가
        if mesh_a.area <= 0 or mesh_b.area <= 0:
            return 0.0

        samples_a, _ = mesh_a.sample(n, return_index=True)
        samples_b, _ = mesh_b.sample(n, return_index=True)

        samples_a = np.asarray(samples_a)
        samples_b = np.asarray(samples_b)

        tree_b = cKDTree(samples_b)
        dists_a, _ = tree_b.query(samples_a)

        tree_a = cKDTree(samples_a)
        dists_b, _ = tree_a.query(samples_b)

        return float(max(dists_a.max(), dists_b.max()))
