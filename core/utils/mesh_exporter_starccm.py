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

    if fmt != "txt":
        return StarCCMExportResult(
            success=False,
            fmt=fmt,
            message=f"unknown fmt={fmt} (지원: txt | binary)",
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
        fp.write(b"CCM ")  # magic
        fp.write(struct.pack("<I", 1))  # version
        fp.write(struct.pack("<I", len(points)))
        fp.write(struct.pack("<I", n_cells))
        fp.write(struct.pack("<I", len(faces)))
        fp.write(struct.pack("<H", len(boundary)))
        fp.write(b"\x00\x00")  # reserved
        # point block
        fp.write(points.astype(np.float64).tobytes())
        # face block (length + indices per face) — placeholder
        for face in faces:
            fp.write(struct.pack("<I", len(face)))
            fp.write(np.asarray(face, dtype=np.int32).tobytes())

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
            f"binary .ccm skeleton written ({output_path}). "
            f"NOTE: header speculative — Siemens 비공개 포맷. "
            f"StarCCM+ 으로 import 안 될 수 있음."
        ),
    )
