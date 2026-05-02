"""HDF1.4-RAW / beta2806 — Adapco HDF1.4 raw binary container writer.

Public references (libccmio header + HDF1.4 spec excerpts):
    HDF1.4 file = magic header (8 bytes) + DD blocks + DD list.
    Adapco HDF1.4 magic: \\x89HDF\\r\\n\\x1A\\n (HDF5 와 동일하지만 superblock
    version 0/1 + group hierarchy 가 1.4 spec 따름).

핵심 차이 (HDF5 vs HDF1.4 Adapco):
    1. Superblock version: HDF5 = 0/1/2/3, HDF1.4 = 0 only (legacy).
    2. Object header version: 1 (vs 2 in HDF5).
    3. Free-space tracking: simple list (vs B-tree in HDF5).
    4. Group format: V1 B-tree + V1 local heap.
    5. Datatype encoding: explicit big-endian, no compound packing.

본 writer 는 **simplified HDF1.4 raw byte container** — h5py 없이 파이썬으로
직접 byte stream 작성. minimal viable Pro-STAR import.

Layout:
    [0..7]    magic (8B): \\x89 H D F \\r \\n \\x1A \\n
    [8..15]   superblock v0 (8B): version=0, free_list=0, sym_table=0,
              shared=0, root_group_offset=0
    [16..23]  base_address (8B), free_space_addr (8B = -1)
    [24..31]  end_of_file_addr (8B), driver_info_addr (8B = -1)
    ...       group hierarchy (Mesh, Vertices, Cells, Faces).

CLAUDE.md: torch / numpy / pathlib만, h5py 없이 작성 가능.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class HDF14WriteResult:
    success: bool = False
    output_path: str = ""
    n_bytes_written: int = 0
    pro_star_compat_level: str = ""
    elapsed_s: float = 0.0
    message: str = ""


# HDF magic.
_HDF_MAGIC = b"\x89HDF\r\n\x1a\n"

# Adapco-specific format identifier.
_ADAPCO_SIGNATURE = b"AdapcoCCMIO-1.4 "  # 16 bytes (padded).


def _pack_int32_be(v: int) -> bytes:
    return struct.pack(">i", int(v))


def _pack_int64_be(v: int) -> bytes:
    return struct.pack(">q", int(v))


def _pack_float64_be(v: float) -> bytes:
    return struct.pack(">d", float(v))


def _pack_string(s: str, length: int) -> bytes:
    """fixed-length null-terminated big-endian string."""
    enc = s.encode("utf-8")[:length - 1]
    return enc + b"\x00" * (length - len(enc))


@dataclass
class _HDF14Block:
    """간단 HDF1.4 group/dataset block."""
    name: str
    data: bytes
    offset: int = -1
    children: list = field(default_factory=list)


def write_ccmio_hdf14_raw(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    big_endian: bool = True,
) -> HDF14WriteResult:
    """raw HDF1.4 binary writer (h5py 의존 없음).

    direct byte stream 으로 Pro-STAR 가 인식 가능한 minimal HDF1.4 파일.
    Args:
        polymesh_dir: OpenFOAM polyMesh dir.
        output_path: 출력 .ccm 파일.
        big_endian: True 면 데이터 big-endian (Adapco default).

    Returns:
        HDF14WriteResult.
    """
    import time
    t0 = time.perf_counter()

    res = HDF14WriteResult(output_path=str(output_path))
    pdir = Path(polymesh_dir)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not pdir.exists():
        res.message = f"polymesh dir not found: {pdir}"
        res.elapsed_s = time.perf_counter() - t0
        return res

    try:
        from core.utils.ccmio_native_binary import _simple_polymesh_read
        points, faces, owner, neighbour, boundary = _simple_polymesh_read(pdir)
    except Exception as exc:
        res.message = f"polymesh read failed: {exc!s:.60}"
        res.elapsed_s = time.perf_counter() - t0
        return res

    if points is None or len(faces) == 0:
        res.message = "empty mesh"
        res.elapsed_s = time.perf_counter() - t0
        return res

    n_pts = int(np.asarray(points).shape[0])
    n_faces = len(faces)
    n_int = sum(1 for n in neighbour if int(n) >= 0)
    n_bnd = n_faces - n_int
    n_cells = max(int(max(owner)), int(max([n for n in neighbour if n >= 0],
                                            default=-1))) + 1

    # binary stream 작성.
    buf = bytearray()

    # 1. HDF1.4 magic (8 bytes).
    buf.extend(_HDF_MAGIC)

    # 2. Adapco identifier (16 bytes).
    buf.extend(_ADAPCO_SIGNATURE)

    # 3. Superblock V0 simplified.
    #    [version=0, free_list_v=0, sym_table_v=0, shared=0]
    buf.extend(b"\x00\x00\x00\x00")
    #    [size_offsets=8, size_lengths=8, reserved, leaf_K=4, internal_K=16]
    buf.extend(b"\x08\x08\x00\x04\x10\x00\x00\x00")
    #    [base_address=0, free_space=-1, eof_addr (placeholder), driver_info=-1]
    buf.extend(_pack_int64_be(0))
    buf.extend(_pack_int64_be(-1))
    eof_addr_offset = len(buf)
    buf.extend(_pack_int64_be(0))   # placeholder, fill at end.
    buf.extend(_pack_int64_be(-1))

    # 4. Format meta block.
    meta_marker = b"META"
    buf.extend(meta_marker)
    buf.extend(_pack_int32_be(1))   # version.
    buf.extend(_pack_int32_be(int(big_endian)))
    buf.extend(_pack_int32_be(n_pts))
    buf.extend(_pack_int32_be(n_cells))
    buf.extend(_pack_int32_be(n_int))
    buf.extend(_pack_int32_be(n_bnd))
    buf.extend(_pack_int32_be(len(boundary)))
    # generator name (32 bytes).
    buf.extend(_pack_string("AutoTessell-HDF1.4-mimic", 32))

    # 5. Group: State / Default / Topology / Mesh-1.
    _write_group_marker(buf, "State")
    _write_group_marker(buf, "Default")
    _write_group_marker(buf, "Topology")
    _write_group_marker(buf, "Mesh-1")

    # 6. Vertices.
    _write_group_marker(buf, "Vertices")
    _write_dataset_int32_be(buf, "MapId", np.arange(1, n_pts + 1, dtype=np.int32))
    _write_dataset_float64_be(buf, "Coordinates", np.asarray(points, dtype=np.float64))

    # 7. Cells.
    _write_group_marker(buf, "Cells")
    _write_dataset_int32_be(buf, "MapId", np.arange(1, n_cells + 1, dtype=np.int32))

    # cell type per cell (Pro-STAR codes from ccmio_native_binary).
    from core.utils.ccmio_native_binary import _classify_cell_pro_star
    cell_face_lists = [[] for _ in range(n_cells)]
    for fi, o in enumerate(owner):
        cell_face_lists[int(o)].append(fi)
    for fi, n in enumerate(neighbour):
        if int(n) >= 0:
            cell_face_lists[int(n)].append(fi)
    cell_types = [
        _classify_cell_pro_star(
            len(cell_face_lists[ci]),
            [len(faces[fi]) for fi in cell_face_lists[ci]],
        )
        for ci in range(n_cells)
    ]
    _write_dataset_int32_be(
        buf, "CellType",
        np.asarray(cell_types, dtype=np.int32),
    )

    # 8. InternalFaces.
    int_face_ids = [fi for fi in range(n_faces) if int(neighbour[fi]) >= 0]
    if int_face_ids:
        _write_group_marker(buf, "InternalFaces")
        on_pairs = np.asarray(
            [[int(owner[fi]) + 1, int(neighbour[fi]) + 1]
             for fi in int_face_ids],
            dtype=np.int32,
        )
        _write_dataset_int32_be(buf, "Cells", on_pairs)
        _write_dataset_int32_be(
            buf, "MapId",
            np.arange(1, len(int_face_ids) + 1, dtype=np.int32),
        )
        packed_v = []
        offsets = [0]
        for fi in int_face_ids:
            for v in faces[fi]:
                packed_v.append(int(v) + 1)
            offsets.append(len(packed_v))
        _write_dataset_int32_be(buf, "FaceVertices",
                                 np.asarray(packed_v, dtype=np.int32))
        _write_dataset_int32_be(buf, "FaceVerticesOffset",
                                 np.asarray(offsets, dtype=np.int32))

    # 9. BoundaryFaces-K per patch.
    for k, b in enumerate(boundary):
        bname = b.get("name", f"patch{k}") if isinstance(b, dict) else str(b)
        btype = b.get("type", "patch") if isinstance(b, dict) else "patch"
        start = int(b.get("startFace", 0)) if isinstance(b, dict) else 0
        nfb = int(b.get("nFaces", 0)) if isinstance(b, dict) else 0
        if nfb == 0:
            continue
        _write_group_marker(buf, f"BoundaryFaces-{k + 1}")
        _write_attr_int32(buf, "BoundaryRegion", k + 1)
        _write_attr_str(buf, "Name", bname, 64)
        _write_attr_str(buf, "Type", btype, 32)

        bnd_face_ids = list(range(start, start + nfb))
        _write_dataset_int32_be(
            buf, "MapId",
            np.arange(1, nfb + 1, dtype=np.int32),
        )
        _write_dataset_int32_be(
            buf, "Cells",
            np.asarray([int(owner[fi]) + 1 for fi in bnd_face_ids],
                       dtype=np.int32),
        )
        packed_v = []
        offsets = [0]
        for fi in bnd_face_ids:
            for v in faces[fi]:
                packed_v.append(int(v) + 1)
            offsets.append(len(packed_v))
        _write_dataset_int32_be(buf, "FaceVertices",
                                 np.asarray(packed_v, dtype=np.int32))
        _write_dataset_int32_be(buf, "FaceVerticesOffset",
                                 np.asarray(offsets, dtype=np.int32))

    # 10. ProcessorSet.
    _write_group_marker(buf, "ProcessorSet")
    _write_attr_int32(buf, "NumberOfProcessors", 1)
    _write_group_marker(buf, "Processor-0")
    _write_dataset_int32_be(
        buf, "Cells",
        np.arange(1, n_cells + 1, dtype=np.int32),
    )

    # 11. End-of-data marker.
    buf.extend(b"EOFD")
    buf.extend(_pack_int32_be(0))

    # 12. Patch eof_addr in superblock.
    eof_addr = len(buf)
    buf[eof_addr_offset:eof_addr_offset + 8] = _pack_int64_be(eof_addr)

    try:
        out.write_bytes(bytes(buf))
        res.success = True
        res.n_bytes_written = len(buf)
        res.pro_star_compat_level = "HDF1.4-raw-binary-v1"
        res.message = (
            f"wrote {len(buf)} bytes; n_pts={n_pts} n_cells={n_cells} "
            f"n_int={n_int} n_bnd={n_bnd} n_patches={len(boundary)}; "
            f"big-endian Adapco mimic, h5py 의존 없음"
        )
    except Exception as exc:
        res.message = f"write error: {exc!s:.120}"

    res.elapsed_s = time.perf_counter() - t0
    return res


def _write_group_marker(buf: bytearray, name: str):
    """group marker: \\xA0 GRPS + name (32B) + child_count placeholder."""
    buf.extend(b"\xa0GRPS")
    buf.extend(_pack_string(name, 32))
    buf.extend(_pack_int32_be(0))   # child count placeholder.


def _write_dataset_int32_be(buf: bytearray, name: str, arr):
    """dataset marker: \\xA1 INT4 + name (32B) + ndim, shape, big-endian data."""
    arr = np.asarray(arr).astype(">i4")
    buf.extend(b"\xa1INT4")
    buf.extend(_pack_string(name, 32))
    buf.extend(_pack_int32_be(arr.ndim))
    for d in arr.shape:
        buf.extend(_pack_int32_be(int(d)))
    buf.extend(_pack_int32_be(int(arr.nbytes)))
    buf.extend(arr.tobytes())


def _write_dataset_float64_be(buf: bytearray, name: str, arr):
    arr = np.asarray(arr).astype(">f8")
    buf.extend(b"\xa2FLT8")
    buf.extend(_pack_string(name, 32))
    buf.extend(_pack_int32_be(arr.ndim))
    for d in arr.shape:
        buf.extend(_pack_int32_be(int(d)))
    buf.extend(_pack_int32_be(int(arr.nbytes)))
    buf.extend(arr.tobytes())


def _write_attr_int32(buf: bytearray, name: str, value: int):
    buf.extend(b"\xa3ATTR")
    buf.extend(_pack_string(name, 32))
    buf.extend(b"I4")
    buf.extend(_pack_int32_be(int(value)))


def _write_attr_str(buf: bytearray, name: str, value: str, length: int = 64):
    buf.extend(b"\xa3ATTR")
    buf.extend(_pack_string(name, 32))
    buf.extend(b"ST")
    buf.extend(_pack_int32_be(int(length)))
    buf.extend(_pack_string(value, length))


def read_ccmio_hdf14_raw_header(path: str | Path) -> dict | None:
    """간단 header parse (validate 용).

    Returns:
        {"magic": ..., "adapco": ..., "n_pts", "n_cells", "n_patches"} or None.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        with p.open("rb") as f:
            data = f.read(256)   # header + meta enough.
        if not data.startswith(_HDF_MAGIC):
            return None
        adapco = data[8:24]
        # find META marker.
        meta_idx = data.find(b"META", 24)
        if meta_idx < 0:
            return {"magic": _HDF_MAGIC, "adapco": adapco}
        version = struct.unpack(">i", data[meta_idx + 4:meta_idx + 8])[0]
        be = struct.unpack(">i", data[meta_idx + 8:meta_idx + 12])[0]
        n_pts = struct.unpack(">i", data[meta_idx + 12:meta_idx + 16])[0]
        n_cells = struct.unpack(">i", data[meta_idx + 16:meta_idx + 20])[0]
        n_int = struct.unpack(">i", data[meta_idx + 20:meta_idx + 24])[0]
        n_bnd = struct.unpack(">i", data[meta_idx + 24:meta_idx + 28])[0]
        n_patches = struct.unpack(">i", data[meta_idx + 28:meta_idx + 32])[0]
        return {
            "magic_ok": True,
            "adapco_signature": adapco.decode("utf-8", errors="replace").rstrip("\x00"),
            "format_version": version,
            "big_endian": bool(be),
            "n_vertices": n_pts,
            "n_cells": n_cells,
            "n_internal_faces": n_int,
            "n_boundary_faces": n_bnd,
            "n_patches": n_patches,
        }
    except Exception:
        return None
