"""checkMesh 실행 및 stdout 파싱."""

from __future__ import annotations

import re
from pathlib import Path

from core.schemas import CheckMeshResult
from core.utils.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# 정규식 패턴
# ---------------------------------------------------------------------------

_RE_CELLS = re.compile(r"cells:\s+(\d+)")
_RE_FACES = re.compile(r"faces:\s+(\d+)")
_RE_POINTS = re.compile(r"points:\s+(\d+)")
_RE_INTERNAL_FACES = re.compile(r"internal faces:\s+(\d+)")
_RE_MAX_NON_ORTHO = re.compile(
    r"(?:Max non-orthogonality\s*=\s*|Mesh non-orthogonality Max:\s*)([\d.eE+\-]+)"
)
_RE_AVG_NON_ORTHO = re.compile(
    r"(?:average non-orthogonality\s*=\s*|average:\s*)([\d.eE+\-]+)"
)
_RE_MAX_SKEWNESS = re.compile(r"Max skewness\s*=\s*([\d.eE+\-]+)")
_RE_MAX_ASPECT = re.compile(r"Max aspect ratio\s*=\s*([\d.eE+\-]+)")
_RE_MIN_FACE_AREA = re.compile(r"Minimum face area\s*=\s*([\d.eE+\-]+)")
_RE_MIN_VOLUME = re.compile(r"Min volume\s*=\s*([\d.eE+\-]+)")
_RE_MIN_DETERMINANT = re.compile(r"Min determinant\s*=\s*([\d.eE+\-]+)")
_RE_NEGATIVE_VOLUMES = re.compile(r"\*\*\*Error:\s+(\d+)\s+negative volumes?", re.IGNORECASE)
_RE_SEVERELY_NON_ORTHO = re.compile(
    r"Number of severely non-orthogonal\b.*?faces:\s+(\d+)", re.IGNORECASE
)
_RE_FAILED_CHECKS = re.compile(r"Failed\s+(\d+)\s+mesh checks?", re.IGNORECASE)
_RE_MESH_OK = re.compile(r"Mesh OK\.", re.IGNORECASE)


class CheckMeshParser:
    """checkMesh stdout을 파싱해 CheckMeshResult를 반환하는 순수 파서."""

    def parse(self, stdout: str) -> CheckMeshResult:  # noqa: C901
        """checkMesh 표준 출력을 파싱한다.

        Args:
            stdout: checkMesh 프로세스의 표준 출력 문자열.

        Returns:
            파싱된 CheckMeshResult 객체.
        """

        def _int(pattern: re.Pattern[str], default: int = 0) -> int:
            m = pattern.search(stdout)
            return int(m.group(1)) if m else default

        def _float(pattern: re.Pattern[str], default: float = 0.0) -> float:
            m = pattern.search(stdout)
            return float(m.group(1).rstrip(".,;")) if m else default

        cells = _int(_RE_CELLS)
        faces = _int(_RE_FACES)
        points = _int(_RE_POINTS)
        max_non_ortho = _float(_RE_MAX_NON_ORTHO)
        avg_non_ortho = _float(_RE_AVG_NON_ORTHO)
        max_skewness = _float(_RE_MAX_SKEWNESS)
        max_aspect_ratio = _float(_RE_MAX_ASPECT)
        min_face_area = _float(_RE_MIN_FACE_AREA)
        min_cell_volume = _float(_RE_MIN_VOLUME, default=1.0)
        min_determinant = _float(_RE_MIN_DETERMINANT, default=1.0)
        negative_volumes = _int(_RE_NEGATIVE_VOLUMES)
        severely_non_ortho_faces = _int(_RE_SEVERELY_NON_ORTHO)
        failed_checks = _int(_RE_FAILED_CHECKS)
        mesh_ok = bool(_RE_MESH_OK.search(stdout))

        # "Failed N mesh checks." 가 있으면 mesh_ok 는 False
        if failed_checks > 0:
            mesh_ok = False

        result = CheckMeshResult(
            cells=cells,
            faces=faces,
            points=points,
            max_non_orthogonality=max_non_ortho,
            avg_non_orthogonality=avg_non_ortho,
            max_skewness=max_skewness,
            max_aspect_ratio=max_aspect_ratio,
            min_face_area=min_face_area,
            min_cell_volume=min_cell_volume,
            min_determinant=min_determinant,
            negative_volumes=negative_volumes,
            severely_non_ortho_faces=severely_non_ortho_faces,
            failed_checks=failed_checks,
            mesh_ok=mesh_ok,
        )
        log.debug("checkMesh parsed", mesh_ok=result.mesh_ok, failed_checks=result.failed_checks)
        return result


