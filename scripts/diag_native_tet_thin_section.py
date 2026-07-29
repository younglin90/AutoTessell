"""Report-only TET-THIN-SECTION-1 calibration census.

This intentionally uses a Delaunay calibration primal built from each input STL's
surface vertices. It is not the production native-tet result and cannot justify
a generation change; it only validates the thickness measurement and its cost.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.analyzer.file_reader import load_mesh  # noqa: E402
from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402
from core.generator.native_tet.thin_section import estimate_boundary_thickness  # noqa: E402
from core.generator.native_tet.writer_topology import audit_written_polymesh  # noqa: E402
from core.utils.polymesh_reader import parse_foam_points_array  # noqa: E402


def _native_tet_primal(path: Path, target_cells: int) -> tuple[np.ndarray, np.ndarray]:
    """Generate one native-tet case and reconstruct its all-tet primal.

    This is an offline diagnostic route.  It fails closed if the written mesh
    is not exclusively tetrahedral rather than silently measuring a subset.
    """
    mesh = load_mesh(path)
    with tempfile.TemporaryDirectory(prefix="native_tet_thin_section_") as temp_dir:
        case_dir = Path(temp_dir) / "case"
        result = generate_native_tet(
            np.asarray(mesh.vertices, dtype=np.float64),
            np.asarray(mesh.faces, dtype=np.int64),
            case_dir,
            target_cells=int(target_cells),
        )
        if not result.success:
            raise RuntimeError(f"native_tet failed: {result.message}")
        poly = case_dir / "constant" / "polyMesh"
        points = parse_foam_points_array(poly / "points")
        audit = audit_written_polymesh(poly)
        non_tets = audit.non_tetrahedron_vertex_incidence_cells
        if non_tets:
            details = json.dumps([cell.as_dict() for cell in non_tets], sort_keys=True)
            raise RuntimeError(
                "native_tet output contains "
                f"{len(non_tets)} cells without tetrahedron vertex incidence: {details}; "
                "written face-incidence audit: "
                f"{audit.as_dict()['n_incomplete_tetrahedron_face_encodings']} "
                "four-vertex cells lack a complete tetrahedron face encoding"
            )
        tets = np.asarray([cell.unique_vertex_ids for cell in audit.cells], dtype=np.int64)
    return np.asarray(points, dtype=np.float64), tets


def _summarize(
    path: Path,
    points: np.ndarray,
    tets: np.ndarray,
    *,
    calibration_only: bool,
    started: float,
) -> dict[str, object]:
    mesh = load_mesh(path)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    report = estimate_boundary_thickness(points, tets, candidate_faces=64)
    result = report.as_dict()
    result.pop("thickness_values", None)
    result.pop("through_thickness_cell_counts", None)
    result["n_thickness_values"] = int(report.n_ray_hits)
    result["n_through_thickness_counts"] = int(report.n_ray_hits)
    result.update(
        {
            "shape": path.name,
            "input_faces": int(faces.shape[0]),
            "primal_tets": int(tets.shape[0]),
            "elapsed_seconds": float(time.perf_counter() - started),
            "calibration_only": calibration_only,
        }
    )
    return result


def measure(
    path: Path, *, native_primal: bool = False, target_cells: int = 2000
) -> dict[str, object]:
    mesh = load_mesh(path)
    points = np.asarray(mesh.vertices, dtype=np.float64)
    started = time.perf_counter()
    if native_primal:
        points, tets = _native_tet_primal(path, target_cells)
    else:
        tets = np.asarray(Delaunay(points).simplices, dtype=np.int64)
    return _summarize(
        path,
        points,
        tets,
        calibration_only=not native_primal,
        started=started,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--native-primal", action="store_true")
    parser.add_argument("--target-cells", type=int, default=2000)
    args = parser.parse_args()
    for path in args.paths:
        print(
            json.dumps(
                measure(
                    path,
                    native_primal=args.native_primal,
                    target_cells=args.target_cells,
                ),
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
