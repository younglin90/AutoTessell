"""C7 (1.1) — StarCCM+ .ccm partial writer skeleton.

Siemens StarCCM+ binary mesh format. 비공개이지만 OpenFOAM polyMesh 와
유사한 구조 (zone-based with face/owner/neighbor blocks).

현재 (skeleton, 2026-04): API + 텍스트 호환 .ccm.txt writer.
실제 binary writer 는 별도 카드 (포맷 reverse-engineering 필요):
    C7-1.2: ASCII .ccm.txt (사람이 읽을 수 있는 zone dump) — 본 카드
    C7-1.3: binary .ccm header + zone block (1-2개월)
    C7-1.4: full StarCCM+ load + simulation 검증 (1개월)

API:
    write_starccm(case_dir, polyMesh_path, fmt='txt'|'binary')
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class StarCCMExportResult:
    success: bool
    output_path: str = ""
    n_points: int = 0
    n_cells: int = 0
    n_faces: int = 0
    n_zones: int = 0
    fmt: str = ""
    elapsed: float = 0.0
    message: str = ""


def write_starccm(
    polyMesh_dir: Path | str,
    output_path: Path | str,
    *,
    fmt: str = "txt",
) -> StarCCMExportResult:
    """OpenFOAM polyMesh → StarCCM+ .ccm 변환 (skeleton).

    Args:
        polyMesh_dir: OpenFOAM polyMesh directory (points, faces, owner,
            neighbour, boundary).
        output_path: 출력 .ccm 파일 경로.
        fmt: 'txt' (ASCII zone dump, 본 카드) | 'binary' (별도 카드).

    Returns:
        StarCCMExportResult.
    """
    import time
    t0 = time.perf_counter()

    polyMesh_dir = Path(polyMesh_dir)
    output_path = Path(output_path)

    if fmt == "binary":
        # C7-1.3 — binary .ccm header 시도 (research-level skeleton).
        return _write_binary_ccm_skeleton(
            polyMesh_dir, output_path, t0,
        )

    if fmt == "ccmio":
        # F4 / beta2601 — Siemens CCMIO HDF5 reverse-engineered writer.
        try:
            from core.utils.ccmio_writer import write_ccmio
            r = write_ccmio(polyMesh_dir, output_path)
            return StarCCMExportResult(
                success=r.success,
                output_path=r.output_path,
                fmt="ccmio",
                n_points=r.n_vertices,
                n_cells=r.n_cells,
                n_faces=r.n_internal_faces + r.n_boundary_faces,
                n_zones=r.n_boundary_patches,
                elapsed=r.elapsed,
                message=r.message,
            )
        except Exception as exc:
            return StarCCMExportResult(
                success=False, fmt="ccmio",
                elapsed=time.perf_counter() - t0,
                message=f"ccmio writer error: {exc!s:.80}",
            )

    if fmt != "txt":
        return StarCCMExportResult(
            success=False,
            fmt=fmt,
            message=f"unknown fmt={fmt} (지원: txt | binary | ccmio)",
            elapsed=time.perf_counter() - t0,
        )

    # txt fmt — ASCII zone dump.
    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
    except ImportError:
        return StarCCMExportResult(
            success=False,
            fmt=fmt,
            message="poly_mesh_reader unavailable",
            elapsed=time.perf_counter() - t0,
        )

    try:
        pm = read_poly_mesh(polyMesh_dir)
        points = np.asarray(pm.get("points", []), dtype=np.float64)
        faces = list(pm.get("faces", []))
        owner = np.asarray(pm.get("owner", []), dtype=np.int64)
        neighbour = np.asarray(pm.get("neighbour", []), dtype=np.int64)
        boundary = list(pm.get("boundary", []))
    except Exception as exc:
        return StarCCMExportResult(
            success=False,
            fmt=fmt,
            message=f"polyMesh read 실패: {exc!s:.120}",
            elapsed=time.perf_counter() - t0,
        )

    n_cells = int(owner.max() + 1) if owner.size else 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("# StarCCM+ .ccm.txt skeleton (AutoTessell C7-1.2)\n")
        f.write("# Format: zone-based ASCII dump for inspection / parity check.\n")
        f.write(f"# n_points={len(points)} n_faces={len(faces)} n_cells={n_cells}\n")
        f.write(f"# n_zones={len(boundary)}\n\n")
        f.write("ZONE points\n")
        f.write(f"COUNT {len(points)}\n")
        for p in points:
            f.write(f"{p[0]:.10g} {p[1]:.10g} {p[2]:.10g}\n")
        f.write("\nZONE faces\n")
        f.write(f"COUNT {len(faces)}\n")
        for face in faces:
            f.write(f"{len(face)} " + " ".join(str(int(v)) for v in face) + "\n")
        f.write("\nZONE owner\n")
        f.write(f"COUNT {owner.size}\n")
        for o in owner.tolist():
            f.write(f"{int(o)}\n")
        f.write("\nZONE neighbour\n")
        f.write(f"COUNT {neighbour.size}\n")
        for n in neighbour.tolist():
            f.write(f"{int(n)}\n")
        f.write("\nZONE boundary\n")
        f.write(f"COUNT {len(boundary)}\n")
        for patch in boundary:
            name = str(patch.get("name", "patch"))
            ptype = str(patch.get("type", "patch"))
            start = int(patch.get("startFace", 0))
            nf = int(patch.get("nFaces", 0))
            f.write(f"{name} {ptype} startFace={start} nFaces={nf}\n")

    return StarCCMExportResult(
        success=True,
        output_path=str(output_path),
        n_points=len(points),
        n_cells=n_cells,
        n_faces=len(faces),
        n_zones=len(boundary),
        fmt=fmt,
        elapsed=time.perf_counter() - t0,
        message=f"wrote ASCII zone dump to {output_path}",
    )


def _write_binary_ccm_skeleton(
    polyMesh_dir: Path,
    output_path: Path,
    t0: float,
) -> "StarCCMExportResult":
    """C7-1.3 — binary .ccm header skeleton.

    StarCCM+ .ccm 포맷은 비공개. 알려진 일부 구조 (PROSTAR / pro-STAR 호환):
        - magic bytes (4): "CCM " (4 chars)
        - version (4 bytes uint32 little-endian)
        - n_points (4 bytes uint32)
        - n_cells (4 bytes uint32)
        - n_faces (4 bytes uint32)
        - n_zones (2 bytes uint16)
        - reserved (2 bytes)
        - point block: n_points × 3 × float64
        - face block: variable-length records per face
        - zone block: zone metadata + face-range mappings

    실제 binary writer 는 Siemens 비공개 포맷이라 reverse-engineering 필요.
    여기서는 magic header + size header 만 작성 (real .ccm 으로 인식 안 됨).
    """
    import struct
    import time
    try:
        from core.utils.poly_mesh_reader import read_poly_mesh
        pm = read_poly_mesh(polyMesh_dir)
        points = np.asarray(pm.get("points", []), dtype=np.float64)
        faces = list(pm.get("faces", []))
        owner = np.asarray(pm.get("owner", []), dtype=np.int64)
        neighbour = np.asarray(pm.get("neighbour", []), dtype=np.int64)
        boundary = list(pm.get("boundary", []))
    except Exception as exc:
        return StarCCMExportResult(
            success=False,
            output_path=str(output_path),
            fmt="binary",
            elapsed=time.perf_counter() - t0,
            message=f"binary skeleton: polyMesh read failed: {exc!s:.80}",
        )

    n_cells = int(owner.max() + 1) if owner.size else 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fp:
        # === C7-1.3 / beta2593 — full topology binary blocks ===
        # 헤더 (32 bytes 고정).
        fp.write(b"CCMV")  # magic (변경: "CCMV" — 우리 native variant 표시).
        fp.write(struct.pack("<I", 2))  # version 2 (beta2593 호환).
        fp.write(struct.pack("<I", len(points)))
        fp.write(struct.pack("<I", n_cells))
        fp.write(struct.pack("<I", len(faces)))
        fp.write(struct.pack("<I", int(neighbour.size)))     # internal face count.
        fp.write(struct.pack("<H", len(boundary)))
        fp.write(b"\x00" * 6)  # reserved padding to 32 bytes.

        # === BLOCK 1: POINTS ===
        # tag "PTS\0" + count + payload (n_points × 3 × float64 little-endian).
        fp.write(b"PTS\0")
        fp.write(struct.pack("<I", len(points)))
        fp.write(points.astype("<f8").tobytes(order="C"))

        # === BLOCK 2: FACES (var-length) ===
        # tag "FAC\0" + count + per-face: <uint32 nVerts> <int32 verts...>.
        fp.write(b"FAC\0")
        fp.write(struct.pack("<I", len(faces)))
        for face in faces:
            fp.write(struct.pack("<I", len(face)))
            fp.write(np.asarray(face, dtype="<i4").tobytes(order="C"))

        # === BLOCK 3: OWNER ===
        # tag "OWN\0" + count + int32 array.
        fp.write(b"OWN\0")
        fp.write(struct.pack("<I", int(owner.size)))
        fp.write(owner.astype("<i4").tobytes(order="C"))

        # === BLOCK 4: NEIGHBOUR ===
        # tag "NBR\0" + count + int32 array (only internal faces).
        fp.write(b"NBR\0")
        fp.write(struct.pack("<I", int(neighbour.size)))
        fp.write(neighbour.astype("<i4").tobytes(order="C"))

        # === BLOCK 5: ZONES (boundary patches) ===
        # tag "ZNE\0" + count + per-zone: <uint16 nameLen> <name bytes>
        # <uint32 startFace> <uint32 nFaces> <uint8 typeCode>.
        # typeCode: 0=patch, 1=wall, 2=symmetry, 3=empty.
        fp.write(b"ZNE\0")
        fp.write(struct.pack("<I", len(boundary)))
        for patch in boundary:
            name = str(patch.get("name", "patch")).encode("utf-8")[:255]
            start_face = int(patch.get("startFace", 0))
            n_face_p = int(patch.get("nFaces", 0))
            type_str = str(patch.get("type", "patch")).lower()
            type_map = {"patch": 0, "wall": 1, "symmetry": 2, "empty": 3, "symmetryplane": 2}
            type_code = type_map.get(type_str, 0)
            fp.write(struct.pack("<H", len(name)))
            fp.write(name)
            fp.write(struct.pack("<I", start_face))
            fp.write(struct.pack("<I", n_face_p))
            fp.write(struct.pack("<B", type_code))

        # === BLOCK 6: TRAILER ===
        # tag "END\0" + magic 0xCCAA5555 (sanity check).
        fp.write(b"END\0")
        fp.write(struct.pack("<I", 0xCCAA5555))

    return StarCCMExportResult(
        success=True,
        output_path=str(output_path),
        n_points=len(points),
        n_cells=n_cells,
        n_faces=len(faces),
        n_zones=len(boundary),
        fmt="binary",
        elapsed=time.perf_counter() - t0,
        message=(
            f"AutoTessell native binary .ccm v2 written ({output_path}). "
            f"6 블록 (PTS/FAC/OWN/NBR/ZNE/END). Siemens 공식 포맷 아님 — "
            f"내부 / 사용자 정의 reader 용. 공식 import 는 ASCII path 권장."
        ),
    )
