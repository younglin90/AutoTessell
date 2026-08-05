"""
Dev-mode mesh pipeline: pytetwild + trimesh + pure-Python polyMesh writer.

No Docker, no OpenFOAM, no S3 required.
Produces a real tetrahedral mesh in OpenFOAM polyMesh format.
"""

import logging
from pathlib import Path

from mesh.of_writer import write_polymesh

logger = logging.getLogger(__name__)


def _cells_to_edge_fac(target_cells: int, vertices) -> float:
    """
    target_cells → edge_length_fac 역산.

    각 사면체 부피 ≈ edge³/8, 기하 충진율 ≈ 50%
    → edge ≈ (4 * bbox_vol / target_cells)^(1/3)
    → edge_length_fac = edge / bbox_diag
    """
    import numpy as np
    bbox_min = vertices.min(axis=0)
    bbox_max = vertices.max(axis=0)
    dims = bbox_max - bbox_min
    vol = float(max(np.prod(dims), 1e-12))
    diag = float(max(np.linalg.norm(dims), 1e-6))
    edge = (4.0 * vol / max(target_cells, 1)) ** (1.0 / 3.0)
    fac = edge / diag
    return max(0.02, min(0.2, fac))


def generate_mesh_dev(
    stl_path: Path,
    case_dir: Path,
    target_cells: int = 500_000,
    mesh_purpose: str = "cfd",
    params=None,  # MeshParams | None
) -> dict:
    """
    STL → real tet mesh → OpenFOAM polyMesh (Windows-compatible).

    Uses pytetwild for tetrahedralization and a pure-Python polyMesh writer.

    Returns:
        {"tier": "pytetwild_dev", "num_cells": int, "num_points": int, "passed": True}

    Raises:
        RuntimeError on failure
    """
    try:
        import numpy as np
        import pytetwild
        import trimesh
    except ImportError as e:
        raise RuntimeError(
            f"pytetwild 또는 trimesh 미설치: {e}\n"
            "pip install pytetwild trimesh numpy"
        )

    from mesh.params import MeshParams
    mp: MeshParams = params if params is not None else MeshParams()

    logger.info("dev 메쉬 파이프라인 시작: %s", stl_path)

    # 1. Load and repair STL
    mesh = trimesh.load(str(stl_path), force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        raise RuntimeError("STL 로딩 실패 — 유효한 메쉬가 아닙니다")

    # Fill holes and fix winding
    trimesh.repair.fill_holes(mesh)
    trimesh.repair.fix_winding(mesh)
    trimesh.repair.fix_normals(mesh)

    logger.info(
        "trimesh 로드: vertices=%d, faces=%d, watertight=%s",
        len(mesh.vertices), len(mesh.faces), mesh.is_watertight,
    )

    vertices = np.array(mesh.vertices, dtype=np.float64)
    faces = np.array(mesh.faces, dtype=np.int32)

    # 2. Tetrahedralize with pytetwild
    # edge_length_fac: pro override > auto from target_cells
    edge_fac = (
        max(0.02, min(0.2, mp.tet_edge_length_fac))
        if mp.tet_edge_length_fac is not None
        else _cells_to_edge_fac(target_cells, vertices)
    )
    stop_energy = mp.tet_stop_energy

    logger.info(
        "pytetwild 실행: target_cells=%d, purpose=%s, edge_fac=%.4f, stop_energy=%.1f",
        target_cells, mesh_purpose, edge_fac, stop_energy,
    )
    try:
        v_out, t_out = pytetwild.tetrahedralize(
            vertices,
            faces,
            edge_length_fac=edge_fac,
            stop_energy=stop_energy,
            quiet=True,
        )
    except Exception as e:
        raise RuntimeError(f"pytetwild 실패: {e}") from e

    logger.info("pytetwild 완료: vertices=%d, tets=%d", len(v_out), len(t_out))

    # 3. Write OpenFOAM polyMesh
    case_dir.mkdir(parents=True, exist_ok=True)
    stats = write_polymesh(v_out, t_out, case_dir)

    logger.info(
        "polyMesh 작성 완료: cells=%d, faces=%d, internal=%d",
        stats["num_cells"], stats["num_faces"], stats["num_internal_faces"],
    )

    return {
        "tier": "pytetwild_dev",
        "num_cells": stats["num_cells"],
        "num_points": stats["num_points"],
        "num_faces": stats["num_faces"],
        "passed": True,
    }
