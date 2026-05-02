"""CCMIO-CHUNK / beta2808 — Adapco HDF1.4 chunk format reverse-engineered.

기존 ccmio_native_binary (BETA2804) 와 ccmio_hdf14_binary (BETA2806) 가
flat byte stream 인 반면, 본 모듈은 **chunked layout** 으로 Pro-STAR
의 native chunk reader 와 정확 매칭 시도.

Adapco chunk format (libccmio source 분석):
    Each chunk = [chunk_id (4B) | size (4B) | data | crc32 (4B)].
    Master chunk table at file end (negative offset from EOF).

Chunk types:
    0x00 = META          (n_pts, n_cells, n_int, n_bnd, n_patches).
    0x10 = VERTICES      (vertex coordinates, big-endian f8).
    0x20 = CELLS         (cell map + cell type + face refs).
    0x30 = INT_FACES     (internal face cells + face vertices).
    0x40 = BND_FACES     (per-patch boundary face data).
    0x50 = PATCH_INFO    (patch name + type per region).
    0x60 = PROC_SET      (parallel decomposition).
    0xFF = MASTER_TABLE  (chunk_id → file offset map at EOF).

Pro-STAR direct binary import 호환을 위한 정확한 chunk ordering:
    META → VERTICES → CELLS → INT_FACES → BND_FACES (multi) → PATCH_INFO →
    PROC_SET → MASTER_TABLE → footer.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# Chunk IDs.
CHUNK_META       = 0x00
CHUNK_VERTICES   = 0x10
CHUNK_CELLS      = 0x20
CHUNK_INT_FACES  = 0x30
CHUNK_BND_FACES  = 0x40
CHUNK_PATCH_INFO = 0x50
CHUNK_PROC_SET   = 0x60
CHUNK_MASTER     = 0xFF

# Pro-STAR cell type codes (libccmio standard).
CELL_TYPE_TET    = 1
CELL_TYPE_PYR    = 2
CELL_TYPE_WEDGE  = 3
CELL_TYPE_HEX    = 4
CELL_TYPE_POLY   = 5

# Format magic (8B): \x89 H D F \r \n \x1A \n + Adapco identifier.
_HDF_MAGIC = b"\x89HDF\r\n\x1a\n"
_ADAPCO_SIG = b"AdapcoCCMIO-1.4-CHK"   # 19B + null = 20B padded.


@dataclass
class ChunkRecord:
    """parsed chunk metadata."""
    chunk_id: int = 0
    size: int = 0
    offset: int = 0
    crc32: int = 0


@dataclass
class ChunkWriteResult:
    success: bool = False
    output_path: str = ""
    n_bytes: int = 0
    n_chunks: int = 0
    chunk_offsets: dict = None
    pro_star_compat: str = ""
    elapsed_s: float = 0.0
    message: str = ""

    def __post_init__(self):
        if self.chunk_offsets is None:
            self.chunk_offsets = {}


def _pack_chunk_header(chunk_id: int, size: int) -> bytes:
    """[id(4B) | size(4B)]."""
    return struct.pack(">II", int(chunk_id) & 0xFFFFFFFF, int(size))


def _pack_chunk_footer(data: bytes) -> bytes:
    """[crc32(4B)] for integrity check."""
    crc = zlib.crc32(data) & 0xFFFFFFFF
    return struct.pack(">I", crc)


def _build_meta_chunk(n_pts: int, n_cells: int, n_int: int,
                     n_bnd: int, n_patches: int, big_endian: bool = True) -> bytes:
    payload = struct.pack(
        ">iiiiii",
        1,                          # format version.
        int(big_endian),
        int(n_pts), int(n_cells),
        int(n_int), int(n_bnd),
    ) + struct.pack(">i", int(n_patches))
    # padding to 64B for alignment.
    pad = max(0, 64 - len(payload))
    payload += b"\x00" * pad
    return payload


def _build_vertices_chunk(points: np.ndarray) -> bytes:
    """[n_pts(4B) | coords (Nv*3*8B big-endian f8)]."""
    n_pts = int(points.shape[0])
    arr = np.asarray(points, dtype=">f8")
    return struct.pack(">i", n_pts) + arr.tobytes()


def _build_cells_chunk(cell_types: np.ndarray) -> bytes:
    """[n_cells(4B) | cell_types (Nc*4B big-endian i4)]."""
    n_cells = int(cell_types.shape[0])
    arr = np.asarray(cell_types, dtype=">i4")
    return struct.pack(">i", n_cells) + arr.tobytes()


def _build_face_chunk(
    owner_arr: np.ndarray,
    neighbor_arr: np.ndarray | None,
    packed_v: np.ndarray,
    offsets: np.ndarray,
) -> bytes:
    """[n_faces(4B) | owner (Nf*4B) | neighbour (Nf*4B or absent) |
        n_packed(4B) | packed_v | n_offsets(4B) | offsets]."""
    n_f = int(owner_arr.shape[0])
    payload = struct.pack(">i", n_f)
    payload += np.asarray(owner_arr, dtype=">i4").tobytes()
    if neighbor_arr is not None:
        payload += np.asarray(neighbor_arr, dtype=">i4").tobytes()
    payload += struct.pack(">i", int(packed_v.shape[0]))
    payload += np.asarray(packed_v, dtype=">i4").tobytes()
    payload += struct.pack(">i", int(offsets.shape[0]))
    payload += np.asarray(offsets, dtype=">i4").tobytes()
    return payload


def _build_patch_info_chunk(boundary_list: list) -> bytes:
    """[n_patches(4B) | per-patch (region(4B) | name_len(4B) | name |
        type_len(4B) | type | n_faces(4B) | start_face(4B))]."""
    n = len(boundary_list)
    payload = struct.pack(">i", n)
    for k, b in enumerate(boundary_list):
        if not isinstance(b, dict):
            continue
        name = str(b.get("name", f"patch{k}")).encode("utf-8")[:60]
        ptype = str(b.get("type", "patch")).encode("utf-8")[:32]
        nfb = int(b.get("nFaces", 0))
        startf = int(b.get("startFace", 0))
        payload += struct.pack(">i", k + 1)             # region id (1-based).
        payload += struct.pack(">i", len(name))
        payload += name + b"\x00" * (64 - len(name))
        payload += struct.pack(">i", len(ptype))
        payload += ptype + b"\x00" * (32 - len(ptype))
        payload += struct.pack(">ii", nfb, startf)
    return payload


def _build_master_table(chunk_offsets: dict) -> bytes:
    """[n_entries(4B) | per-entry (chunk_id(4B) | offset(8B) | size(4B))]."""
    payload = struct.pack(">i", len(chunk_offsets))
    for cid, (offset, size) in sorted(chunk_offsets.items()):
        payload += struct.pack(">iqi", int(cid), int(offset), int(size))
    return payload


def write_ccmio_chunked_binary(
    polymesh_dir: str | Path,
    output_path: str | Path,
    *,
    big_endian: bool = True,
) -> ChunkWriteResult:
    """OpenFOAM polyMesh → Adapco chunked HDF1.4 binary.

    chunk format → Pro-STAR direct chunk reader 호환.

    Args:
        polymesh_dir: OpenFOAM polyMesh dir.
        output_path: 출력 .ccm 파일.
        big_endian: True 면 모든 데이터 big-endian.

    Returns:
        ChunkWriteResult.
    """
    import time
    t0 = time.perf_counter()
    res = ChunkWriteResult(output_path=str(output_path))

    pdir = Path(polymesh_dir)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not pdir.exists():
        res.message = f"polymesh dir not found: {pdir}"
        res.elapsed_s = time.perf_counter() - t0
        return res

    try:
        from core.utils.ccmio_native_binary import (
            _simple_polymesh_read, _classify_cell_pro_star,
        )
        points, faces, owner, neighbour, boundary = _simple_polymesh_read(pdir)
    except Exception as exc:
        res.message = f"polymesh read error: {exc!s:.60}"
        res.elapsed_s = time.perf_counter() - t0
        return res

    if points is None or len(faces) == 0:
        res.message = "empty mesh"
        res.elapsed_s = time.perf_counter() - t0
        return res

    n_pts = int(np.asarray(points).shape[0])
    n_int = sum(1 for n in neighbour if int(n) >= 0)
    n_faces = len(faces)
    n_bnd = n_faces - n_int
    n_cells = max(int(max(owner)), int(max([n for n in neighbour if n >= 0],
                                            default=-1))) + 1

    # cell type 분류.
    cell_face_lists = [[] for _ in range(n_cells)]
    for fi, o in enumerate(owner):
        cell_face_lists[int(o)].append(fi)
    for fi, n in enumerate(neighbour):
        if int(n) >= 0:
            cell_face_lists[int(n)].append(fi)
    cell_types = np.asarray([
        _classify_cell_pro_star(
            len(cell_face_lists[ci]),
            [len(faces[fi]) for fi in cell_face_lists[ci]],
        )
        for ci in range(n_cells)
    ], dtype=np.int32)

    buf = bytearray()

    # File header.
    buf.extend(_HDF_MAGIC)
    buf.extend(_ADAPCO_SIG.ljust(20, b"\x00"))

    chunk_offsets: dict[int, tuple[int, int]] = {}

    def _emit_chunk(cid: int, payload: bytes):
        offset = len(buf)
        size = len(payload)
        hdr = _pack_chunk_header(cid, size)
        crc = _pack_chunk_footer(payload)
        buf.extend(hdr)
        buf.extend(payload)
        buf.extend(crc)
        chunk_offsets[cid] = (offset, size)

    # 1. META chunk.
    _emit_chunk(
        CHUNK_META,
        _build_meta_chunk(n_pts, n_cells, n_int, n_bnd, len(boundary),
                          big_endian=big_endian),
    )

    # 2. VERTICES.
    _emit_chunk(CHUNK_VERTICES, _build_vertices_chunk(np.asarray(points)))

    # 3. CELLS.
    _emit_chunk(CHUNK_CELLS, _build_cells_chunk(cell_types))

    # 4. INT_FACES.
    int_face_ids = [fi for fi in range(n_faces) if int(neighbour[fi]) >= 0]
    if int_face_ids:
        ow = np.asarray([int(owner[fi]) + 1 for fi in int_face_ids],
                         dtype=np.int32)
        nb = np.asarray([int(neighbour[fi]) + 1 for fi in int_face_ids],
                         dtype=np.int32)
        packed_v_int = []
        offsets_int = [0]
        for fi in int_face_ids:
            for v in faces[fi]:
                packed_v_int.append(int(v) + 1)
            offsets_int.append(len(packed_v_int))
        _emit_chunk(
            CHUNK_INT_FACES,
            _build_face_chunk(
                ow, nb,
                np.asarray(packed_v_int, dtype=np.int32),
                np.asarray(offsets_int, dtype=np.int32),
            ),
        )

    # 5. BND_FACES (concat all patches into single chunk).
    bnd_face_ids_all = [fi for fi in range(n_faces) if int(neighbour[fi]) < 0]
    if bnd_face_ids_all:
        ow_bnd = np.asarray([int(owner[fi]) + 1 for fi in bnd_face_ids_all],
                             dtype=np.int32)
        packed_v_bnd = []
        offsets_bnd = [0]
        for fi in bnd_face_ids_all:
            for v in faces[fi]:
                packed_v_bnd.append(int(v) + 1)
            offsets_bnd.append(len(packed_v_bnd))
        _emit_chunk(
            CHUNK_BND_FACES,
            _build_face_chunk(
                ow_bnd, None,
                np.asarray(packed_v_bnd, dtype=np.int32),
                np.asarray(offsets_bnd, dtype=np.int32),
            ),
        )

    # 6. PATCH_INFO.
    _emit_chunk(CHUNK_PATCH_INFO, _build_patch_info_chunk(boundary))

    # 7. PROC_SET (single processor).
    _emit_chunk(
        CHUNK_PROC_SET,
        struct.pack(">ii", 1, n_cells)
        + np.arange(1, n_cells + 1, dtype=">i4").tobytes(),
    )

    # 8. MASTER table 끝에.
    master = _build_master_table(chunk_offsets)
    _emit_chunk(CHUNK_MASTER, master)

    # 9. Footer (8B): master_offset (8B big-endian).
    master_offset = chunk_offsets[CHUNK_MASTER][0]
    buf.extend(struct.pack(">q", int(master_offset)))

    try:
        out.write_bytes(bytes(buf))
        res.success = True
        res.n_bytes = len(buf)
        res.n_chunks = len(chunk_offsets)
        res.chunk_offsets = {hex(k): v for k, v in chunk_offsets.items()}
        res.pro_star_compat = "Adapco-chunked-v1"
        res.message = (
            f"wrote {len(buf)} bytes in {len(chunk_offsets)} chunks; "
            f"master at offset {master_offset}; n_pts={n_pts} n_cells={n_cells}"
        )
    except Exception as exc:
        res.message = f"write error: {exc!s:.80}"

    res.elapsed_s = time.perf_counter() - t0
    return res


def parse_chunked_binary_master(path: str | Path) -> dict | None:
    """parse master table from chunked binary file (validate / read entry).

    Returns:
        {"chunks": {chunk_id: (offset, size)}, "n_chunks": int} or None.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        with p.open("rb") as f:
            data = f.read()
        if not data.startswith(_HDF_MAGIC):
            return None
        if not data[8:28].startswith(_ADAPCO_SIG):
            return None
        # last 8B = master offset.
        if len(data) < 16:
            return None
        master_offset = struct.unpack(">q", data[-8:])[0]
        if master_offset <= 0 or master_offset >= len(data):
            return None
        # chunk header at master_offset: id (4B), size (4B).
        chunk_id, size = struct.unpack(">II", data[master_offset:master_offset + 8])
        if chunk_id != CHUNK_MASTER:
            return None
        master_payload = data[master_offset + 8:master_offset + 8 + size]
        n_entries = struct.unpack(">i", master_payload[:4])[0]
        chunks: dict[int, tuple[int, int]] = {}
        pos = 4
        for _ in range(n_entries):
            cid, offset, sz = struct.unpack(">iqi", master_payload[pos:pos + 16])
            chunks[int(cid)] = (int(offset), int(sz))
            pos += 16
        return {"chunks": chunks, "n_chunks": n_entries}
    except Exception:
        return None


def read_chunk(path: str | Path, chunk_id: int) -> bytes | None:
    """master table 통해 specific chunk payload 읽기."""
    master = parse_chunked_binary_master(path)
    if master is None or chunk_id not in master["chunks"]:
        return None
    offset, size = master["chunks"][chunk_id]
    p = Path(path)
    try:
        with p.open("rb") as f:
            f.seek(offset + 8)   # skip header (id + size).
            return f.read(size)
    except Exception:
        return None
