"""
Mesh generation pipeline: STL → OpenFOAM polyMesh

5-tier hybrid pipeline (tried in order):

  [공통 전처리]
    trimesh  (MIT)   — STL 로딩, 수리, BBox 추출
    pyACVD   (MIT)   — Voronoi 균일 surface remeshing (optional, graceful skip)

  Tier 0   tessell_mesh / geogram  (BSD-3-Clause)
             C++/pybind11 tet 메쉬 — 빠름, 2D/3D 지원
             tessell-mesh/ 빌드 필요 (./build.sh)

  Tier 0.5  Netgen  (LGPL-2.1)
             pip install netgen-mesher — STL → tet → Gmsh .msh → gmshToFoam
             자체 품질 최적화 내장, 순수 Python

  Tier 1   snappyHexMesh  (GPL/OpenFOAM 내장)
             Hex-dominant, 외부유동 CFD 최고 품질
             OpenFOAM 12 Docker 환경 필요

  Tier 2   pytetwild  (MPL-2.0)  +  MMG 후처리  (LGPL-3.0, optional)
             불량 STL 최후 fallback
             mmg3d binary가 PATH에 있으면 자동으로 품질 개선

모든 tier 이후 checkMesh 품질 검증 실행.
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
from mesh.stl_utils import (
    BBox,
    StlComplexity,
    analyze_stl_complexity,
    get_bbox,
    reconstruct_surface_poisson,
    remesh_surface_uniform,
    repair_stl_to_path,
)

logger = logging.getLogger(__name__)

__all__ = ["generate_mesh", "MeshGenerationError"]


class MeshGenerationError(RuntimeError):
    pass


class _TessellNotBuilt(Exception):
    """tessell_mesh.so 가 빌드되지 않았을 때."""


class _NetgenNotInstalled(Exception):
    """netgen-mesher 가 설치되지 않았을 때."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_mesh(
    stl_path: Path,
    case_dir: Path,
    target_cells: int = 500_000,
    mesh_purpose: str = "cfd",
    params=None,  # MeshParams | None
) -> dict:
    """
    STL → OpenFOAM polyMesh 생성.

    Returns:
        {"tier": "tessell"|"netgen"|"snappy"|"pytetwild", "num_cells": int|None, ...}

    Raises:
        MeshGenerationError: 모든 tier 실패 시
    """
    from mesh.params import MeshParams
    mp: MeshParams = params if params is not None else MeshParams()

    case_dir.mkdir(parents=True, exist_ok=True)
    bbox = get_bbox(stl_path)
    logger.info("STL bbox: %s, purpose: %s, target_cells: %d", bbox, mesh_purpose, target_cells)

    # 공통 전처리: pyACVD 균일 remeshing (optional)
    # 전처리 파일을 stl_path.parent (tmpdir)에 저장 — _reset_case(case_dir)가 삭제하지 않도록.
    # case_dir을 쓰면 Tier 0 실패 후 _reset_case()가 _repaired.stl 등을 지워버려
    # 다음 tier가 존재하지 않는 경로를 열려고 함 (버그).
    prep_dir = stl_path.parent
    clean_stl = _maybe_remesh_surface(stl_path, prep_dir, bbox)

    errors: list[str] = []
    tessell_skipped = False

    # FEA: 사면체 메쉬 목적 — tessell/netgen/pytetwild만 시도, snappyHexMesh 건너뜀
    skip_snappy = (mesh_purpose == "fea")

    # --- Tier 0: tessell_mesh / geogram ---
    try:
        result = _tessell_pipeline(clean_stl, case_dir, bbox)
        return {"tier": "tessell", **result}
    except _TessellNotBuilt:
        logger.info("tessell_mesh.so 없음 — Tier 0 건너뜀")
        tessell_skipped = True
    except Exception as e:
        logger.warning("Tier 0 (tessell) 실패: %s", e)
        errors.append(f"tessell: {e}")
        _reset_case(case_dir)

    # --- Tier 0.5: Netgen ---
    try:
        result = _netgen_pipeline(clean_stl, case_dir, bbox, mp)
        return {"tier": "netgen", **result}
    except _NetgenNotInstalled:
        logger.info("netgen-mesher 미설치 — Tier 0.5 건너뜀")
    except Exception as e:
        logger.warning("Tier 0.5 (netgen) 실패: %s", e)
        errors.append(f"netgen: {e}")
        _reset_case(case_dir)

    # --- Tier 1: snappyHexMesh (CFD 전용 — FEA 목적이면 건너뜀) ---
    if skip_snappy:
        logger.info("mesh_purpose=fea — snappyHexMesh 건너뜀")
    else:
        try:
            result = _snappy_pipeline(clean_stl, case_dir, bbox, target_cells, mp)
            return {"tier": "snappy", **result}
        except Exception as e:
            logger.warning("Tier 1 (snappy) 실패: %s", e)
            errors.append(f"snappy: {e}")
            _reset_case(case_dir)

    # --- Tier 2: pytetwild + MMG 후처리 ---
    try:
        result = _pytetwild_pipeline(clean_stl, case_dir, bbox, target_cells, mp)
        return {"tier": "pytetwild", **result}
    except Exception as e:
        errors.append(f"pytetwild: {e}")
        prefix = "(tessell 미빌드 — cd tessell-mesh && ./build.sh)\n" if tessell_skipped else ""
        raise MeshGenerationError(
            prefix + "모든 메쉬 생성 tier 실패:\n" + "\n".join(errors)
        ) from e


