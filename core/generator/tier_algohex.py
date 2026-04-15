"""Tier AlgoHex: Frame Field 기반 Tet→Hex 메쉬 변환기.

AlgoHex (AGPL-3.0, SIGGRAPH 2023) 바이너리를 subprocess로 호출해
tet mesh로부터 올-헥사헤드론 메쉬를 생성한다.

파이프라인:
  STL → Netgen tet mesh (.vtk) → AlgoHex HexMeshing → hex .ovm → polyMesh 변환

참고: https://github.com/cgg-bern/AlgoHex
CLI: AlgoHexMeshing --hexme-pipeline -i input.vtk -o output.ovm

Tier 파라미터 (strategy.tier_specific_params):
    algohex_pipeline (str, default="hexme"):
        "hexme" | "split" | "collapse"
        hexme: HexMe 논문 표준 파이프라인
        split:  Frame Field Singularity Correction 파이프라인
        collapse: All-Hex Meshing using Singularity-Restricted Field
    algohex_tet_size (float, default=0.05):
        Netgen으로 생성할 초기 tet mesh의 max element size.
        0~1 사이 값. 작을수록 세밀, 느림.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_algohex"
_BIN_NAME = "AlgoHexMeshing"
_WRAPPER_NAME = "algohex_mesh"


def _find_binary() -> Path | None:
    """AlgoHexMeshing 실행 파일을 찾아 반환한다."""
    import sys

    project_bin = Path(__file__).resolve().parents[2] / "bin"

    if sys.platform == "win32":
        for name in (_WRAPPER_NAME, _BIN_NAME):
            for ext in (".exe", ""):
                p = project_bin / (name + ext)
                if p.exists():
                    return p
        import os
        for win_dir in (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "AutoTessell" / "bin",
            Path(r"C:\AutoTessell\bin"),
        ):
            for name in (_WRAPPER_NAME, _BIN_NAME):
                p = win_dir / (name + ".exe")
                if p.exists():
                    return p
    else:
        for name in (_WRAPPER_NAME, _BIN_NAME):
            candidate = project_bin / name
            if candidate.exists():
                return candidate

    found = shutil.which(_BIN_NAME) or shutil.which(_WRAPPER_NAME)
    if found:
        return Path(found)
    return None


class TierAlgoHexGenerator:
    """Frame Field 기반 All-Hex 메쉬 생성기 (AlgoHex).

    STL → Netgen tet mesh → AlgoHex hex .ovm → polyMesh 변환.
    Netgen이 없으면 meshio/pyvista의 delaunay_3d fallback 사용.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        logger.info("tier_algohex_start", preprocessed_path=str(preprocessed_path))

        binary = _find_binary()
        if binary is None:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=(
                    "AlgoHexMeshing 바이너리를 찾을 수 없습니다. "
                    "AlgoHex/build/Build/bin/HexMeshing을 bin/에 복사하세요."
                ),
            )

        try:
            import meshio  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"meshio 미설치: {exc}",
            )

        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            return self._run_pipeline(
                binary=binary,
                strategy=strategy,
                preprocessed_path=preprocessed_path,
                case_dir=case_dir,
                t_start=t_start,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_algohex_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"AlgoHex 실행 실패: {exc}",
            )

    def _run_pipeline(
        self,
        binary: Path,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
        t_start: float,
    ) -> TierAttempt:
        import meshio

        params = strategy.tier_specific_params
        pipeline = str(params.get("algohex_pipeline", "hexme")).lower()
        tet_size = float(params.get("algohex_tet_size", 0.05))

        logger.info("tier_algohex_params", pipeline=pipeline, tet_size=tet_size)

        work_dir = case_dir / "_algohex_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: STL → Tet mesh (.vtk) via Netgen
        tet_vtk = work_dir / "tet_mesh.vtk"
        self._generate_tet_mesh(preprocessed_path, tet_vtk, tet_size)
        logger.info("tier_algohex_tet_generated", tet_vtk=str(tet_vtk))

        # Step 2: AlgoHex hex meshing
        hex_ovm = work_dir / "hex_mesh.ovm"
        bin_dir = binary.parent
        env = {**os.environ, "LD_LIBRARY_PATH": f"{bin_dir}:{os.environ.get('LD_LIBRARY_PATH', '')}"}

        pipeline_flag = {
            "hexme": "--hexme-pipeline",
            "split": "--split-paper",
            "collapse": "--collapse-paper",
        }.get(pipeline, "--hexme-pipeline")

        cmd = [
            str(binary),
            pipeline_flag,
            "-i", str(tet_vtk),
            "-o", str(hex_ovm),
        ]
        logger.info("tier_algohex_running", cmd=" ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1200,
            env=env,
        )

        if result.returncode != 0:
            logger.warning(
                "tier_algohex_nonzero_exit",
                returncode=result.returncode,
                stderr=result.stderr[-500:],
            )

        # Step 3: Read OVM hex output
        if not hex_ovm.exists():
            raise RuntimeError(
                f"AlgoHex OVM 출력을 찾을 수 없습니다. "
                f"stdout: {result.stdout[-300:]}\nstderr: {result.stderr[-300:]}"
            )

        logger.info("tier_algohex_reading_ovm", path=str(hex_ovm))
        hex_v, cell_face_lists = _parse_ovm_full(hex_ovm)

        logger.info(
            "tier_algohex_mesh_built",
            num_points=len(hex_v),
            num_cells=len(cell_face_lists),
        )

        # Step 4: write polyhedral polyMesh (true hex connectivity)
        mesh_stats = _write_polyhedral_polymesh(hex_v, cell_face_lists, case_dir)
        PolyMeshWriter._ensure_system_files(case_dir)

        shutil.rmtree(str(work_dir), ignore_errors=True)

        elapsed = time.monotonic() - t_start
        logger.info("tier_algohex_success", elapsed=elapsed, mesh_stats=mesh_stats)
        return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)

    def _generate_tet_mesh(
        self,
        surface_path: Path,
        output_vtk: Path,
        max_size: float,
    ) -> None:
        """STL 표면 → tet volume mesh (.vtk, ASCII v2.0 for AlgoHex).

        meshpy(TetGen) 우선, 실패 시 Netgen fallback.
        AlgoHex는 반드시 VTK DataFile Version 2.0 ASCII 포맷이어야 함.
        """
        # Primary: meshpy (TetGen) — 신뢰성 높음
        try:
            import meshpy.tet as tet
            import trimesh

            surf = trimesh.load(str(surface_path), force="mesh")
            verts = np.array(surf.vertices, dtype=np.float64)
            faces = np.array(surf.faces, dtype=np.int32)

            info = tet.MeshInfo()
            info.set_points(verts.tolist())
            info.set_facets(faces.tolist())

            vol = max_size ** 3 / 6.0
            mesh_out = tet.build(info, options=tet.Options(f"pqa{vol:.10e}"))

            pts = np.array(mesh_out.points, dtype=np.float64)
            elements = np.array(mesh_out.elements, dtype=np.int64)

            _write_vtk_v2_ascii(output_vtk, pts, elements, cell_type=10)  # 10=tetra
            return
        except Exception as e:
            logger.warning("tier_algohex_meshpy_failed", error=str(e))

        # Fallback: Netgen (STL only, not STEP)
        try:
            import netgen.stl as ngstl  # type: ignore
            import netgen.meshing as meshing  # type: ignore

            geo = ngstl.LoadSTLGeometry(str(surface_path))
            mp = meshing.MeshingParameters(maxh=max_size)
            mesh = geo.GenerateMesh(mp)

            pts_list = []
            for v in mesh.vertices:
                pts_list.append([v.p[0], v.p[1], v.p[2]])
            cells_list = []
            for el in mesh.Elements3D():
                cells_list.append([v.nr - 1 for v in el.vertices])

            if cells_list:
                pts = np.array(pts_list, dtype=np.float64)
                elements = np.array(cells_list, dtype=np.int64)
                _write_vtk_v2_ascii(output_vtk, pts, elements, cell_type=10)
                return
        except Exception as e:
            logger.warning("tier_algohex_netgen_failed", error=str(e))

        raise RuntimeError(
            "Tet mesh 생성 실패: meshpy(TetGen)과 Netgen 모두 실패했습니다."
        )