class MeshQualityChecker:
    """OpenFOAM checkMesh를 실행하고 결과를 파싱하는 클래스.

    ``prefer_native=True`` 로 생성하면 OpenFOAM 설치 여부와 무관하게
    ``NativeMeshChecker`` 를 직접 사용한다 (GUI의 Tier 5 "Native Python 검증"
    옵션에서 활용).
    """

    def __init__(
        self,
        parser: CheckMeshParser | None = None,
        *,
        prefer_native: bool = False,
    ) -> None:
        self._parser = parser or CheckMeshParser()
        self._prefer_native = prefer_native
        # 마지막 run 이 어떤 엔진을 사용했는지 기록 ("native" | "openfoam")
        self.last_engine_used: str | None = None

    def set_prefer_native(self, value: bool) -> None:
        """런타임에 native checker 우선 여부를 변경한다."""
        self._prefer_native = bool(value)

    def run(self, case_dir: Path) -> CheckMeshResult:
        """checkMesh -allGeometry -allTopology를 실행하고 결과를 반환한다.

        OpenFOAM이 없거나 ``prefer_native`` 가 True이면 NativeMeshChecker로 폴백.
        """
        if self._prefer_native:
            log.info("Using NativeMeshChecker (prefer_native=True)",
                     case_dir=str(case_dir))
            from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415
            self.last_engine_used = "native"
            return NativeMeshChecker().run(case_dir)
        try:
            result = self._run_openfoam(case_dir)
            self.last_engine_used = "openfoam"
            return result
        except FileNotFoundError:
            log.info(
                "OpenFOAM checkMesh not available, falling back to NativeMeshChecker",
                case_dir=str(case_dir),
            )
            from core.evaluator.native_checker import NativeMeshChecker  # noqa: PLC0415
            self.last_engine_used = "native"
            return NativeMeshChecker().run(case_dir)

    def _run_openfoam(self, case_dir: Path) -> CheckMeshResult:
        """Run OpenFOAM checkMesh and parse its stdout.

        Raises:
            FileNotFoundError: checkMesh 바이너리를 찾을 수 없을 때.
        """
        log.info("Running OpenFOAM checkMesh", case_dir=str(case_dir))

        try:
            from core.utils.openfoam_utils import OpenFOAMError, run_openfoam  # noqa: PLC0415
            proc = run_openfoam(
                "checkMesh", case_dir,
                args=["-allGeometry", "-allTopology"],
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"checkMesh 바이너리를 찾을 수 없습니다. OpenFOAM이 설치되어 있는지 확인하세요: {exc}"
            ) from exc
        except OpenFOAMError as exc:
            # checkMesh는 메쉬 불량 시 0이 아닌 종료코드를 반환할 수 있음
            # stdout/stderr를 파싱하여 결과를 반환한다
            log.info("checkMesh returned non-zero (expected for bad meshes)", returncode=exc.returncode)
            stdout = exc.stdout + "\n" + exc.stderr
            return self._parser.parse(stdout)

        stdout = proc.stdout + "\n" + proc.stderr
        log.debug("checkMesh stdout length", chars=len(stdout))
        return self._parser.parse(stdout)
