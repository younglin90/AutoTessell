"""Shared OpenFOAM polyMesh file parsers.

These parsers are used by both the geometry fidelity checker and the native
mesh quality checker so that the parsing logic lives in one place.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Low-level token helpers
# ---------------------------------------------------------------------------


def _strip_foam_comments(text: str) -> str:
    """Remove /* ... */ block comments and // line comments."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _read_foam_list(text: str) -> list[str]:
    """Extract tokens inside the outermost ( ... ) block."""
    text = _strip_foam_comments(text)
    start = text.find("(")
    end = text.rfind(")")
    if start == -1 or end == -1:
        return []
    return text[start + 1 : end].split()


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------


def parse_foam_points(points_file: Path) -> list[list[float]]:
    """Parse polyMesh/points and return a list of [x, y, z] coordinates."""
    text = points_file.read_text()
    tokens = _read_foam_list(text)
    coords: list[list[float]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("("):
            x = float(tok.lstrip("(").rstrip(")"))
            y = float(tokens[i + 1].rstrip(")"))
            z = float(tokens[i + 2].rstrip(")"))
            coords.append([x, y, z])
            i += 3
        else:
            i += 1
    return coords


def parse_foam_faces(faces_file: Path) -> list[list[int]]:
    """Parse polyMesh/faces and return a list of vertex-index lists."""
    text = faces_file.read_text()
    tokens = _read_foam_list(text)
    faces: list[list[int]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        try:
            if "(" in tok:
                n_str, rest = tok.split("(", 1)
                n = int(n_str)
                verts: list[int] = []
                if rest.rstrip(")"):
                    verts.append(int(rest.strip("()")))
                i += 1
                while len(verts) < n:
                    t = tokens[i].strip("()")
                    if t:
                        verts.append(int(t))
                    i += 1
                faces.append(verts)
            else:
                n = int(tok)
                i += 1
                verts = []
                opening = tokens[i]
                if opening == "(":
                    i += 1
                else:
                    v = opening.lstrip("(").rstrip(")")
                    if v:
                        verts.append(int(v))
                    i += 1
                while len(verts) < n:
                    t = tokens[i].strip("()")
                    if t:
                        verts.append(int(t))
                    i += 1
                faces.append(verts)
        except (ValueError, IndexError):
            i += 1
    return faces


def parse_foam_labels(label_file: Path) -> list[int]:
    """Parse a polyMesh label list file (owner or neighbour)."""
    text = label_file.read_text()
    tokens = _read_foam_list(text)
    labels: list[int] = []
    for tok in tokens:
        try:
            labels.append(int(tok))
        except ValueError:
            pass
    return labels


def parse_foam_boundary(boundary_file: Path) -> list[dict[str, Any]]:
    """Parse polyMesh/boundary and return patch info dicts.

    Each dict has keys: ``name``, ``nFaces``, ``startFace``.
    """
    text = boundary_file.read_text()
    text = _strip_foam_comments(text)

    patches: list[dict[str, Any]] = []
    # Match named patch blocks: name { ... nFaces N; startFace M; ... }
    # We also want to capture the patch name
    patch_blocks = re.findall(
        r"(\w[\w\s]*?)\s*\{([^}]+)\}",
        text,
        re.DOTALL,
    )
    for name_raw, block in patch_blocks:
        nfaces_m = re.search(r"nFaces\s+(\d+)", block)
        startface_m = re.search(r"startFace\s+(\d+)", block)
        if nfaces_m and startface_m:
            patches.append(
                {
                    "name": name_raw.strip(),
                    "nFaces": int(nfaces_m.group(1)),
                    "startFace": int(startface_m.group(1)),
                }
            )
    return patches
