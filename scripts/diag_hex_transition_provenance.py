"""HEX-TRANS-2 — transition adjacency / feature provenance census.

This is report-only.  It does not modify a mesh or enable any repair lane.
The written generic cell-face output does not retain the octree level and patch
provenance tables, so this diagnostic reconstructs only defensible proxies:

* an internal face is a transition face when the two owner-cell volumes differ
  by at least the 2:1 refinement signature (ratio >= 1.5);
* a boundary face's transition distance is the shortest cell-adjacency distance
  to a cell incident to such a face;
* sharp-feature provenance is a geometry-only class inferred from proximity to
  STL feature vertices.  Patch provenance is explicitly reported as
  ``defaultWall/unknown`` because it is not serialized by the current path.

The census cross-tabulates all boundary faces and OpenFOAM-skew flagged faces.
It is intentionally a diagnostic proxy, not an all-hex or provenance proof.

Usage:
    python scripts/diag_hex_transition_provenance.py [max_cells]
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
import sys
import tempfile

import numpy as np

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

from core.generator.native_hex.match_diagnostic import (  # noqa: E402
    compute_boundary_face_skew,
)
from core.generator.native_hex.metrics import (  # noqa: E402
    _cell_volume,
    _face_key,
    _face_owners,
    read_written_polymesh_cells,
)
from core.generator.native_hex.snap import _detect_surface_feature_vertices  # noqa: E402
from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402


_SHAPES = {
    "cylinder": Path(REPO) / "tests" / "benchmarks" / "cylinder.stl",
    "sphere": Path(REPO) / "tests" / "benchmarks" / "sphere.stl",
    "gear": Path(REPO) / "tests" / "stl" / "04_extreme_gear.stl",
}
_SKEW_THRESHOLD = 2.0
_TRANSITION_VOLUME_RATIO = 1.5


def _cell_centroid(points: np.ndarray, cell: list[list[int]]) -> np.ndarray:
    ids = sorted({int(v) for face in cell for v in face})
    return points[np.asarray(ids, dtype=np.int64)].mean(axis=0)


def _cell_adjacency(
    cells: list[list[list[int]]], owners: dict[tuple[int, ...], list[int]]
) -> list[set[int]]:
    adjacency = [set() for _ in cells]
    for face_owners in owners.values():
        unique = sorted(set(int(v) for v in face_owners))
        if len(unique) != 2:
            continue
        left, right = unique
        adjacency[left].add(right)
        adjacency[right].add(left)
    return adjacency


def _transition_cells(
    points: np.ndarray,
    cells: list[list[list[int]]],
    owners: dict[tuple[int, ...], list[int]],
) -> tuple[set[int], set[tuple[int, ...]], np.ndarray]:
    volumes = np.asarray([_cell_volume(points, cell) for cell in cells], dtype=np.float64)
    transition_faces: set[tuple[int, ...]] = set()
    transition_cells: set[int] = set()
    for key, face_owners in owners.items():
        unique = sorted(set(int(v) for v in face_owners))
        if len(unique) != 2:
            continue
        left, right = unique
        small = min(volumes[left], volumes[right])
        large = max(volumes[left], volumes[right])
        ratio = large / max(small, 1e-30)
        if ratio >= _TRANSITION_VOLUME_RATIO:
            transition_faces.add(key)
            transition_cells.update((left, right))
    return transition_cells, transition_faces, volumes


def _transition_distances(
    adjacency: list[set[int]], transition_cells: set[int]
) -> dict[int, int]:
    distances: dict[int, int] = {}
    queue: deque[int] = deque()
    for cell in sorted(transition_cells):
        distances[cell] = 0
        queue.append(cell)
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacency[current]):
            if neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances


def _provenance_class(
    points: np.ndarray,
    face: tuple[int, ...],
    surface_vertices: np.ndarray,
    feature_ids: np.ndarray,
    local_scale: float,
) -> str:
    if feature_ids.size == 0:
        return "smooth/defaultWall"
    feature_points = surface_vertices[feature_ids]
    face_points = points[np.asarray(face, dtype=np.int64)]
    distance = np.linalg.norm(face_points[:, None, :] - feature_points[None, :, :], axis=2)
    near = np.min(distance, axis=1) <= max(1e-12, 0.35 * local_scale)
    n_near = int(np.count_nonzero(near))
    if n_near >= 3:
        return "corner/defaultWall"
    if n_near > 0:
        return "curve_or_feature/defaultWall"
    return "smooth/defaultWall"


def analyze(
    points: np.ndarray,
    cells: list[list[list[int]]],
    surface_vertices: np.ndarray,
    surface_faces: np.ndarray,
) -> dict[str, object]:
    owners = _face_owners(cells)
    adjacency = _cell_adjacency(cells, owners)
    transition_cells, transition_faces, volumes = _transition_cells(points, cells, owners)
    distances = _transition_distances(adjacency, transition_cells)
    feature_ids = _detect_surface_feature_vertices(surface_vertices, surface_faces, 30.0)

    boundary = compute_boundary_face_skew(points, cells)
    rows: list[dict[str, object]] = []
    for item in boundary:
        owner = int(item.owner_cell)
        scale = float(max(volumes[owner], 1e-30) ** (1.0 / 3.0))
        prov = _provenance_class(
            points, item.face_key, surface_vertices, feature_ids, scale
        )
        rows.append(
            {
                "face": item.face_key,
                "owner": owner,
                "skew": float(item.skewness),
                "bad": bool(item.skewness >= _SKEW_THRESHOLD),
                "transition_distance": distances.get(owner, None),
                "direct_transition": owner in transition_cells,
                "provenance": prov,
            }
        )
    return {
        "n_cells": len(cells),
        "n_boundary": len(rows),
        "n_transition_faces": len(transition_faces),
        "n_transition_cells": len(transition_cells),
        "n_feature_vertices": int(feature_ids.size),
        "rows": rows,
    }


def _bucket(row: dict[str, object]) -> str:
    distance = row["transition_distance"]
    if distance is None:
        return "unconnected"
    if int(distance) == 0:
        return "direct"
    if int(distance) == 1:
        return "one-ring"
    if int(distance) == 2:
        return "two-ring"
    return "farther"


def _print_report(name: str, report: dict[str, object]) -> None:
    rows = report["rows"]
    all_rows = list(rows)  # type: ignore[arg-type]
    bad_rows = [row for row in all_rows if bool(row["bad"])]
    all_buckets = Counter(_bucket(row) for row in all_rows)
    bad_buckets = Counter(_bucket(row) for row in bad_rows)
    all_prov = Counter(str(row["provenance"]) for row in all_rows)
    bad_prov = Counter(str(row["provenance"]) for row in bad_rows)

    def frac(count: int, total: int) -> str:
        return f"{100.0 * count / total:.1f}%" if total else "0.0%"

    print(
        f"{name}: cells={report['n_cells']} boundary={report['n_boundary']} "
        f"bad={len(bad_rows)} transition_faces={report['n_transition_faces']} "
        f"transition_cells={report['n_transition_cells']} "
        f"feature_vertices={report['n_feature_vertices']}"
    )
    print(f"  transition distance all={dict(sorted(all_buckets.items()))}")
    print(f"  transition distance bad={dict(sorted(bad_buckets.items()))}")
    print(f"  provenance all={dict(sorted(all_prov.items()))}")
    print(f"  provenance bad={dict(sorted(bad_prov.items()))}")
    direct_all = all_buckets["direct"]
    direct_bad = bad_buckets["direct"]
    print(
        f"  direct-transition enrichment: all={frac(direct_all, len(all_rows))} "
        f"bad={frac(direct_bad, len(bad_rows))} "
        f"ratio={(direct_bad / max(len(bad_rows), 1)) / max(direct_all / max(len(all_rows), 1), 1e-30):.3f}"
    )
    for row in bad_rows[:3]:
        print(
            f"  bad-example face={row['face']} owner={row['owner']} "
            f"skew={float(row['skew']):.4f} distance={row['transition_distance']} "
            f"provenance={row['provenance']}"
        )


def _run_one(name: str, stl_path: Path, max_cells: int) -> None:
    if not stl_path.exists():
        print(f"{name}: SKIP (fixture not found: {stl_path})")
        return
    from core.analyzer.readers.stl import read_stl  # noqa: PLC0415

    surface_mesh = read_stl(str(stl_path))
    surface_vertices = np.asarray(surface_mesh.vertices, dtype=np.float64)
    surface_faces = np.asarray(surface_mesh.faces, dtype=np.int64)
    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp) / "case"
        result = PipelineOrchestrator().run(
            stl_path,
            case,
            quality_level="fine",
            mesh_type="hex_dominant",
            tier_hint="native_hex",
            max_iterations=1,
            auto_retry="off",
            strict_tier=True,
            write_of_case=True,
            max_cells=max_cells,
            tier_specific_params={
                "max_cells": max_cells,
                "target_cells": max_cells,
                "bl_layers": 0,
            },
        )
        loaded = read_written_polymesh_cells(case)
        if loaded is None:
            print(f"{name}: NO POLYMESH error={result.error}")
            return
        points, cells = loaded
        _print_report(name, analyze(points, cells, surface_vertices, surface_faces))


def main() -> int:
    max_cells = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    for name, path in _SHAPES.items():
        _run_one(name, path, max_cells)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
