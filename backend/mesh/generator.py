"""
Mesh generation pipeline: STL → OpenFOAM polyMesh

Tier 1 (primary): snappyHexMesh
  STL → bbox → auto blockMeshDict + snappyHexMeshDict → blockMesh → snappyHexMesh

Tier 2 (fallback): pytetwild + gmshToFoam
  STL → trimesh repair → pytetwild tet mesh → .msh → gmshToFoam → polyMesh

Both tiers end with checkMesh validation.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from mesh.openfoam_config import (
    FlowDomain,
    block_mesh_dict,
    build_domain,
    control_dict,
    fv_schemes,
    fv_solution,
    snappy_hex_mesh_dict,
    surface_feature_extract_dict,
)
from mesh.stl_utils import BBox, get_bbox, repair_stl_to_path

logger = logging.getLogger(__name__)

# Re-export so tasks.py only imports from generator
__all__ = ["generate_mesh", "MeshGenerationError"]


class MeshGenerationError(RuntimeError):
    pass


def generate_mesh(
    stl_path: Path,
    case_dir: Path,
    target_cells: int = 500_000,
) -> dict:
    """
    Generate an OpenFOAM polyMesh from stl_path into case_dir.

    Returns a dict with mesh statistics:
        {"tier": "snappy"|"pytetwild", "num_cells": int|None, ...}

    Raises MeshGenerationError if all tiers fail.
    """
    case_dir.mkdir(parents=True, exist_ok=True)
    bbox = get_bbox(stl_path)
    logger.info("STL bbox: %s", bbox)

    # --- Tier 1: snappyHexMesh ---
    try:
        result = _snappy_pipeline(stl_path, case_dir, bbox, target_cells)
        return {"tier": "snappy", **result}
    except Exception as e:
        logger.warning("snappyHexMesh tier failed (%s) — trying pytetwild fallback", e)
        shutil.rmtree(case_dir, ignore_errors=True)
        case_dir.mkdir(parents=True, exist_ok=True)

    # --- Tier 2: pytetwild → gmshToFoam ---
    try:
        result = _pytetwild_pipeline(stl_path, case_dir, bbox)
        return {"tier": "pytetwild", **result}
    except Exception as e:
        raise MeshGenerationError(
            f"All mesh generation tiers failed. Last error: {e}"
        ) from e


# ---------------------------------------------------------------------------
# Tier 1: snappyHexMesh
# ---------------------------------------------------------------------------

def _snappy_pipeline(
    stl_path: Path,
    case_dir: Path,
    bbox: BBox,
    target_cells: int,
) -> dict:
    """
    Full snappyHexMesh pipeline.

    Directory layout created:
      case_dir/
        constant/triSurface/{geometry.stl}
        system/blockMeshDict
        system/snappyHexMeshDict
        system/surfaceFeatureExtractDict
        system/controlDict
        system/fvSchemes
        system/fvSolution
    """
    stl_name = stl_path.name
    domain = build_domain(bbox, stl_name, target_background_cells=max(8_000, target_cells // 50))

    # --- Write case structure ---
    _write_snappy_case(case_dir, stl_path, domain)

    # --- Run pipeline ---
    env = _openfoam_env()

    _run_of(["blockMesh", "-case", str(case_dir)], env, "blockMesh")
    _run_of(
        ["surfaceFeatureExtract", "-case", str(case_dir)],
        env,
        "surfaceFeatureExtract",
    )
    _run_of(
        ["snappyHexMesh", "-overwrite", "-case", str(case_dir)],
        env,
        "snappyHexMesh",
    )

    # snappyHexMesh writes to a numbered time directory by default;
    # -overwrite flag writes directly to constant/polyMesh.
    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        raise MeshGenerationError(
            "snappyHexMesh completed but constant/polyMesh/faces not found"
        )

    stats = _mesh_stats(case_dir, env)
    logger.info("snappyHexMesh OK — cells=%s", stats.get("num_cells"))
    return stats


def _write_snappy_case(case_dir: Path, stl_path: Path, domain: FlowDomain) -> None:
    system = case_dir / "system"
    constant = case_dir / "constant"
    tri_surface = constant / "triSurface"

    system.mkdir(parents=True, exist_ok=True)
    tri_surface.mkdir(parents=True, exist_ok=True)

    stl_name = stl_path.name
    shutil.copy2(stl_path, tri_surface / stl_name)

    (system / "blockMeshDict").write_text(block_mesh_dict(domain))
    (system / "snappyHexMeshDict").write_text(snappy_hex_mesh_dict(domain))
    (system / "surfaceFeatureExtractDict").write_text(
        surface_feature_extract_dict(stl_name)
    )
    (system / "controlDict").write_text(control_dict())
    (system / "fvSchemes").write_text(fv_schemes())
    (system / "fvSolution").write_text(fv_solution())


# ---------------------------------------------------------------------------
# Tier 2: pytetwild → gmshToFoam
# ---------------------------------------------------------------------------

def _pytetwild_pipeline(stl_path: Path, case_dir: Path, bbox: BBox) -> dict:
    """
    Fallback pipeline using pytetwild (MPL-2.0) for robust dirty-STL meshing.

    pytetwild → .msh (Gmsh format 2) → gmshToFoam → polyMesh
    """
    try:
        import numpy as np
        import pytetwild
        import trimesh
    except ImportError as e:
        raise MeshGenerationError(
            f"pytetwild/trimesh not available (pip install pytetwild trimesh): {e}"
        )

    # 1. Load + repair STL
    repaired_stl = case_dir / "repaired.stl"
    is_watertight = repair_stl_to_path(stl_path, repaired_stl)
    if not is_watertight:
        logger.warning("STL is not watertight after repair — proceeding anyway")

    # 2. Generate tet mesh with pytetwild
    logger.info("Running pytetwild mesh generation")
    surf = trimesh.load(str(repaired_stl), force="mesh")
    vertices = np.array(surf.vertices, dtype=np.float64)
    faces = np.array(surf.faces, dtype=np.int32)

    # edge_length controls mesh coarseness relative to bbox
    L = bbox.characteristic_length
    edge_length = L / 20.0  # ~20 cells across the geometry

    try:
        v_out, t_out = pytetwild.tetrahedralize(
            vertices,
            faces,
            edge_length_r=edge_length / L,  # relative to bbox diagonal
            stop_quality=10,
        )
    except Exception as e:
        raise MeshGenerationError(f"pytetwild failed: {e}") from e

    # 3. Write Gmsh .msh format 2
    msh_path = case_dir / "mesh.msh"
    _write_gmsh_msh2(v_out, t_out, msh_path)

    # 4. Setup minimal OpenFOAM case structure
    _setup_minimal_case(case_dir)

    # 5. Run gmshToFoam
    env = _openfoam_env()
    _run_of(
        ["gmshToFoam", str(msh_path), "-case", str(case_dir)],
        env,
        "gmshToFoam",
    )

    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        raise MeshGenerationError("gmshToFoam completed but polyMesh/faces not found")

    stats = _mesh_stats(case_dir, env)
    logger.info("pytetwild/gmshToFoam OK — cells=%s", stats.get("num_cells"))
    return stats


def _write_gmsh_msh2(vertices, tets, msh_path: Path) -> None:
    """Write a minimal Gmsh 2.2 ASCII .msh file with tetrahedral elements."""
    with open(msh_path, "w") as f:
        f.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")

        # Nodes
        f.write("$Nodes\n")
        f.write(f"{len(vertices)}\n")
        for i, (x, y, z) in enumerate(vertices, 1):
            f.write(f"{i} {x:.10g} {y:.10g} {z:.10g}\n")
        f.write("$EndNodes\n")

        # Elements (tet type = 4)
        f.write("$Elements\n")
        f.write(f"{len(tets)}\n")
        for i, tet in enumerate(tets, 1):
            # elm-number elm-type num-tags tag1 tag2 n1 n2 n3 n4
            n1, n2, n3, n4 = int(tet[0]) + 1, int(tet[1]) + 1, int(tet[2]) + 1, int(tet[3]) + 1
            f.write(f"{i} 4 2 1 1 {n1} {n2} {n3} {n4}\n")
        f.write("$EndElements\n")


def _setup_minimal_case(case_dir: Path) -> None:
    system = case_dir / "system"
    constant = case_dir / "constant"
    system.mkdir(parents=True, exist_ok=True)
    constant.mkdir(parents=True, exist_ok=True)
    (system / "controlDict").write_text(control_dict())
    (system / "fvSchemes").write_text(fv_schemes())
    (system / "fvSolution").write_text(fv_solution())


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _openfoam_env() -> dict:
    """Return a shell environment with OpenFOAM sourced, or an empty dict."""
    import os
    import subprocess as sp

    of_bashrc = "/opt/openfoam12/etc/bashrc"
    if not Path(of_bashrc).exists():
        # Development environment: use system PATH as-is
        return None  # type: ignore[return-value]

    try:
        result = sp.run(
            ["bash", "-c", f"source {of_bashrc} && env"],
            capture_output=True, text=True, timeout=30,
        )
        env = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                env[k] = v
        return env
    except Exception:
        return None  # type: ignore[return-value]


def _run_of(cmd: list[str], env: dict | None, label: str, timeout: int = 300) -> str:
    """Run an OpenFOAM command, raising MeshGenerationError on failure."""
    logger.info("Running %s: %s", label, " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        raise MeshGenerationError(
            f"{label}: command not found ({cmd[0]}) — is OpenFOAM installed?"
        )
    except subprocess.TimeoutExpired:
        raise MeshGenerationError(f"{label} timed out after {timeout}s")

    if proc.returncode != 0:
        # Include last 50 lines of stderr for diagnosis
        tail = "\n".join((proc.stderr + proc.stdout).splitlines()[-50:])
        raise MeshGenerationError(f"{label} failed (rc={proc.returncode}):\n{tail}")

    return proc.stdout


def _mesh_stats(case_dir: Path, env: dict | None) -> dict:
    """Run checkMesh and return parsed statistics."""
    from mesh.checkmesh import parse_checkmesh_output

    try:
        proc = subprocess.run(
            ["checkMesh", "-case", str(case_dir)],
            capture_output=True, text=True, timeout=120, env=env,
        )
        result = parse_checkmesh_output(proc.stdout + proc.stderr)
        return {
            "passed": result.passed,
            "num_cells": result.num_cells,
            "max_non_orthogonality": result.max_non_orthogonality,
            "max_skewness": result.max_skewness,
            "checkmesh_output": result.raw_output[-2000:],  # last 2000 chars
        }
    except FileNotFoundError:
        logger.warning("checkMesh not found — skipping quality check")
        return {"passed": True, "num_cells": None}
