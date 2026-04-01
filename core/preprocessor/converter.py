"""포맷 변환 모듈.

STL이 아닌 입력 포맷을 STL로 변환한다.
STEP/IGES는 cadquery가 필요하며, 미설치 시 NotImplementedError를 발생시킨다.
"""

from __future__ import annotations

from pathlib import Path

import trimesh

from core.utils.logging import get_logger

log = get_logger(__name__)

# trimesh 직접 변환 가능 포맷 (STL 제외)
_TRIMESH_CONVERTIBLE: frozenset[str] = frozenset(
    {".obj", ".ply", ".off", ".3mf", ".glb", ".gltf", ".dae"}
)

# CAD B-Rep 포맷
_CAD_FORMATS: frozenset[str] = frozenset(
    {".step", ".stp", ".iges", ".igs", ".brep"}
)

# meshio 변환 포맷
_MESHIO_CONVERTIBLE: frozenset[str] = frozenset(
    {".msh", ".vtu", ".vtk", ".vtp", ".xdmf", ".xmf", ".nas", ".bdf", ".inp"}
)


class FormatConverter:
    """입력 포맷 → STL 변환기."""

    def needs_conversion(self, path: Path) -> bool:
        """STL 변환이 필요한 포맷인지 확인.

        Args:
            path: 입력 파일 경로.

        Returns:
            True이면 변환 필요.
        """
        suffix = path.suffix.lower()
        return suffix != ".stl"

    def convert_to_stl(self, path: Path, output_dir: Path) -> Path:
        """입력 파일을 STL로 변환한다.

        Args:
            path: 입력 파일 경로.
            output_dir: 출력 디렉터리.

        Returns:
            변환된 STL 파일 경로 (STL이면 원본 경로 반환).

        Raises:
            NotImplementedError: STEP/IGES/BREP 변환 시 cadquery 미설치.
            ValueError: 지원하지 않는 포맷.
        """
        suffix = path.suffix.lower()

        if suffix == ".stl":
            log.info("convert_passthrough", path=str(path), reason="already STL")
            return path

        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / (path.stem + "_converted.stl")

        if suffix in _CAD_FORMATS:
            return self._convert_cad(path, out_path)

        if suffix in _TRIMESH_CONVERTIBLE:
            return self._convert_via_trimesh(path, out_path)

        if suffix in _MESHIO_CONVERTIBLE:
            return self._convert_via_meshio(path, out_path)

        raise ValueError(
            f"지원하지 않는 변환 포맷: {suffix} (파일: {path})"
        )

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _convert_cad(self, path: Path, out_path: Path) -> Path:
        """STEP/IGES/BREP → STL 변환.

        cadquery 또는 gmsh를 사용한다.
        미설치 환경에서는 NotImplementedError를 발생시킨다.
        """
        suffix = path.suffix.lower()
        log.info("convert_cad_start", path=str(path), format=suffix)

        # cadquery 시도
        try:
            import cadquery as cq  # type: ignore[import]

            if suffix in (".step", ".stp"):
                shape = cq.importers.importStep(str(path))
            elif suffix in (".iges", ".igs"):
                shape = cq.importers.importStep(str(path))  # cadquery IGES 지원 제한
            else:
                raise NotImplementedError(f"cadquery로 {suffix} 변환 미지원")

            cq.exporters.export(shape, str(out_path))
            log.info("convert_cad_done_cadquery", output=str(out_path))
            return out_path

        except ImportError:
            pass
        except NotImplementedError:
            raise

        # gmsh CLI fallback
        try:
            import subprocess
            result = subprocess.run(
                ["gmsh", str(path), "-2", "-o", str(out_path), "-format", "stl"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and out_path.exists():
                log.info("convert_cad_done_gmsh", output=str(out_path))
                return out_path
            log.warning(
                "gmsh_failed",
                returncode=result.returncode,
                stderr=result.stderr[:500],
            )
        except (FileNotFoundError, Exception) as exc:
            log.warning("gmsh_unavailable", error=str(exc))

        raise NotImplementedError(
            f"CAD 포맷({suffix}) 변환에는 cadquery 또는 gmsh가 필요합니다. "
            "설치 후 재시도하거나 --tier netgen 옵션을 사용하세요."
        )

    def _convert_via_trimesh(self, path: Path, out_path: Path) -> Path:
        """OBJ/PLY/OFF 등 trimesh 직접 변환."""
        log.info("convert_trimesh_start", path=str(path))
        try:
            result = trimesh.load(str(path), force="mesh")
            if isinstance(result, trimesh.Scene):
                if len(result.geometry) == 0:
                    raise ValueError("빈 Scene")
                meshes = list(result.geometry.values())
                result = trimesh.util.concatenate(meshes)
            result.export(str(out_path))
            log.info(
                "convert_trimesh_done",
                output=str(out_path),
                num_faces=len(result.faces),
            )
            return out_path
        except Exception as exc:
            raise ValueError(
                f"trimesh 변환 실패 [{path.suffix}]: {path}\n원인: {exc}"
            ) from exc

    def _convert_via_meshio(self, path: Path, out_path: Path) -> Path:
        """meshio 기반 변환 (볼륨 메쉬 → 표면 추출 → STL)."""
        log.info("convert_meshio_start", path=str(path))
        try:
            import meshio  # type: ignore[import]
            import numpy as np

            mesh = meshio.read(str(path))
            tri_cells = [c for c in mesh.cells if c.type == "triangle"]
            if not tri_cells:
                raise ValueError(
                    f"삼각형 셀 없음. 포함 셀 타입: {[c.type for c in mesh.cells]}"
                )
            faces = np.vstack([c.data for c in tri_cells])
            surface = trimesh.Trimesh(
                vertices=mesh.points[:, :3],
                faces=faces,
                process=False,
            )
            surface.export(str(out_path))
            log.info(
                "convert_meshio_done",
                output=str(out_path),
                num_faces=len(surface.faces),
            )
            return out_path
        except ImportError as exc:
            raise ImportError(
                "meshio가 설치되지 않았습니다. `pip install meshio`를 실행하세요."
            ) from exc
        except Exception as exc:
            raise ValueError(
                f"meshio 변환 실패 [{path.suffix}]: {path}\n원인: {exc}"
            ) from exc
