"""범용 메쉬 파일 로더.

지원 포맷: STL, OBJ, PLY, OFF (trimesh 기반)
CAD 포맷: STEP, IGES, BREP (cadquery → trimesh 테셀레이션)
추가 포맷 확장은 meshio 계층에서 처리한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import trimesh

from core.utils.logging import get_logger

log = get_logger(__name__)

# trimesh 로딩을 지원하는 확장자 목록
TRIMESH_FORMATS: frozenset[str] = frozenset(
    {".stl", ".obj", ".ply", ".off", ".3mf", ".glb", ".gltf", ".dae"}
)

# meshio 로딩을 지원하는 확장자 목록 (trimesh fallback 포함)
MESHIO_FORMATS: frozenset[str] = frozenset(
    {".msh", ".vtu", ".vtk", ".vtp", ".xdmf", ".xmf", ".nas", ".bdf", ".inp"}
)

CAD_FORMATS: frozenset[str] = frozenset({".step", ".stp", ".iges", ".igs", ".brep"})


def _detect_format(path: Path) -> str:
    """확장자 기반 포맷 감지. 대문자 정규화 후 반환."""
    return path.suffix.lower()


def load_mesh(path: Path) -> trimesh.Trimesh:
    """파일을 로딩하여 trimesh.Trimesh 객체를 반환한다.

    Args:
        path: 입력 파일 경로.

    Returns:
        표면 삼각 메쉬.

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 경우.
        ValueError: 지원하지 않는 포맷이거나 로딩에 실패한 경우.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {path}")

    if not path.is_file():
        raise ValueError(f"경로가 파일이 아닙니다: {path}")

    fmt = _detect_format(path)
    file_size = os.path.getsize(path)

    log.info(
        "loading_mesh",
        path=str(path),
        format=fmt,
        file_size_bytes=file_size,
    )

    if fmt in CAD_FORMATS:
        return _load_via_cad(path, fmt)

    if fmt in MESHIO_FORMATS:
        return _load_via_meshio(path, fmt)

    if fmt in TRIMESH_FORMATS or fmt:
        return _load_via_trimesh(path, fmt)

    raise ValueError(f"지원하지 않는 파일 포맷입니다: {fmt} (파일: {path})")


def _load_via_cad(path: Path, fmt: str) -> trimesh.Trimesh:
    """CAD B-Rep 파일을 cadquery로 로딩 후 trimesh로 테셀레이션.

    cadquery 실패 시 gmsh로 폴백한다.
    """
    # --- cadquery 시도 ---
    cq_error: str = ""
    try:
        return _load_via_cadquery(path, fmt)
    except Exception as cq_exc:
        cq_error = str(cq_exc)
        log.warning("cadquery_load_failed", path=str(path), fmt=fmt, error=cq_error)

    # --- gmsh 폴백 ---
    try:
        return _load_via_gmsh(path, fmt)
    except Exception as gmsh_exc:
        raise ValueError(
            f"CAD 파일 로딩 실패 [{fmt}]: {path}\n"
            f"cadquery 오류: {cq_error}\n"
            f"gmsh 오류: {gmsh_exc}"
        ) from gmsh_exc


def _load_via_cadquery(path: Path, fmt: str) -> trimesh.Trimesh:
    """cadquery를 사용한 CAD 로딩 및 테셀레이션."""
    try:
        import cadquery as cq
    except ImportError as exc:
        raise ImportError(
            "cadquery가 설치되지 않았습니다. `pip install cadquery`를 실행하세요."
        ) from exc

    import numpy as np

    ext = fmt.lstrip(".")
    if ext in ("step", "stp"):
        wp = cq.importers.importStep(str(path))
    elif ext == "brep":
        wp = cq.importers.importBrep(str(path))
    elif ext in ("iges", "igs"):
        # cadquery는 IGES 전용 임포터가 없으므로 importShape로 시도
        wp = cq.importers.importShape("STEP", str(path))
    else:
        raise ValueError(f"cadquery에서 지원하지 않는 CAD 확장자: {fmt}")

    shape = wp.val()
    vertices_cq, faces_list = shape.tessellate(tolerance=0.001, angularTolerance=0.1)  # type: ignore[union-attr]

    if not vertices_cq or not faces_list:
        raise ValueError(f"cadquery 테셀레이션 결과가 비어 있습니다: {path}")

    vertices_np = np.array([(v.x, v.y, v.z) for v in vertices_cq], dtype=np.float64)
    faces_np = np.array(faces_list, dtype=np.int32)

    mesh = trimesh.Trimesh(vertices=vertices_np, faces=faces_np, process=True)

    if len(mesh.faces) == 0:
        raise ValueError(f"cadquery 테셀레이션 후 유효한 면이 없습니다: {path}")

    log.info(
        "mesh_loaded_via_cadquery",
        path=str(path),
        num_vertices=len(mesh.vertices),
        num_faces=len(mesh.faces),
    )
    return mesh


