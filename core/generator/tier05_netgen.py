"""Tier 0.5: Netgen/ngsolve 메쉬 생성기."""

from __future__ import annotations

import contextlib
import io
import os
import time
from pathlib import Path

from core.schemas import MeshStrategy, TierAttempt
from core.utils.errors import format_missing_dependency_message
from core.utils.logging import get_logger
from core.utils.openfoam_utils import OpenFOAMError, run_openfoam

logger = get_logger(__name__)

TIER_NAME = "tier05_netgen"

# CAD 파일 확장자 (패스스루 지원)
_CAD_EXTENSIONS = {".step", ".stp", ".iges", ".igs", ".brep", ".brp"}


class Tier05NetgenGenerator:
    """Netgen/ngsolve 기반 테트라헤드럴 메쉬 생성기.

    STEP/IGES CAD 파일을 직접 읽어 고품질 tet 메쉬를 생성한다.
    STL 입력 시 STLGeometry를 사용한다.
    결과는 Gmsh2 포맷으로 export 후 gmshToFoam으로 변환한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """Tier 0.5 메쉬 생성을 실행한다.

        Args:
            strategy: Strategist가 생성한 메쉬 전략.
            preprocessed_path: 전처리된 STL 또는 CAD 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt. 실패 시 status="failed".
        """
        t_start = time.monotonic()
        logger.info("tier05_netgen_start", preprocessed_path=str(preprocessed_path))

        # netgen 모듈 import 시도
        try:
            import netgen.meshing as nm  # noqa: F401
            from netgen.occ import OCCGeometry  # noqa: F401
            from netgen.stl import STLGeometry  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier05_netgen_import_failed",
                error=str(exc),
                hint="netgen/ngsolve 미설치. 'pip install netgen-mesher' 또는 패키지 매니저 사용.",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="netgen",
                    fallback="MeshPy/cfMesh/TetWild fallback",
                    action="pip install netgen-mesher",
                    detail=str(exc),
                ),
            )

        # 파일 존재 확인
        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        # 메쉬 생성 실행
        try:
            params = strategy.tier_specific_params
            maxh = strategy.surface_mesh.target_cell_size
            minh = strategy.surface_mesh.min_cell_size
            grading = params.get("netgen_grading", 0.3)
            curvaturesafety = params.get("netgen_curvaturesafety", 2.0)
            segmentsperedge = params.get("netgen_segmentsperedge", 1.0)
            # GUI에서 직접 설정 가능 (0 = 근접 엣지 검출 비활성화)
            user_closeedgefac = params.get("netgen_closeedgefac", None)

            is_cad = preprocessed_path.suffix.lower() in _CAD_EXTENSIONS

            logger.info(
                "tier05_netgen_meshing",
                is_cad=is_cad,
                maxh=maxh,
                minh=minh,
                grading=grading,
            )

            if is_cad:
                # CAD 파일: sewing + tolerance 수정 시도 (cadquery)
                cad_path = self._preprocess_cad_geometry(preprocessed_path)
                geo = OCCGeometry(str(cad_path))
                if cad_path != preprocessed_path:
                    logger.info("cad_preprocessed", method="cadquery_clean", src=str(preprocessed_path))
            else:
                geo = STLGeometry(str(preprocessed_path))

            # Netgen C++ 라이브러리가 stdout/stderr로 직접 출력하므로
            # fd-level 리다이렉트로 억제한다 (Python redirect_stdout으로는 불충분)
            #
            # 어려운 형상에서 "too many attempts in domain 1" 예외가 발생하므로
            # 파라미터를 점진적으로 완화하며 최대 3회 재시도한다.
            # closeedgefac=0 → 근접 엣지 검출 비활성화 (주요 원인 제거)
            # 사용자가 closeedgefac을 명시한 경우 1회만 시도, 아니면 3단계 재시도
            if user_closeedgefac is not None:
                retry_configs = [
                    (grading, curvaturesafety, float(user_closeedgefac), 1.0, True),
                ]
            else:
                retry_configs = [
                    # (grading, curvaturesafety, closeedgefac, maxh_factor, uselocalh)
                    (grading, curvaturesafety, 2.0, 1.0, True),   # attempt 1: original
                    (0.5,     1.0,             0,   1.0, False),   # attempt 2: no close-edge
                    (0.7,     1.0,             0,   2.0, False),   # attempt 3: coarse
                ]

            mesh = None
            last_exc: Exception | None = None
            for attempt, (g, cs, cef, maxh_factor, localh) in enumerate(retry_configs, 1):
                try:
                    mp_kwargs: dict = dict(
                        maxh=maxh * maxh_factor,
                        grading=g,
                        curvaturesafety=cs,
                        segmentsperedge=segmentsperedge,
                        uselocalh=localh,
                    )
                    if cef > 0:
                        mp_kwargs["closeedgefac"] = cef

                    logger.info("tier05_netgen_attempt", attempt=attempt, **mp_kwargs)

                    with _suppress_c_output():
                        mesh = geo.GenerateMesh(**mp_kwargs)

                    logger.info("tier05_netgen_attempt_success", attempt=attempt)
                    break
                except TypeError as te:
                    # 이 버전의 Netgen이 특정 kwarg를 지원하지 않는 경우
                    # uselocalh / closeedgefac 을 제거하고 재시도
                    logger.warning(
                        "tier05_netgen_kwarg_unsupported",
                        attempt=attempt,
                        error=str(te),
                    )
                    try:
                        mp_kwargs.pop("uselocalh", None)
                        mp_kwargs.pop("closeedgefac", None)
                        with _suppress_c_output():
                            mesh = geo.GenerateMesh(**mp_kwargs)
                        logger.info("tier05_netgen_attempt_success_reduced_kwargs", attempt=attempt)
                        break
                    except Exception as exc2:
                        last_exc = exc2
                        logger.warning(
                            "tier05_netgen_attempt_failed",
                            attempt=attempt,
                            error=str(exc2),
                        )
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "tier05_netgen_attempt_failed",
                        attempt=attempt,
                        error=str(exc),
                    )

            if mesh is None:
                raise last_exc or RuntimeError("Netgen: all meshing attempts failed")

            # Gmsh2 포맷으로 export
            msh_path = case_dir / "netgen_mesh.msh"
            mesh.Export(str(msh_path), "Gmsh2 Format")

            logger.info("tier05_netgen_msh_exported", path=str(msh_path))

            # gmshToFoam으로 polyMesh 변환 (OpenFOAM 미설치 시 PolyMeshWriter fallback)
            try:
                run_openfoam("gmshToFoam", case_dir, args=[str(msh_path)])
                logger.info("tier05_netgen_gmshtfoam_done")
            except (OpenFOAMError, FileNotFoundError) as gmsh_exc:
                logger.info(
                    "tier05_netgen_gmshtfoam_unavailable",
                    reason=str(gmsh_exc),
                    fallback="PolyMeshWriter",
                )
                import meshio as _meshio
                msh_data = _meshio.read(str(msh_path))
                tets = None
                for cb in msh_data.cells:
                    if cb.type == "tetra":
                        tets = cb.data
                        break
                if tets is None:
                    raise RuntimeError("No tetra cells found in Netgen mesh export")
                from core.generator.polymesh_writer import PolyMeshWriter
                writer = PolyMeshWriter()
                writer.write(msh_data.points, tets, case_dir)
                logger.info("tier05_netgen_polymesh_writer_done")

            elapsed = time.monotonic() - t_start
            logger.info("tier05_netgen_success", elapsed=elapsed)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier05_netgen_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier 0.5 실행 실패: {exc}",
            )

    @staticmethod
    def _preprocess_cad_geometry(cad_path: Path) -> Path:
        """CAD 파일 전처리: sewing + tolerance 수정 (cadquery).

        cadquery가 설치된 경우 STEP/IGES를 로드해 .clean()을 적용하고
        일시 파일로 저장. 실패 시 원본 경로 반환 (passthrough).

        Args:
            cad_path: 입력 STEP/IGES 파일 경로.

        Returns:
            전처리된 CAD 파일 경로 (또는 원본 경로).
        """
        try:
            import cadquery as cq

            logger.info("cad_sewing_start", input_path=str(cad_path))

            # STEP/IGES 로드
            if cad_path.suffix.lower() == ".brep":
                shape = cq.importers.importBrep(str(cad_path))
            else:
                # STEP (.step, .stp) 또는 IGES (.iges, .igs)
                shape = cq.importers.importStep(str(cad_path))

            # Sewing + 불필요한 엣지 제거
            shape = shape.clean()

            # 일시 파일로 저장
            output_path = cad_path.parent / f"{cad_path.stem}_sewed{cad_path.suffix}"
            cq.exporters.export(shape, str(output_path), "STEP")

            logger.info("cad_sewing_done", output_path=str(output_path))
            return output_path

        except ImportError:
            logger.debug(
                "cadquery_unavailable",
                msg="cadquery 미설치 — CAD sewing 건너뜀. Netgen이 직접 처리.",
                input_path=str(cad_path),
            )
            return cad_path

        except Exception as exc:
            logger.warning(
                "cad_sewing_failed",
                error=str(exc),
                fallback="원본 CAD 파일 사용",
            )
            return cad_path


@contextlib.contextmanager
def _suppress_c_output():
    """Netgen C++ 라이브러리의 fd-level stdout/stderr 출력을 억제한다.

    Python의 redirect_stdout은 C 확장의 직접 write(1, ...) 호출을 막지 못하므로
    os.dup2로 fd 1/2를 /dev/null로 교체한다.
    """
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout = os.dup(1)
    saved_stderr = os.dup(2)
    try:
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)
        yield
    finally:
        os.dup2(saved_stdout, 1)
        os.dup2(saved_stderr, 2)
        os.close(saved_stdout)
        os.close(saved_stderr)