def _parse_ovm_full(
    ovm_path: Path,
) -> tuple[np.ndarray, list[list[list[int]]]]:
    """OVM ASCII 포맷을 파싱해 (points, cell_face_lists) 반환.

    OVM 구조:
        OVM ASCII
        Vertices / n / xyz ...
        Edges    / n / v0 v1 ...
        Faces    / n / k he0 he1 ... (half-edge 인덱스)
        Polyhedra/ n / m hf0 hf1 ... (half-face 인덱스)

    half-edge he → edge he//2, start_vertex = edges[he//2][he%2]
    face vertices = [start_v(he0), start_v(he1), ..., start_v(he_{k-1})]

    half-face hf → face hf//2
    hf%2==0: face vertices as-is (outward from this cell)
    hf%2==1: face vertices reversed (flip to get outward normals)

    Returns:
        points: (N, 3) vertex array
        cell_face_lists: list of cells; each cell is a list of faces;
                         each face is a list of vertex indices (outward CCW).
    """
    lines = ovm_path.read_text().splitlines()
    idx = 0

    def _skip_to(section: str) -> None:
        nonlocal idx
        while idx < len(lines) and lines[idx].strip() != section:
            idx += 1
        idx += 1  # skip section header

    # --- Vertices ---
    _skip_to("Vertices")
    n_vertices = int(lines[idx].strip())
    idx += 1
    points_list: list[list[float]] = []
    for _ in range(n_vertices):
        xyz = list(map(float, lines[idx].split()))
        points_list.append(xyz)
        idx += 1
    points = np.array(points_list, dtype=np.float64)

    # --- Edges ---
    _skip_to("Edges")
    n_edges = int(lines[idx].strip())
    idx += 1
    edges: list[tuple[int, int]] = []
    for _ in range(n_edges):
        v0, v1 = map(int, lines[idx].split())
        edges.append((v0, v1))
        idx += 1

    # --- Faces ---
    # Build face_verts: for each face, list of vertex indices in order
    # using half-edge start vertices.
    _skip_to("Faces")
    n_faces_ovm = int(lines[idx].strip())
    idx += 1
    face_verts: list[list[int]] = []
    for _ in range(n_faces_ovm):
        parts = list(map(int, lines[idx].split()))
        k = parts[0]
        halfedges = parts[1:k + 1]
        # start_vertex of half-edge he = edges[he//2][he % 2]
        vseq = [edges[he // 2][he % 2] for he in halfedges]
        face_verts.append(vseq)
        idx += 1

    # --- Polyhedra ---
    _skip_to("Polyhedra")
    n_cells = int(lines[idx].strip())
    idx += 1
    cell_face_lists: list[list[list[int]]] = []
    for _ in range(n_cells):
        parts = list(map(int, lines[idx].split()))
        m = parts[0]
        halffaces = parts[1:m + 1]
        idx += 1

        cell_faces: list[list[int]] = []
        for hf in halffaces:
            fi = hf // 2
            verts = face_verts[fi]
            if hf % 2 == 1:
                # reversed orientation → flip to get outward normals
                verts = verts[::-1]
            cell_faces.append(verts)

        cell_face_lists.append(cell_faces)

    return points, cell_face_lists


def _write_polyhedral_polymesh(
    points: np.ndarray,
    cell_face_lists: list[list[list[int]]],
    case_dir: Path,
) -> dict[str, int]:
    """Polyhedral cell data를 OpenFOAM polyMesh로 직접 기록한다.

    Args:
        points: (N, 3) vertex coordinate array.
        cell_face_lists: list of cells; each cell is a list of faces;
                         each face is a list of vertex indices (outward CCW from cell).
        case_dir: OpenFOAM case directory.

    Returns:
        dict with n_points, n_faces, n_cells, n_internal_faces, n_boundary_faces.
    """
    from core.generator.polymesh_writer import _FOAM_HEADER, _FOOTER

    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)

    n_cells = len(cell_face_lists)
    n_points = len(points)

    # --- Build face catalogue ---
    # Use frozenset of vertex indices as canonical key to detect shared faces.
    # For each face, record: (ordered_verts, owner_cell, neighbour_cell or -1).
    face_map: dict[frozenset, int] = {}      # canonical key → face index
    face_ordered: list[list[int]] = []       # face index → ordered vertex list
    face_owner: list[int] = []               # face index → owner cell
    face_neighbour: list[int] = []           # face index → neighbour cell (-1=boundary)

    for cell_i, cell_faces in enumerate(cell_face_lists):
        for face_vlist in cell_faces:
            key = frozenset(face_vlist)
            if key not in face_map:
                fi = len(face_ordered)
                face_map[key] = fi
                face_ordered.append(list(face_vlist))
                face_owner.append(cell_i)
                face_neighbour.append(-1)
            else:
                fi = face_map[key]
                # Second cell to see this face → it becomes the neighbour
                # The owner (first cell) orientation is already stored.
                face_neighbour[fi] = cell_i

    n_total_faces = len(face_ordered)

    # --- Classify internal vs boundary ---
    internal_face_ids = [i for i in range(n_total_faces) if face_neighbour[i] >= 0]
    boundary_face_ids = [i for i in range(n_total_faces) if face_neighbour[i] < 0]

    # Sort internal by (owner, neighbour), boundary by owner
    internal_face_ids.sort(key=lambda i: (face_owner[i], face_neighbour[i]))
    boundary_face_ids.sort(key=lambda i: face_owner[i])

    n_internal = len(internal_face_ids)
    n_boundary = len(boundary_face_ids)
    n_faces = n_internal + n_boundary

    # Reordered face lists: internal first, then boundary
    ordered_ids = internal_face_ids + boundary_face_ids

    # Build flat owner/neighbour lists in final face order
    owner_list = [face_owner[i] for i in ordered_ids]
    neighbour_list = [face_neighbour[i] for i in internal_face_ids]

    def _foam_header(foam_class: str, object_name: str) -> str:
        return _FOAM_HEADER.format(
            foam_class=foam_class,
            location="constant/polyMesh",
            object_name=object_name,
        )

    # --- Write points ---
    with open(poly_dir / "points", "w") as f:
        f.write(_foam_header("vectorField", "points"))
        f.write(f"{n_points}\n(\n")
        for p in points:
            f.write(f"({p[0]:.10g} {p[1]:.10g} {p[2]:.10g})\n")
        f.write(")\n")
        f.write(_FOOTER)

    # --- Write faces (n-gon format) ---
    with open(poly_dir / "faces", "w") as f:
        f.write(_foam_header("faceList", "faces"))
        f.write(f"{n_faces}\n(\n")
        for fi in ordered_ids:
            vlist = face_ordered[fi]
            ids_str = " ".join(str(v) for v in vlist)
            f.write(f"{len(vlist)}({ids_str})\n")
        f.write(")\n")
        f.write(_FOOTER)

    # --- Write owner (with note field) ---
    note = (
        f"nPoints:{n_points}  nCells:{n_cells}  "
        f"nFaces:{n_faces}  nInternalFaces:{n_internal}"
    )
    owner_header = _FOAM_HEADER.format(
        foam_class="labelList",
        location="constant/polyMesh",
        object_name="owner",
    ).replace(
        "    object      owner;",
        f"    note        \"{note}\";\n    object      owner;",
    )
    with open(poly_dir / "owner", "w") as f:
        f.write(owner_header)
        f.write(f"{n_faces}\n(\n")
        for o in owner_list:
            f.write(f"{o}\n")
        f.write(")\n")
        f.write(_FOOTER)

    # --- Write neighbour ---
    with open(poly_dir / "neighbour", "w") as f:
        f.write(_foam_header("labelList", "neighbour"))
        f.write(f"{n_internal}\n(\n")
        for nb in neighbour_list:
            f.write(f"{nb}\n")
        f.write(")\n")
        f.write(_FOOTER)

    # --- Write boundary ---
    with open(poly_dir / "boundary", "w") as f:
        f.write(_foam_header("polyBoundaryMesh", "boundary"))
        if n_boundary > 0:
            f.write("1\n(\n")
            f.write("    defaultWall\n    {\n")
            f.write("        type wall;\n")
            f.write(f"        nFaces {n_boundary};\n")
            f.write(f"        startFace {n_internal};\n")
            f.write("    }\n)\n")
        else:
            f.write("0\n(\n)\n")
        f.write(_FOOTER)

    return {
        "n_points": n_points,
        "n_faces": n_faces,
        "n_cells": n_cells,
        "n_internal_faces": n_internal,
        "n_boundary_faces": n_boundary,
    }


def _write_vtk_v2_ascii(path: Path, points: np.ndarray, cells: np.ndarray, cell_type: int) -> None:
    """VTK DataFile Version 2.0 ASCII 언구조 격자 파일을 직접 생성한다.

    AlgoHex는 반드시 이 포맷을 요구함 (meshio 기본 출력은 v4.0 XML/binary).
    cell_type: 10=tetra, 12=hexahedron
    """
    n_pts = len(points)
    n_cells = len(cells)
    verts_per_cell = cells.shape[1]

    with open(path, "w") as f:
        f.write("# vtk DataFile Version 2.0\n")
        f.write("AlgoHex tet mesh\n")
        f.write("ASCII\n")
        f.write("DATASET UNSTRUCTURED_GRID\n")
        f.write(f"POINTS {n_pts} double\n")
        for p in points:
            f.write(f"{p[0]:.10g} {p[1]:.10g} {p[2]:.10g}\n")
        f.write(f"CELLS {n_cells} {n_cells * (verts_per_cell + 1)}\n")
        for c in cells:
            f.write(f"{verts_per_cell}")
            for v in c:
                f.write(f" {v}")
            f.write("\n")
        f.write(f"CELL_TYPES {n_cells}\n")
        for _ in range(n_cells):
            f.write(f"{cell_type}\n")
