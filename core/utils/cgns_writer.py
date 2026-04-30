"""G5 / beta2605 — CGNS (CFD General Notation System) HDF5 writer.

CGNS 는 CFD 의 ANSI/ISO 표준 (NASA + DOE consortium). HDF5 backend 사용.
주요 사용처: NASA FUN3D, OpenFOAM (cgnsToFoam), ANSYS Fluent, Star-CCM+.

CGNS HDF5 hierarchy (SIDS standard 4.x):
    /                                    (root)
        @CGNSLibraryVersion              (float32: 4.4)
        @CGNSBase_t                      (label)
        Base/                            (CGNS base node)
            @CellDimension               (int32: 3)
            @PhysicalDimension           (int32: 3)
            Zone-1/                      (Zone_t)
                @ZoneType                ("Unstructured")
                ZoneType/                (NodeData)
                    @label = "ZoneType_t"
                    " data" = "Unstructured"
                GridCoordinates/         (GridCoordinates_t)
                    CoordinateX/         (DataArray_t, float64)
                    CoordinateY/
                    CoordinateZ/
                Cells/                   (Elements_t)
                    @ElementType         (int32 — see ElementType_t enum)
                    @ElementRange        (int32 (2,))
                    ElementConnectivity/ (DataArray_t, int32)
                ZoneBC/                  (ZoneBC_t)
                    BC-N/                (BC_t)
                        @BCType
                        @PointRange or PointList

레퍼런스:
    - CGNS Standard Interface Data Structures (SIDS) v4.4.
    - hdf5_layout.md — github.com/CGNS/CGNS docs.

CLAUDE.md 정책:
    - h5py optional (graceful skip).
    - 외부 lib 신규 의존 0 (h5py 는 이미 환경에 있음).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


# CGNS ElementType_t enum (SIDS v4.4):
ELEMENT_TYPE = {
    "TRI_3": 5,
    "QUAD_4": 7,
    "TETRA_4": 10,
    "PYRA_5": 12,
    "PENTA_6": 14,    # wedge / prism
    "HEXA_8": 17,
    "MIXED": 20,
    "NGON_n": 22,     # polyhedral n-gon face
    "NFACE_n": 23,    # polyhedral cell list of NGON ids
}


@dataclass
class CGNSWriteResult:
    """CGNS write result."""

    success: bool
    output_path: str = ""
    n_nodes: int = 0
    n_cells: int = 0
    n_zones: int = 0
    n_bc: int = 0
    elapsed: float = 0.0
    backend: str = ""
    message: str = ""


def _create_cgns_node(
    parent: Any,
    name: str,
    label: str,
    data: np.ndarray | None = None,
    data_type: str = "MT",
) -> Any:
    """CGNS node helper: HDF5 group with required attributes.

    label: CGNS node label (CGNSBase_t, Zone_t, ...).
    data_type: "MT" (no data), "I4" (int32), "R4" (float32), "R8" (float64),
               "C1" (string).
    """
    grp = parent.create_group(name)
    grp.attrs["label"] = np.bytes_(label.encode("ascii"))
    grp.attrs["name"] = np.bytes_(name.encode("ascii"))
    grp.attrs["type"] = np.bytes_(data_type.encode("ascii"))
    if data is not None:
        grp.create_dataset(" data", data=data)
    grp.attrs["flags"] = np.int32(1)
    return grp


def write_cgns(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    base_name: str = "Base",
    zone_name: str = "Zone-1",
) -> CGNSWriteResult:
    """OpenFOAM polyMesh → CGNS HDF5.

    Args:
        polymesh_dir: OpenFOAM polyMesh 디렉터리.
        output_path: 출력 .cgns 파일 경로.
        base_name / zone_name: CGNS Base/Zone 노드 이름.
    """
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    pm_path = Path(polymesh_dir)

    try:
        import h5py
    except ImportError:
        return CGNSWriteResult(
            success=False, output_path=str(out),
            backend="skip", message="h5py not installed",
            elapsed=time.perf_counter() - t0,
        )

    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(pm_path)
    except Exception as exc:
        return CGNSWriteResult(
            success=False, output_path=str(out),
            backend="skip",
            message=f"poly_mesh_reader unavailable: {exc!s:.60}",
            elapsed=time.perf_counter() - t0,
        )

    points = np.asarray(pm.get("points", []), dtype=np.float64)
    faces_list = list(pm.get("faces", []))
    owner = np.asarray(pm.get("owner", []), dtype=np.int64)
    neighbour = np.asarray(pm.get("neighbour", []), dtype=np.int64)
    boundary = list(pm.get("boundary", []))

    n_pts = int(points.shape[0])
    n_cells = int(owner.max() + 1) if owner.size else 0
    n_int = int(neighbour.size)
    n_total_faces = len(faces_list)

    if n_pts == 0 or n_cells == 0:
        return CGNSWriteResult(
            success=False, output_path=str(out),
            backend="h5py", message="empty mesh",
            elapsed=time.perf_counter() - t0,
        )

    # Polyhedral mesh — NGON_n (faces) + NFACE_n (cell→face lists).
    # NGON_n connectivity: per face: [n_verts, v1, v2, ...].
    ngon_conn: list[int] = []
    for f in faces_list:
        ngon_conn.append(len(f))
        # CGNS 는 1-based.
        ngon_conn.extend([int(v) + 1 for v in f])
    ngon_arr = np.asarray(ngon_conn, dtype=np.int32)

    # NFACE_n: cell 별 face list (1-based, sign 으로 owner/neighbour 표시).
    nface_per_cell: list[list[int]] = [[] for _ in range(n_cells)]
    for fi in range(n_total_faces):
        if fi < int(owner.size):
            # owner 측은 양수.
            nface_per_cell[int(owner[fi])].append(fi + 1)
        if fi < n_int and fi < int(neighbour.size):
            # neighbour 측은 음수 (CGNS 관습).
            nface_per_cell[int(neighbour[fi])].append(-(fi + 1))

    nface_conn: list[int] = []
    for cf in nface_per_cell:
        nface_conn.append(len(cf))
        nface_conn.extend(cf)
    nface_arr = np.asarray(nface_conn, dtype=np.int32)

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with h5py.File(str(out), "w") as f:
            # Root attrs.
            f.attrs["name"] = np.bytes_(b"HDF5 MotherNode")
            f.attrs["label"] = np.bytes_(b"Root Node of HDF5 File")
            f.attrs["type"] = np.bytes_(b"MT")
            f.attrs["flags"] = np.int32(1)

            # CGNSLibraryVersion node.
            ver = _create_cgns_node(
                f, "CGNSLibraryVersion", "CGNSLibraryVersion_t",
                data=np.array([4.4], dtype=np.float32), data_type="R4",
            )

            # Base node.
            base = _create_cgns_node(
                f, base_name, "CGNSBase_t",
                data=np.array([3, 3], dtype=np.int32), data_type="I4",
            )

            # Zone node.
            zone_size = np.array(
                [[n_pts, n_cells, 0]], dtype=np.int32,
            ).T  # CGNS: shape (3, NIndexDim), 여기선 (3, 1).
            zone = _create_cgns_node(
                base, zone_name, "Zone_t",
                data=zone_size, data_type="I4",
            )

            # ZoneType (Unstructured).
            _create_cgns_node(
                zone, "ZoneType", "ZoneType_t",
                data=np.frombuffer(b"Unstructured", dtype="S1"),
                data_type="C1",
            )

            # GridCoordinates.
            gc = _create_cgns_node(
                zone, "GridCoordinates", "GridCoordinates_t",
            )
            for i, axis in enumerate(("CoordinateX", "CoordinateY", "CoordinateZ")):
                _create_cgns_node(
                    gc, axis, "DataArray_t",
                    data=points[:, i].astype(np.float64),
                    data_type="R8",
                )

            # NGON_n (faces).
            ngon = _create_cgns_node(
                zone, "NGonElements", "Elements_t",
                data=np.array([ELEMENT_TYPE["NGON_n"], 0], dtype=np.int32),
                data_type="I4",
            )
            _create_cgns_node(
                ngon, "ElementRange", "IndexRange_t",
                data=np.array([1, n_total_faces], dtype=np.int32),
                data_type="I4",
            )
            _create_cgns_node(
                ngon, "ElementConnectivity", "DataArray_t",
                data=ngon_arr, data_type="I4",
            )

            # NFACE_n (cells as list of face IDs).
            nface = _create_cgns_node(
                zone, "NFaceElements", "Elements_t",
                data=np.array([ELEMENT_TYPE["NFACE_n"], 0], dtype=np.int32),
                data_type="I4",
            )
            _create_cgns_node(
                nface, "ElementRange", "IndexRange_t",
                data=np.array([n_total_faces + 1, n_total_faces + n_cells], dtype=np.int32),
                data_type="I4",
            )
            _create_cgns_node(
                nface, "ElementConnectivity", "DataArray_t",
                data=nface_arr, data_type="I4",
            )

            # ZoneBC + per-patch BC nodes.
            zbc = _create_cgns_node(zone, "ZoneBC", "ZoneBC_t")
            n_bc_patches = 0
            for pi, patch in enumerate(boundary):
                start = int(patch.get("startFace", 0))
                nf = int(patch.get("nFaces", 0))
                if nf == 0:
                    continue
                name = str(patch.get("name", f"patch-{pi}"))
                bc_type = str(patch.get("type", "BCWall")).lower()
                bc_type_cgns = {
                    "wall": "BCWall",
                    "patch": "BCFarfield",
                    "symmetry": "BCSymmetryPlane",
                    "empty": "BCExtrapolate",
                }.get(bc_type, "BCFarfield")

                bc = _create_cgns_node(
                    zbc, name, "BC_t",
                    data=np.frombuffer(bc_type_cgns.encode("ascii"), dtype="S1"),
                    data_type="C1",
                )
                # PointRange (face IDs as 1-based range).
                _create_cgns_node(
                    bc, "PointRange", "IndexRange_t",
                    data=np.array([start + 1, start + nf], dtype=np.int32),
                    data_type="I4",
                )
                # GridLocation = FaceCenter.
                _create_cgns_node(
                    bc, "GridLocation", "GridLocation_t",
                    data=np.frombuffer(b"FaceCenter", dtype="S1"),
                    data_type="C1",
                )
                n_bc_patches += 1

        return CGNSWriteResult(
            success=True, output_path=str(out),
            n_nodes=n_pts, n_cells=n_cells,
            n_zones=1, n_bc=n_bc_patches,
            backend="h5py",
            elapsed=time.perf_counter() - t0,
            message=(
                f"CGNS HDF5 written ({n_pts} nodes, {n_cells} cells, "
                f"{n_total_faces} faces, {n_bc_patches} BC patches). "
                f"NGON_n + NFACE_n polyhedral. CGNS 4.4 SIDS-compatible."
            ),
        )
    except Exception as exc:
        return CGNSWriteResult(
            success=False, output_path=str(out),
            backend="h5py", message=f"write error: {exc!s:.80}",
            elapsed=time.perf_counter() - t0,
        )
