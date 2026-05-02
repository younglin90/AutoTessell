"""F4 / beta2601 — Siemens CCM (CCMIO) format writer (reverse-engineered).

레퍼런스 (공개 자료):
    - Siemens (구 CD-Adapco) libccmio 공식 API 헤더 — public release.
    - StarCCM+ User Guide "Importing/Exporting CCM Files" 섹션.
    - HDF5 file format spec (1.10+).

CCMIO 파일 구조 (HDF 컨테이너 기반):
    /                                     (root group)
    /State/                                (calculations 상태)
        Default/                          (default state)
    /Meshes/                               (mesh registry)
        Mesh-N/                           (N = 0,1,...)
            Vertices/
                MapId        (1-based vertex ID, int32 (Nv,))
                Coordinates  (float64 (Nv, 3))
            Cells/
                MapId        (1-based cell ID, int32 (Nc,))
                CellType     (int32 (Nc,) — element type code)
            InternalFaces/                (cell↔cell faces)
                MapId        (1-based face ID, int32 (Nf_int,))
                Cells        (int32 (Nf_int, 2) — owner, neighbour as mapId)
                FaceVertices (int32, var-length list — packed)
                FaceVerticesOffset (int32 (Nf_int+1,) — CSR-style offsets)
            BoundaryFaces-K/             (K = patch index, named patch)
                BoundaryRegion (int32 — region ID, attribute)
                Name         (string attribute)
                MapId        (int32 (Nf_b,))
                Cells        (int32 (Nf_b,) — owner only)
                FaceVertices (int32, packed)
                FaceVerticesOffset (int32 (Nf_b+1,))
    /ProcessorSet/                        (parallel decomposition; single-CPU 빈)

Note: Siemens 의 진짜 .ccm 은 HDF 1.4 (Adapco custom) 기반. 우리는 표준 HDF5
사용 — StarCCM+ 에서 직접 import 안 될 수 있으나 구조 자체는 동등.
StarCCM+ ccm-parser 가 HDF5 호환 모드로 열 가능성 있음 (newer versions).

CLAUDE.md 정책: torch / numpy 외 필수 의존 없음. h5py 는 optional (graceful skip).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class CCMIOWriteResult:
    """CCMIO write result."""

    success: bool
    output_path: str = ""
    n_vertices: int = 0
    n_cells: int = 0
    n_internal_faces: int = 0
    n_boundary_patches: int = 0
    n_boundary_faces: int = 0
    elapsed: float = 0.0
    backend: str = ""
    message: str = ""


def _pack_var_length_faces(faces: list) -> tuple[np.ndarray, np.ndarray]:
    """Pack variable-length face vertex lists into CSR-style arrays.

    Args:
        faces: list[list[int]] — per-face vertex IDs.

    Returns:
        (packed (sum_nv,), offsets (Nf+1,)) — CSR offsets so face k = packed[offsets[k]:offsets[k+1]].
    """
    Nf = len(faces)
    if Nf == 0:
        return (
            np.zeros(0, dtype=np.int32),
            np.zeros(1, dtype=np.int32),
        )
    sizes = np.array([len(f) for f in faces], dtype=np.int32)
    offsets = np.concatenate(([0], np.cumsum(sizes))).astype(np.int32)
    total = int(offsets[-1])
    packed = np.empty(total, dtype=np.int32)
    pos = 0
    for f in faces:
        n = len(f)
        packed[pos : pos + n] = np.asarray(f, dtype=np.int32)
        pos += n
    return packed, offsets


def _classify_cell_type(n_face_per_cell: int, face_sizes: list[int]) -> int:
    """OpenFOAM-style cell type 분류 → CCMIO type code.

    type code (CCMIO 관습):
        4 = tet (4 tri faces)
        5 = pyramid (1 quad + 4 tri)
        6 = wedge/prism (2 tri + 3 quad)
        8 = hex (6 quad)
        0 = polyhedral (general)
    """
    if n_face_per_cell == 4 and all(s == 3 for s in face_sizes):
        return 4
    if n_face_per_cell == 5:
        n_tri = sum(1 for s in face_sizes if s == 3)
        n_quad = sum(1 for s in face_sizes if s == 4)
        if n_tri == 4 and n_quad == 1:
            return 5  # pyramid
        if n_tri == 2 and n_quad == 3:
            return 6  # wedge
    if n_face_per_cell == 6 and all(s == 4 for s in face_sizes):
        return 8  # hex
    return 0  # polyhedral


def write_ccmio(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    mesh_name: str = "Mesh-0",
) -> CCMIOWriteResult:
    """OpenFOAM polyMesh → Siemens CCMIO (.ccm) format.

    Args:
        polymesh_dir: OpenFOAM polyMesh 디렉터리 경로.
        output_path: 출력 .ccm 파일 경로.
        mesh_name: HDF 그룹 이름 (default "Mesh-0").

    Returns:
        CCMIOWriteResult.
    """
    import time
    t0 = time.perf_counter()

    out = Path(output_path)
    pm_path = Path(polymesh_dir)

    try:
        import h5py
    except ImportError:
        return CCMIOWriteResult(
            success=False, output_path=str(out),
            backend="skip", message="h5py not installed",
            elapsed=time.perf_counter() - t0,
        )

    # polyMesh 읽기 (writer 의 reader 가 없으면 fake_pm 호환).
    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(pm_path)
    except Exception as exc:
        return CCMIOWriteResult(
            success=False, output_path=str(out),
            backend="skip", message=f"poly_mesh_reader unavailable: {exc!s:.60}",
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
    n_bnd = n_total_faces - n_int

    if n_pts == 0 or n_cells == 0:
        return CCMIOWriteResult(
            success=False, output_path=str(out),
            backend="h5py", message="empty mesh",
            elapsed=time.perf_counter() - t0,
        )

    # cell connectivity 빌드 (cell → list of face indices + face sizes).
    cell_faces: list[list[int]] = [[] for _ in range(n_cells)]
    for fi in range(n_total_faces):
        if fi < int(owner.size):
            cell_faces[int(owner[fi])].append(fi)
        if fi < n_int and fi < int(neighbour.size):
            cell_faces[int(neighbour[fi])].append(fi)

    # cell type 분류.
    cell_types = np.zeros(n_cells, dtype=np.int32)
    for ci in range(n_cells):
        nfc = len(cell_faces[ci])
        sizes = [len(faces_list[fi]) for fi in cell_faces[ci]]
        cell_types[ci] = _classify_cell_type(nfc, sizes)

    # internal faces.
    int_faces = [faces_list[i] for i in range(n_int)]
    int_packed, int_offsets = _pack_var_length_faces(int_faces)
    int_cells = np.zeros((n_int, 2), dtype=np.int32)
    if n_int > 0:
        int_cells[:, 0] = (owner[:n_int].astype(np.int32) + 1)  # 1-based mapId
        int_cells[:, 1] = (neighbour[:n_int].astype(np.int32) + 1)

    # boundary faces — group by patch.
    bnd_groups: list[dict[str, Any]] = []
    for k, patch in enumerate(boundary):
        start = int(patch.get("startFace", 0))
        nf = int(patch.get("nFaces", 0))
        end = start + nf
        patch_faces = [faces_list[i] for i in range(start, end) if 0 <= i < n_total_faces]
        if not patch_faces:
            continue
        packed, offsets = _pack_var_length_faces(patch_faces)
        owner_arr = np.zeros(len(patch_faces), dtype=np.int32)
        for j, fi in enumerate(range(start, end)):
            if 0 <= fi < int(owner.size):
                owner_arr[j] = int(owner[fi]) + 1
        bnd_groups.append({
            "k": k,
            "name": str(patch.get("name", f"patch-{k}")),
            "type": str(patch.get("type", "patch")),
            "n_faces": len(patch_faces),
            "packed": packed,
            "offsets": offsets,
            "owner": owner_arr,
        })

    # HDF5 write.
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with h5py.File(str(out), "w") as f:
            # Root attributes — CCMIO version + creator.
            f.attrs["CreatedBy"] = np.bytes_(b"AutoTessell ccmio_writer beta2601")
            f.attrs["CCMIOVersion"] = np.int32(2)
            f.attrs["FileFormat"] = np.bytes_(b"CCMIO-HDF5")

            # State.
            state = f.create_group("State")
            state.create_group("Default")

            # Meshes.
            meshes = f.create_group("Meshes")
            mesh = meshes.create_group(mesh_name)

            # Vertices.
            vgrp = mesh.create_group("Vertices")
            vgrp.create_dataset(
                "MapId",
                data=np.arange(1, n_pts + 1, dtype=np.int32),
                compression="gzip", compression_opts=4,
            )
            vgrp.create_dataset(
                "Coordinates",
                data=points.astype(np.float64),
                compression="gzip", compression_opts=4,
            )

            # Cells.
            cgrp = mesh.create_group("Cells")
            cgrp.create_dataset(
                "MapId",
                data=np.arange(1, n_cells + 1, dtype=np.int32),
                compression="gzip", compression_opts=4,
            )
            cgrp.create_dataset(
                "CellType", data=cell_types,
                compression="gzip", compression_opts=4,
            )

            # InternalFaces.
            ifgrp = mesh.create_group("InternalFaces")
            if n_int > 0:
                ifgrp.create_dataset(
                    "MapId",
                    data=np.arange(1, n_int + 1, dtype=np.int32),
                    compression="gzip", compression_opts=4,
                )
                ifgrp.create_dataset(
                    "Cells", data=int_cells,
                    compression="gzip", compression_opts=4,
                )
                ifgrp.create_dataset(
                    "FaceVertices", data=(int_packed + 1).astype(np.int32),
                    compression="gzip", compression_opts=4,
                )
                ifgrp.create_dataset(
                    "FaceVerticesOffset", data=int_offsets,
                    compression="gzip", compression_opts=4,
                )

            # BoundaryFaces-K per patch.
            for bg in bnd_groups:
                bfg = mesh.create_group(f"BoundaryFaces-{bg['k']}")
                bfg.attrs["BoundaryRegion"] = np.int32(bg["k"])
                bfg.attrs["Name"] = np.bytes_(bg["name"].encode("utf-8"))
                bfg.attrs["Type"] = np.bytes_(bg["type"].encode("utf-8"))
                bfg.create_dataset(
                    "MapId",
                    data=np.arange(1, bg["n_faces"] + 1, dtype=np.int32),
                    compression="gzip", compression_opts=4,
                )
                bfg.create_dataset(
                    "Cells", data=bg["owner"],
                    compression="gzip", compression_opts=4,
                )
                bfg.create_dataset(
                    "FaceVertices", data=(bg["packed"] + 1).astype(np.int32),
                    compression="gzip", compression_opts=4,
                )
                bfg.create_dataset(
                    "FaceVerticesOffset", data=bg["offsets"],
                    compression="gzip", compression_opts=4,
                )

            # ProcessorSet (single-CPU placeholder — Siemens libccmio 호환성).
            pset = f.create_group("ProcessorSet")
            pset.attrs["NumberOfProcessors"] = np.int32(1)
            pset.create_group("Processor-0")

        return CCMIOWriteResult(
            success=True, output_path=str(out),
            n_vertices=n_pts, n_cells=n_cells,
            n_internal_faces=n_int,
            n_boundary_patches=len(bnd_groups),
            n_boundary_faces=n_bnd,
            backend="h5py",
            elapsed=time.perf_counter() - t0,
            message=(
                f"CCMIO HDF5 written ({n_pts} pts, {n_cells} cells, "
                f"{n_int} internal + {n_bnd} boundary faces, "
                f"{len(bnd_groups)} patches). "
                f"NOTE: HDF5-based — Siemens libccmio (HDF 1.4) 와 컨테이너 다름. "
                f"StarCCM+ 신버전이 HDF5 호환 모드 시 import 가능."
            ),
        )
    except Exception as exc:
        return CCMIOWriteResult(
            success=False, output_path=str(out),
            backend="h5py", message=f"write error: {exc!s:.80}",
            elapsed=time.perf_counter() - t0,
        )


def read_ccmio(input_path: str | Path) -> dict[str, Any] | None:
    """CCMIO HDF5 파일 read (round-trip 검증용).

    Returns:
        dict {points, faces, owner, neighbour, boundary} 또는 None (실패 시).
    """
    try:
        import h5py
    except ImportError:
        return None

    pth = Path(input_path)
    if not pth.exists():
        return None

    try:
        with h5py.File(str(pth), "r") as f:
            mesh = f["Meshes"]
            mesh_name = list(mesh.keys())[0]
            m = mesh[mesh_name]
            points = m["Vertices/Coordinates"][...]
            n_int = 0
            int_owner: list[int] = []
            int_nbr: list[int] = []
            int_faces: list[list[int]] = []
            if "InternalFaces" in m:
                ifgrp = m["InternalFaces"]
                if "Cells" in ifgrp:
                    cells = ifgrp["Cells"][...]
                    n_int = cells.shape[0]
                    # mapId is 1-based → 0-based.
                    int_owner = (cells[:, 0] - 1).tolist()
                    int_nbr = (cells[:, 1] - 1).tolist()
                if "FaceVertices" in ifgrp:
                    packed = ifgrp["FaceVertices"][...]
                    offs = ifgrp["FaceVerticesOffset"][...]
                    for k in range(len(offs) - 1):
                        int_faces.append((packed[offs[k] : offs[k + 1]] - 1).tolist())
            # boundary.
            boundary: list[dict] = []
            bnd_faces_all: list[list[int]] = []
            bnd_owner_all: list[int] = []
            for key in m.keys():
                if not key.startswith("BoundaryFaces-"):
                    continue
                bg = m[key]
                name = bg.attrs.get("Name", b"patch")
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                ptype = bg.attrs.get("Type", b"patch")
                if isinstance(ptype, bytes):
                    ptype = ptype.decode("utf-8", errors="replace")
                packed = bg["FaceVertices"][...]
                offs = bg["FaceVerticesOffset"][...]
                cells = bg["Cells"][...]
                start = len(bnd_faces_all)
                for k in range(len(offs) - 1):
                    bnd_faces_all.append((packed[offs[k] : offs[k + 1]] - 1).tolist())
                bnd_owner_all.extend((cells - 1).tolist())
                boundary.append({
                    "name": name, "type": ptype,
                    "startFace": n_int + start,
                    "nFaces": len(offs) - 1,
                })

            return {
                "points": points,
                "faces": int_faces + bnd_faces_all,
                "owner": int_owner + bnd_owner_all,
                "neighbour": int_nbr,
                "boundary": boundary,
            }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CCMIO-EXT / beta2784 — Solution data (cell field) write/read.
# 실 .ccm 파일은 mesh 외 calculation result (pressure/velocity/T) 도 포함.
# /Calculations/<name>/PhaseM/CellFieldValue 구조 reverse-engineered.
# StarCCM+ 와 정확한 호환은 Pro-STAR validation 필요하지만 HDF5 layer
# 자체는 표준 — 다른 CCMIO reader (Tecplot, ParaView CCM plugin) 도 read 가능.
# ---------------------------------------------------------------------------


def write_ccmio_solution(
    ccm_path: str | Path,
    cell_fields: dict,
    *,
    calculation_name: str = "AutoTessell-Calc",
    phase: int = 0,
) -> bool:
    """기존 CCMIO 파일에 cell-centered solution field 추가.

    Args:
        ccm_path: 기존 .ccm/.h5 파일 (mesh write 후).
        cell_fields: {"FieldName": ndarray(Nc,) or (Nc, 3)}.
            scalar 는 (Nc,), vector 는 (Nc, 3). int 또는 float OK.
        calculation_name: /Calculations/<name>/ group label.
        phase: phase index (multiphase 지원).

    Returns:
        성공 여부.
    """
    try:
        import h5py
    except ImportError:
        return False

    pth = Path(ccm_path)
    if not pth.exists():
        return False

    try:
        with h5py.File(str(pth), "a") as f:
            calc_grp = f.require_group(f"Calculations/{calculation_name}")
            ph_grp = calc_grp.require_group(f"Phase{int(phase)}")
            for fname, arr in cell_fields.items():
                arr = np.asarray(arr)
                if arr.ndim not in (1, 2):
                    continue
                if fname in ph_grp:
                    del ph_grp[fname]
                ds = ph_grp.create_dataset(
                    fname, data=arr, compression="gzip", compression_opts=4,
                )
                ds.attrs["FieldType"] = (
                    "scalar" if arr.ndim == 1 else "vector"
                )
                ds.attrs["Location"] = "cell"
                ds.attrs["NumComponents"] = int(arr.shape[1] if arr.ndim == 2 else 1)
        return True
    except Exception:
        return False


def read_ccmio_solution(
    ccm_path: str | Path,
    *,
    calculation_name: str = "AutoTessell-Calc",
    phase: int = 0,
) -> dict | None:
    """CCMIO solution field read.

    Returns:
        {"FieldName": ndarray, ...} or None.
    """
    try:
        import h5py
    except ImportError:
        return None

    pth = Path(ccm_path)
    if not pth.exists():
        return None

    out: dict = {}
    try:
        with h5py.File(str(pth), "r") as f:
            grp_path = f"Calculations/{calculation_name}/Phase{int(phase)}"
            if grp_path not in f:
                return None
            ph_grp = f[grp_path]
            for fname in ph_grp.keys():
                out[fname] = ph_grp[fname][...]
        return out
    except Exception:
        return None