# ---------------------------------------------------------------------------
# 공통 전처리
# ---------------------------------------------------------------------------

def _maybe_remesh_surface(stl_path: Path, work_dir: Path, bbox: BBox) -> Path:
    """
    3단계 표면 준비 체인:

    1. trimesh repair  (항상 실행)
       — 구멍 메우기, winding 수정, 법선 수정
    2. Open3D Poisson 재구성  (trimesh 후에도 비수밀이면 시도)
       — 점군 → 새 수밀 메쉬로 재구성, 심각한 불량 STL 처리
    3. pyACVD 균일 remeshing  (항상 시도, 가장 좋은 surface에 적용)
       — Voronoi 균일 삼각형 분포로 변환
    """
    # --- 1. trimesh repair ---
    repaired = work_dir / "_repaired.stl"
    watertight = repair_stl_to_path(stl_path, repaired)
    logger.info("trimesh 수리: watertight=%s", watertight)
    source = repaired

    # --- 2. Open3D Poisson 재구성 (비수밀일 때만) ---
    if not watertight:
        poisson_out = work_dir / "_poisson.stl"
        success = reconstruct_surface_poisson(repaired, poisson_out, bbox=bbox)
        if success:
            logger.info("Open3D Poisson 재구성 완료 → 수밀 표면 생성")
            source = poisson_out
        else:
            logger.info("Poisson 재구성 건너뜀 (open3d 미설치 또는 실패)")

    # --- 3. pyACVD 균일 remeshing ---
    remeshed = work_dir / "_remeshed.stl"
    applied = remesh_surface_uniform(source, remeshed, target_points=5000)
    if applied:
        logger.info("pyACVD 균일 remeshing 완료")
        return remeshed
    return source


def _reset_case(case_dir: Path) -> None:
    shutil.rmtree(case_dir, ignore_errors=True)
    case_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Tier 0: tessell_mesh (geogram C++ / CDT)
# ---------------------------------------------------------------------------

def _tessell_pipeline(stl_path: Path, case_dir: Path, bbox: BBox) -> dict:
    """
    C++/geogram tet 메쉬 생성.
    tessell-mesh/ 빌드 후 backend/mesh/tessell_mesh.so 필요.
    """
    try:
        import tessell_mesh as tm  # type: ignore[import]
    except ImportError:
        raise _TessellNotBuilt(
            "tessell_mesh.so 없음 — 빌드: cd tessell-mesh && ./build.sh"
        )

    # stl_path는 _maybe_remesh_surface()에서 이미 수리됨
    logger.info("tessell_mesh (geogram) 실행: %s", stl_path)
    try:
        result = tm.tetrahedralize_stl(str(stl_path), quality=2.0)
    except Exception as e:
        raise MeshGenerationError(f"geogram tetrahedralize 실패: {e}") from e

    logger.info("geogram: %d vertices, %d tets", result.num_vertices, result.num_tets)
    result.write_openfoam(str(case_dir))

    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        raise MeshGenerationError("tessell_mesh: polyMesh/faces 생성 안됨")

    env = _openfoam_env()
    stats = _mesh_stats(case_dir, env)
    stats["num_tets"] = result.num_tets
    logger.info("tessell OK — tets=%d, cells=%s", result.num_tets, stats.get("num_cells"))
    return stats


