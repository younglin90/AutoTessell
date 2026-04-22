"""PLY reader — Stanford PLY, ASCII + binary little/big endian, 자체 구현.

포맷:
    ply
    format {ascii|binary_little_endian|binary_big_endian} 1.0
    comment ...
    element vertex <N>
    property <type> x
    property <type> y
    property <type> z
    [property <type> nx/ny/nz/red/green/blue/alpha/...]
    element face <M>
    property list <count_type> <index_type> vertex_indices
    end_header
    <data>

지원 범위:
    - vertex 의 x/y/z 만 사용, 나머지 property 는 offset 계산해 skip.
    - face 는 list property (vertex_indices) 만 지원. polygon (N>=3) → fan.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from core.analyzer.readers.core_mesh import CoreSurfaceMesh


# PLY type → (numpy dtype, size bytes, struct format char)
_TYPE_MAP: dict[str, tuple[str, int, str]] = {
    "char":    ("i1", 1, "b"),
    "uchar":   ("u1", 1, "B"),
    "int8":    ("i1", 1, "b"),
    "uint8":   ("u1", 1, "B"),
    "short":   ("i2", 2, "h"),
    "ushort":  ("u2", 2, "H"),
    "int16":   ("i2", 2, "h"),
    "uint16":  ("u2", 2, "H"),
    "int":     ("i4", 4, "i"),
    "uint":    ("u4", 4, "I"),
    "int32":   ("i4", 4, "i"),
    "uint32":  ("u4", 4, "I"),
    "float":   ("f4", 4, "f"),
    "float32": ("f4", 4, "f"),
    "double":  ("f8", 8, "d"),
    "float64": ("f8", 8, "d"),
}


def _parse_header(lines: list[str]) -> tuple[str, list[dict], list[dict], int]:
    """PLY header 파싱.

    Returns:
        (format, elements, _, header_byte_length)
        elements: [{"name": "vertex", "count": N, "props": [(name, type)]}, ...]
    """
    if lines[0].strip().lower() != "ply":
        raise ValueError("PLY magic 불일치 (첫 줄이 'ply' 여야 함)")
    fmt_line = lines[1].strip().split()
    if len(fmt_line) < 3 or fmt_line[0].lower() != "format":
        raise ValueError(f"PLY format 선언 없음: {lines[1]!r}")
    fmt = fmt_line[1].lower()

    elements: list[dict] = []
    current: dict | None = None
    idx = 2
    while idx < len(lines):
        s = lines[idx].strip()
        parts = s.split()
        if not parts:
            idx += 1
            continue
        head = parts[0].lower()
        if head == "comment":
            pass
        elif head == "element":
            if current:
                elements.append(current)
            current = {"name": parts[1], "count": int(parts[2]), "props": []}
        elif head == "property":
            assert current is not None, "element 없이 property"
            if parts[1].lower() == "list":
                # list count_type index_type name
                current["props"].append({
                    "kind": "list",
                    "count_type": parts[2],
                    "item_type": parts[3],
                    "name": parts[4],
                })
            else:
                current["props"].append({
                    "kind": "scalar",
                    "type": parts[1],
                    "name": parts[2],
                })
        elif head == "end_header":
            if current:
                elements.append(current)
            idx += 1
            break
        idx += 1

    return fmt, elements, [], idx


def _read_ascii_body(
    f,
    elements: list[dict],
) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[tuple[float, ...]] = []
    faces: list[list[int]] = []
    # tokenize rest of file (spaces + newlines) — ascii body 는 element 별 count 만큼 line.
    for elem in elements:
        name = elem["name"]
        count = elem["count"]
        props = elem["props"]
        if name == "vertex":
            # 각 라인: property 순서대로 값 나열.
            # x,y,z 인덱스 찾기
            prop_names = [p["name"] for p in props]
            try:
                ix, iy, iz = (
                    prop_names.index("x"), prop_names.index("y"), prop_names.index("z"),
                )
            except ValueError as exc:
                raise ValueError(f"vertex element 에 x/y/z 누락: {prop_names}") from exc
            for _ in range(count):
                toks = f.readline().split()
                vertices.append((float(toks[ix]), float(toks[iy]), float(toks[iz])))
        elif name == "face":
            # face 에 list property (vertex_indices) + 뒤에 추가 scalar properties
            # (예: ushort stl) 가 있을 수 있음. 모두 토큰 기준 라인 단위로 파싱.
            for _ in range(count):
                toks = f.readline().split()
                n = int(toks[0])
                idx_list = [int(toks[1 + k]) for k in range(n)]
                # fan triangulation
                for k in range(1, n - 1):
                    faces.append([idx_list[0], idx_list[k], idx_list[k + 1]])
        else:
            # 기타 element (edge 등) skip — count 만큼 line 폐기
            for _ in range(count):
                f.readline()

    V = np.array(vertices, dtype=np.float64) if vertices else np.zeros((0, 3))
    F = np.array(faces, dtype=np.int64) if faces else np.zeros((0, 3), dtype=np.int64)
    return V, F


def _read_binary_body(
    f,
    elements: list[dict],
    endian: str,
) -> tuple[np.ndarray, np.ndarray]:
    prefix = "<" if endian == "binary_little_endian" else ">"
    vertices_acc: list[list[float]] = []
    faces_acc: list[list[int]] = []

    for elem in elements:
        name = elem["name"]
        count = elem["count"]
        props = elem["props"]

        if name == "vertex":
            # 모두 scalar 이어야 함 (list vertex 는 비표준).
            fmt_chars: list[str] = []
            sizes: list[int] = []
            prop_names: list[str] = []
            for p in props:
                if p["kind"] != "scalar":
                    raise ValueError("vertex 에 list property 미지원")
                t = _TYPE_MAP[p["type"]]
                fmt_chars.append(t[2])
                sizes.append(t[1])
                prop_names.append(p["name"])
            row_fmt = prefix + "".join(fmt_chars)
            row_size = sum(sizes)
            try:
                ix, iy, iz = (
                    prop_names.index("x"), prop_names.index("y"), prop_names.index("z"),
                )
            except ValueError as exc:
                raise ValueError("vertex 에 x/y/z 없음") from exc
            data = f.read(row_size * count)
            for r in range(count):
                unpacked = struct.unpack_from(row_fmt, data, r * row_size)
                vertices_acc.append(
                    [float(unpacked[ix]), float(unpacked[iy]), float(unpacked[iz])]
                )
        elif name == "face":
            # 여러 property 가 있을 수 있음. 각 face 에 대해 모든 property 를 순서대로
            # 파싱하되, vertex_indices 이름의 list property 만 index 수집에 사용.
            # 나머지 scalar / list property 는 offset 소비용으로 읽고 버림.
            for _ in range(count):
                vertex_idx: list[int] | None = None
                for pp in props:
                    if pp["kind"] == "list":
                        ct = _TYPE_MAP[pp["count_type"]]
                        it = _TYPE_MAP[pp["item_type"]]
                        n = struct.unpack(
                            prefix + ct[2], f.read(ct[1]),
                        )[0]
                        raw = f.read(it[1] * n)
                        idx_list = list(
                            struct.unpack(prefix + it[2] * n, raw),
                        )
                        if pp["name"] in (
                            "vertex_indices", "vertex_index", "indices",
                        ):
                            vertex_idx = idx_list
                    else:
                        t = _TYPE_MAP[pp["type"]]
                        f.read(t[1])
                if vertex_idx is None:
                    raise ValueError("face element 에 vertex_indices 없음")
                n = len(vertex_idx)
                for k in range(1, n - 1):
                    faces_acc.append(
                        [vertex_idx[0], vertex_idx[k], vertex_idx[k + 1]],
                    )
        else:
            # 기타 element — byte 단위로 skip
            row_size = 0
            is_list = False
            for p in props:
                if p["kind"] == "list":
                    is_list = True
                    break
                row_size += _TYPE_MAP[p["type"]][1]
            if not is_list:
                f.read(row_size * count)
            else:
                # list element 는 row 별로 길이 다르므로 한 개씩 파싱
                for _ in range(count):
                    for p in props:
                        if p["kind"] == "scalar":
                            f.read(_TYPE_MAP[p["type"]][1])
                        else:
                            ct = _TYPE_MAP[p["count_type"]]
                            n = struct.unpack(prefix + ct[2], f.read(ct[1]))[0]
                            f.read(_TYPE_MAP[p["item_type"]][1] * n)

    V = np.array(vertices_acc, dtype=np.float64) if vertices_acc else np.zeros((0, 3))
    F = np.array(faces_acc, dtype=np.int64) if faces_acc else np.zeros((0, 3), dtype=np.int64)
    return V, F


def read_ply(path: str | Path) -> CoreSurfaceMesh:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"PLY 파일 없음: {p}")

    # 1) header 를 텍스트로 파싱 (줄 단위)
    with p.open("rb") as fb:
        header_lines: list[str] = []
        header_bytes = bytearray()
        while True:
            line_b = fb.readline()
            if not line_b:
                raise ValueError("PLY header 끝나기 전에 EOF")
            header_bytes.extend(line_b)
            try:
                line = line_b.decode("ascii", errors="replace").rstrip("\r\n")
            except Exception:
                line = line_b.decode("utf-8", errors="replace").rstrip("\r\n")
            header_lines.append(line)
            if line.strip().lower() == "end_header":
                break
        body_start = fb.tell()

    fmt, elements, _, _ = _parse_header(header_lines)

    if fmt == "ascii":
        with p.open("r", encoding="utf-8", errors="replace") as f:
            # skip header
            while True:
                line = f.readline()
                if line.strip().lower() == "end_header":
                    break
            V, F = _read_ascii_body(f, elements)
    elif fmt in ("binary_little_endian", "binary_big_endian"):
        with p.open("rb") as f:
            f.seek(body_start)
            V, F = _read_binary_body(f, elements, endian=fmt)
    else:
        raise ValueError(f"unknown PLY format: {fmt}")

    return CoreSurfaceMesh(
        vertices=V, faces=F,
        metadata={"format": f"ply_{fmt}", "path": str(p)},
    )
