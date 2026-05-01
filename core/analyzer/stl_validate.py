"""BB5 / beta2755 — STL file pre-flight validator.

STL 파일 읽기 전 빠른 체크: ASCII vs binary, 추정 face count, file size.
malformed STL 조기 거부 + Strategist 입력.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class STLValidateResult:
    path: str = ""
    exists: bool = False
    file_size: int = 0
    is_ascii: bool = False
    is_binary: bool = False
    estimated_n_faces: int = 0
    issues: list[str] | None = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = []


def validate_stl(path: str | Path) -> STLValidateResult:
    """STL 파일 빠른 검증.

    Args:
        path: STL 파일 경로.

    Returns:
        STLValidateResult.
    """
    p = Path(path)
    res = STLValidateResult(path=str(p))

    if not p.exists():
        res.issues.append("file not found")
        return res
    res.exists = True
    res.file_size = int(p.stat().st_size)

    if res.file_size < 84:
        res.issues.append(f"file too small ({res.file_size} bytes)")
        return res

    # detect ASCII vs binary.
    with p.open("rb") as f:
        head = f.read(80)
    if head.lstrip().lower().startswith(b"solid"):
        # likely ASCII, but binary STL can also start with "solid" — verify by face count.
        with p.open("rb") as f:
            f.seek(80)
            try:
                n_faces_b = struct.unpack("<I", f.read(4))[0]
            except struct.error:
                n_faces_b = 0
        # binary STL: 80 + 4 + n*50 = file_size.
        expected_binary_size = 84 + n_faces_b * 50
        if expected_binary_size == res.file_size and 0 < n_faces_b < 10**9:
            res.is_binary = True
            res.estimated_n_faces = n_faces_b
        else:
            # ASCII: count "facet" occurrences (rough, for first 1MB).
            with p.open("rb") as f:
                chunk = f.read(min(1_000_000, res.file_size))
            n_face_ascii = chunk.count(b"facet normal")
            res.is_ascii = True
            # extrapolate to full file if truncated.
            if res.file_size > 1_000_000:
                n_face_ascii = int(n_face_ascii * res.file_size / 1_000_000)
            res.estimated_n_faces = n_face_ascii
    else:
        # binary STL.
        with p.open("rb") as f:
            f.seek(80)
            try:
                n_faces_b = struct.unpack("<I", f.read(4))[0]
            except struct.error:
                n_faces_b = 0
        if n_faces_b > 0 and (84 + n_faces_b * 50) == res.file_size:
            res.is_binary = True
            res.estimated_n_faces = n_faces_b
        else:
            res.issues.append(
                f"binary STL face count mismatch (got {n_faces_b}, "
                f"expected size {84 + n_faces_b * 50}, actual {res.file_size})"
            )

    if res.estimated_n_faces == 0:
        res.issues.append("no faces detected")

    return res