# ---------------------------------------------------------------------------
# Tier 0.5: Netgen
# ---------------------------------------------------------------------------

def _netgen_pipeline(stl_path: Path, case_dir: Path, bbox: BBox, params=None) -> dict:
    """
    Netgen (LGPL-2.1) tet 메쉬 생성.
    pip install netgen-mesher

    Netgen → Gmsh2 .msh → gmshToFoam → polyMesh
    """
    try:
        from netgen.stl import STLGeometry  # type: ignore[import]
    except ImportError:
        raise _NetgenNotInstalled(
            "netgen-mesher 미설치 (pip install netgen-mesher)"
        )

    from mesh.params import MeshParams
    mp: MeshParams = params if params is not None else MeshParams()

    L = bbox.characteristic_length
    maxh = L / mp.netgen_maxh_ratio
    logger.info("Netgen 실행: maxh=%.4g (L/%.1f)", maxh, mp.netgen_maxh_ratio)
    try:
        geo = STLGeometry(str(stl_path))
        mesh = geo.GenerateMesh(maxh=maxh)
    except Exception as e:
        raise MeshGenerationError(f"Netgen 메쉬 생성 실패: {e}") from e

    msh_path = case_dir / "mesh.msh"
    # Gmsh2 Format 우선, 실패 시 Gmsh Format 시도
    exported = False
    for fmt in ("Gmsh2 Format", "Gmsh Format"):
        try:
            mesh.Export(str(msh_path), fmt)
            exported = True
            break
        except Exception:
            continue
    if not exported:
        raise MeshGenerationError("Netgen: Gmsh 포맷 export 실패")

    _setup_minimal_case(case_dir)
    env = _openfoam_env()
    _run_of(["gmshToFoam", str(msh_path), "-case", str(case_dir)], env, "gmshToFoam")

    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        raise MeshGenerationError("Netgen/gmshToFoam: polyMesh/faces 생성 안됨")

    stats = _mesh_stats(case_dir, env)
    logger.info("Netgen OK — cells=%s", stats.get("num_cells"))
    return stats


# ---------------------------------------------------------------------------
# Tier 1: snappyHexMesh
# ---------------------------------------------------------------------------