def _load_via_gmsh(path: Path, fmt: str) -> trimesh.Trimesh:
    """gmsh를 사용한 CAD 로딩 및 표면 메쉬 추출."""
    try:
        import gmsh
    except ImportError as exc:
        raise ImportError(
            "gmsh가 설치되지 않았습니다. `pip install gmsh`를 실행하세요."
        ) from exc

    import numpy as np

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)  # 출력 억제
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.generate(2)  # 표면 메쉬

        # 노드 및 요소 추출
        node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
        # node_coords: [x0,y0,z0, x1,y1,z1, ...]
        vertices = np.array(node_coords, dtype=np.float64).reshape(-1, 3)

        # 삼각형 요소 (타입 2)
        elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements(dim=2)
        tri_faces: list[np.ndarray] = []
        for etype, etags, enode_tags in zip(elem_types, elem_tags, elem_node_tags):
            if etype == 2:  # 3-node triangle
                # gmsh 태그는 1-based → 0-based 변환
                tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}
                raw = np.array(enode_tags, dtype=np.int64).reshape(-1, 3)
                faces_idx = np.vectorize(tag_to_idx.get)(raw)
                tri_faces.append(faces_idx)

        if not tri_faces:
            raise ValueError(f"gmsh 메쉬에서 삼각형 요소를 찾지 못했습니다: {path}")

        faces = np.vstack(tri_faces).astype(np.int32)
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)

        if len(mesh.faces) == 0:
            raise ValueError(f"gmsh 추출 후 유효한 면이 없습니다: {path}")

        log.info(
            "mesh_loaded_via_gmsh",
            path=str(path),
            num_vertices=len(mesh.vertices),
            num_faces=len(mesh.faces),
        )
        return mesh

    finally:
        gmsh.finalize()


def _load_via_trimesh(path: Path, fmt: str) -> trimesh.Trimesh:
    """trimesh.load()를 사용한 로딩."""
    try:
        result = trimesh.load(str(path), force="mesh")
    except Exception as exc:
        raise ValueError(
            f"trimesh 로딩 실패 [{fmt}]: {path}\n원인: {exc}"
        ) from exc

    if result is None:
        raise ValueError(f"trimesh가 빈 결과를 반환했습니다: {path}")

    # Scene이 반환된 경우 단일 메쉬로 병합
    if isinstance(result, trimesh.Scene):
        if len(result.geometry) == 0:
            raise ValueError(f"Scene이 비어 있습니다: {path}")
        meshes = list(result.geometry.values())
        result = trimesh.util.concatenate(meshes)

    if not isinstance(result, trimesh.Trimesh):
        raise ValueError(
            f"Trimesh 객체를 얻지 못했습니다 (type={type(result).__name__}): {path}"
        )

    if len(result.faces) == 0:
        raise ValueError(f"면(face)이 없는 메쉬가 반환되었습니다: {path}")

    log.info(
        "mesh_loaded",
        path=str(path),
        num_vertices=len(result.vertices),
        num_faces=len(result.faces),
    )
    return result


def _load_via_meshio(path: Path, fmt: str) -> trimesh.Trimesh:
    """meshio.read() → 표면 삼각 메쉬 추출."""
    try:
        import meshio
    except ImportError as exc:
        raise ImportError(
            "meshio가 설치되지 않았습니다. `pip install meshio`를 실행하세요."
        ) from exc

    try:
        mesh = meshio.read(str(path))
    except Exception as exc:
        raise ValueError(
            f"meshio 로딩 실패 [{fmt}]: {path}\n원인: {exc}"
        ) from exc

    # 삼각형 셀 추출
    tri_cells = [
        cell for cell in mesh.cells if cell.type == "triangle"
    ]
    if not tri_cells:
        raise ValueError(
            f"meshio 메쉬에서 삼각형 셀을 찾지 못했습니다: {path}\n"
            f"포함된 셀 타입: {[c.type for c in mesh.cells]}"
        )

    import numpy as np

    faces = np.vstack([c.data for c in tri_cells])
    result = trimesh.Trimesh(vertices=mesh.points[:, :3], faces=faces, process=False)

    log.info(
        "mesh_loaded_via_meshio",
        path=str(path),
        num_vertices=len(result.vertices),
        num_faces=len(result.faces),
    )
    return result