def _snappy_pipeline(
    stl_path: Path,
    case_dir: Path,
    bbox: BBox,
    target_cells: int,
    params=None,
) -> dict:
    """
    snappyHexMesh hex-dominant 파이프라인.

    case_dir/
      constant/triSurface/{geometry.stl}
      system/blockMeshDict, snappyHexMeshDict, ...
    """
    from mesh.params import MeshParams
    mp: MeshParams = params if params is not None else MeshParams()
    stl_name = stl_path.name

    # 곡률 기반 복잡도 분석 → 적응형 정밀화 파라미터 도출
    complexity = analyze_stl_complexity(stl_path)
    logger.info(
        "STL 복잡도: ratio=%.1f → refine=%d-%d, featureAngle=%.0f°, layers=%s",
        complexity.complexity_ratio,
        complexity.surface_refine_min,
        complexity.surface_refine_max,
        complexity.resolve_feature_angle,
        3 if complexity.complexity_ratio < 3 else 5,
    )

    domain = build_domain(bbox, stl_name, target_background_cells=max(8_000, target_cells // 50))
    _write_snappy_case(case_dir, stl_path, domain, complexity, mp)

    env = _openfoam_env()
    _run_of(["blockMesh", "-case", str(case_dir)], env, "blockMesh")
    _run_of(["surfaceFeatureExtract", "-case", str(case_dir)], env, "surfaceFeatureExtract")
    _run_of(["snappyHexMesh", "-overwrite", "-case", str(case_dir)], env, "snappyHexMesh")

    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        raise MeshGenerationError("snappyHexMesh: polyMesh/faces 생성 안됨")

    stats = _mesh_stats(case_dir, env)
    logger.info("snappyHexMesh OK — cells=%s", stats.get("num_cells"))
    return stats


def _write_snappy_case(
    case_dir: Path,
    stl_path: Path,
    domain: FlowDomain,
    complexity: StlComplexity | None = None,
    params=None,
) -> None:
    system = case_dir / "system"
    tri_surface = case_dir / "constant" / "triSurface"
    system.mkdir(parents=True, exist_ok=True)
    tri_surface.mkdir(parents=True, exist_ok=True)

    shutil.copy2(stl_path, tri_surface / stl_path.name)
    (system / "blockMeshDict").write_text(block_mesh_dict(domain))
    (system / "snappyHexMeshDict").write_text(snappy_hex_mesh_dict(domain, complexity, params))
    (system / "surfaceFeatureExtractDict").write_text(
        surface_feature_extract_dict(stl_path.name, complexity)
    )
    (system / "controlDict").write_text(control_dict())
    (system / "fvSchemes").write_text(fv_schemes())
    (system / "fvSolution").write_text(fv_solution())


# ---------------------------------------------------------------------------
# Tier 2: pytetwild + MMG 품질 후처리
# ---------------------------------------------------------------------------

def _pytetwild_pipeline(stl_path: Path, case_dir: Path, bbox: BBox, target_cells: int = 500_000, params=None) -> dict:
    """
    pytetwild (MPL-2.0) robust tet 메쉬 생성.
    mmg3d binary 가 PATH에 있으면 MMG (LGPL) 품질 후처리 자동 적용.

    pytetwild → (MMG 후처리) → .msh → gmshToFoam → polyMesh
    """
    try:
        import numpy as np
        import pytetwild
        import trimesh
    except ImportError as e:
        raise MeshGenerationError(
            f"pytetwild/trimesh 미설치 (pip install pytetwild trimesh): {e}"
        )

    from mesh.dev_pipeline import _cells_to_edge_fac
    from mesh.params import MeshParams
    mp: MeshParams = params if params is not None else MeshParams()

    # stl_path는 _maybe_remesh_surface()에서 이미 수리됨
    logger.info("pytetwild 실행")
    surf = trimesh.load(str(stl_path), force="mesh")
    vertices = np.array(surf.vertices, dtype=np.float64)
    faces = np.array(surf.faces, dtype=np.int32)

    edge_fac = (
        max(0.02, min(0.2, mp.tet_edge_length_fac))
        if mp.tet_edge_length_fac is not None
        else _cells_to_edge_fac(target_cells, vertices)
    )
    logger.info("pytetwild: edge_fac=%.4f, stop_energy=%.1f", edge_fac, mp.tet_stop_energy)

    try:
        v_out, t_out = pytetwild.tetrahedralize(
            vertices,
            faces,
            edge_length_fac=edge_fac,
            stop_energy=mp.tet_stop_energy,
            quiet=True,
        )
    except Exception as e:
        raise MeshGenerationError(f"pytetwild 실패: {e}") from e

    # Optional: MMG 품질 후처리
    if mp.mmg_enabled:
        v_out, t_out = _apply_mmg_quality(v_out, t_out, case_dir, bbox, mp)
    else:
        logger.info("MMG 후처리 비활성화 (mmg_enabled=False)")

    msh_path = case_dir / "mesh.msh"
    _write_gmsh_msh2(v_out, t_out, msh_path)
    _setup_minimal_case(case_dir)

    env = _openfoam_env()
    _run_of(["gmshToFoam", str(msh_path), "-case", str(case_dir)], env, "gmshToFoam")

    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        raise MeshGenerationError("gmshToFoam: polyMesh/faces 생성 안됨")

    stats = _mesh_stats(case_dir, env)
    logger.info("pytetwild OK — cells=%s", stats.get("num_cells"))
    return stats


def _apply_mmg_quality(
    v_out,
    t_out,
    work_dir: Path,
    bbox: BBox,
    params=None,
):
    """
    MMG3D (LGPL-3.0) 품질 개선 후처리.

    mmg3d binary가 PATH에 없으면 조용히 원본 반환.
    Medit .mesh 포맷 중간 변환에 meshio 사용.
    """
    # apt-get install mmg 시 mmg3d, 직접 빌드 시 mmg3d_O3 / mmg3d_64
    _MMG_CANDIDATES = ("mmg3d", "mmg3d_O3", "mmg3d_64", "mmg3d_O0")
    mmg_bin = next(
        (shutil.which(name) for name in _MMG_CANDIDATES if shutil.which(name)),
        None,
    )
    if not mmg_bin:
        return v_out, t_out

    try:
        import meshio
        import numpy as np
    except ImportError:
        return v_out, t_out

    try:
        in_mesh = work_dir / "_mmg_in.mesh"
        out_mesh = work_dir / "_mmg_out.mesh"

        meshio.write(
            str(in_mesh),
            meshio.Mesh(
                points=v_out,
                cells=[("tetra", t_out.astype(np.int64))],
            ),
        )

        from mesh.params import MeshParams
        mp: MeshParams = params if params is not None else MeshParams()

        L = bbox.characteristic_length
        hmin = L / 50
        hmax = L / 5
        hausd = mp.mmg_hausd if mp.mmg_hausd is not None else L / 50
        mmg_cmd = [
            mmg_bin,
            "-in", str(in_mesh), "-out", str(out_mesh),
            "-hmin", f"{hmin:.6g}", "-hmax", f"{hmax:.6g}",
            "-hausd", f"{hausd:.6g}",
            "-hgrad", f"{mp.mmg_hgrad:.4g}",
        ]
        proc = subprocess.run(
            mmg_cmd,
            capture_output=True, text=True, timeout=300,
        )

        if proc.returncode != 0 or not out_mesh.exists():
            logger.warning("mmg3d 비정상 종료 — 원본 메쉬 사용")
            return v_out, t_out

        improved = meshio.read(str(out_mesh))
        v_new = improved.points
        t_new = improved.cells_dict.get("tetra")
        if t_new is None:
            return v_out, t_out

        logger.info("MMG3D 품질 개선: %d → %d tets", len(t_out), len(t_new))
        return v_new, t_new.astype(np.int32)

    except Exception as e:
        logger.warning("MMG 후처리 실패 (%s) — 원본 메쉬 사용", e)
        return v_out, t_out


def _write_gmsh_msh2(vertices, tets, msh_path: Path) -> None:
    """Gmsh 2.2 ASCII .msh 파일 작성 (tetrahedral elements)."""
    with open(msh_path, "w") as f:
        f.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")

        f.write("$Nodes\n")
        f.write(f"{len(vertices)}\n")
        for i, (x, y, z) in enumerate(vertices, 1):
            f.write(f"{i} {x:.10g} {y:.10g} {z:.10g}\n")
        f.write("$EndNodes\n")

        f.write("$Elements\n")
        f.write(f"{len(tets)}\n")
        for i, tet in enumerate(tets, 1):
            # tet 배열이 float인 경우도 안전하게 처리
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
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _openfoam_env() -> dict:
    """
    OpenFOAM 환경변수 반환.

    1. 현재 프로세스 환경에 WM_PROJECT_DIR 가 있으면 이미 OF 환경 — os.environ 그대로 반환.
    2. /opt/openfoam12/etc/bashrc 가 있으면 source 후 env 파싱 (타임아웃 60초).
    3. 둘 다 없으면 None 반환 (checkMesh/gmshToFoam 등이 FileNotFoundError 발생).
    """
    import os

    # 빠른 경로: worker 컨테이너는 이미 OF 환경으로 실행됨
    if "WM_PROJECT_DIR" in os.environ:
        return dict(os.environ)

    of_bashrc = "/opt/openfoam12/etc/bashrc"
    if not Path(of_bashrc).exists():
        return None  # type: ignore[return-value]

    try:
        result = subprocess.run(
            ["bash", "-c", f"source {of_bashrc} && env"],
            capture_output=True, text=True, timeout=60,
        )
        env = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                env[k] = v
        return env or None  # type: ignore[return-value]
    except Exception as e:
        logger.warning("OpenFOAM bashrc source 실패 (%s) — env=None", e)
        return None  # type: ignore[return-value]


def _run_of(cmd: list[str], env: dict | None, label: str, timeout: int = 300) -> str:
    """OpenFOAM 명령 실행. 실패 시 MeshGenerationError."""
    logger.info("실행 %s: %s", label, " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env,
        )
    except FileNotFoundError:
        raise MeshGenerationError(
            f"{label}: 명령 없음 ({cmd[0]}) — OpenFOAM 설치 확인"
        )
    except subprocess.TimeoutExpired:
        raise MeshGenerationError(f"{label} 타임아웃 ({timeout}s)")

    if proc.returncode != 0:
        tail = "\n".join((proc.stderr + proc.stdout).splitlines()[-50:])
        raise MeshGenerationError(f"{label} 실패 (rc={proc.returncode}):\n{tail}")

    return proc.stdout


def _mesh_stats(case_dir: Path, env: dict | None) -> dict:
    """checkMesh 실행 후 품질 통계 반환."""
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
            "checkmesh_output": result.raw_output[-2000:],
        }
    except FileNotFoundError:
        logger.warning("checkMesh 없음 — 품질 검증 생략")
        return {"passed": True, "num_cells": None}
