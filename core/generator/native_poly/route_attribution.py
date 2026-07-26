"""POLY-ROUTE-ATTRIB1 -- fixed-primal route attribution diagnostic.

This module is deliberately report-only.  It does not participate in the
native_poly production path and does not change writer, drop, or quality
defaults.  A fixture is converted once into a deterministic star-shaped tet
primal.  That exact ``(V, T)`` pair is then used by both:

* direct ``tet_to_poly_dual``; and
* ``tier_native_poly`` with the tier's imported native-tet generator replaced
  by a fixed-primal provider.

The diagnostic records route selection, disk mesh identity, topology census,
surface-area deviation, volume, checker negative-volume count, quality
metrics, and whether the legacy cell-drop helper was invoked.  Per-fixture
subprocess execution is available so a slow sphere cannot consume an
unbounded benchmark run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import queue as queue_module
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast
from unittest import mock

import numpy as np

from core.analyzer.readers.stl import read_stl
from core.evaluator.native_checker import NativeMeshChecker
from core.generator import tier_native_poly
from core.generator.native_poly import harness as native_poly_harness
from core.generator.native_poly.dual import tet_to_poly_dual
from core.generator.native_tet.mesher import NativeTetResult
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)


@dataclass(frozen=True)
class FixedPrimalFixture:
    """A surface fixture and its deterministic, fixed tet primal."""

    name: str
    source_path: str
    surface_vertices: np.ndarray
    surface_faces: np.ndarray
    primal_vertices: np.ndarray
    primal_tets: np.ndarray
    surface_area: float
    volume: float


@dataclass
class DropInvocation:
    """Observed calls to the legacy cell-drop helper."""

    invoked: bool = False
    calls: int = 0
    dropped_cells: int = 0


@dataclass
class RouteMeshReport:
    """One route/repeat's result, including its on-disk identity."""

    fixture: str
    route_requested: str
    route_selected: str
    repeat: int
    auto_escalate: bool
    fixed_primal_injected: bool
    primal_identity: str
    result_success: bool
    result_message: str
    result_type: str
    selected_mesh_identity: str = ""
    disk_mesh_identity: str = ""
    disk_identity_matches_selected: bool = False
    n_cells: int = 0
    n_faces: int = 0
    n_points: int = 0
    n_internal_faces: int = 0
    n_boundary_faces: int = 0
    n_patches: int = 0
    boundary_area: float = 0.0
    surface_area_deviation_pct: float = 0.0
    volume: float = 0.0
    volume_relative_error_pct: float = 0.0
    negative_volumes: int = 0
    quality: dict[str, float | int | bool | None] = field(default_factory=dict)
    drop: DropInvocation = field(default_factory=DropInvocation)
    error: str = ""


@dataclass
class FixtureComparison:
    """Comparison of direct and tier routes on one fixed primal."""

    fixture: str
    primal_identity: str
    primal_points: int
    primal_tets: int
    timeout: bool = False
    timeout_seconds: float = 0.0
    routes: list[RouteMeshReport] = field(default_factory=list)
    deterministic_repeat_identity: dict[str, bool] = field(default_factory=dict)
    direct_tier_identity_equal: bool = False
    conclusion: str = ""
    error: str = ""


def _array_digest(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode("ascii"))
        digest.update(np.asarray(contiguous.shape, dtype=np.int64).tobytes())
        digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _mesh_digest(poly_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in poly_dir.iterdir() if item.is_file()):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _triangle_area(vertices: np.ndarray, faces: np.ndarray) -> float:
    triangles = np.asarray(vertices, dtype=np.float64)[np.asarray(faces, dtype=np.int64)]
    return float(
        0.5
        * np.linalg.norm(
            np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
            axis=1,
        ).sum()
    )


def _surface_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    triangles = np.asarray(vertices, dtype=np.float64)[np.asarray(faces, dtype=np.int64)]
    signed = np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2]))
    return abs(float(signed.sum()) / 6.0)


def _make_star_primal(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Make a deterministic tet fan without invoking any tet generator."""
    surface_vertices = np.asarray(vertices, dtype=np.float64)
    surface_faces = np.asarray(faces, dtype=np.int64)
    centre = surface_vertices.mean(axis=0)
    primal_vertices = np.vstack([surface_vertices, centre])
    centre_id = int(surface_vertices.shape[0])
    primal_tets = np.empty((surface_faces.shape[0], 4), dtype=np.int64)
    primal_tets[:, 0] = centre_id
    primal_tets[:, 1:] = surface_faces

    a = primal_vertices[primal_tets[:, 1]] - primal_vertices[primal_tets[:, 0]]
    b = primal_vertices[primal_tets[:, 2]] - primal_vertices[primal_tets[:, 0]]
    c = primal_vertices[primal_tets[:, 3]] - primal_vertices[primal_tets[:, 0]]
    signed6 = np.einsum("ij,ij->i", a, np.cross(b, c))
    reverse = signed6 < 0.0
    if np.any(reverse):
        primal_tets[reverse, 2], primal_tets[reverse, 3] = (
            primal_tets[reverse, 3].copy(),
            primal_tets[reverse, 2].copy(),
        )
    if np.any(np.abs(signed6) <= 1.0e-15):
        raise ValueError("surface fixture contains a triangle coplanar with its centroid")
    return primal_vertices, primal_tets


def load_fixed_fixture(source_path: Path) -> FixedPrimalFixture:
    """Load a tracked STL and construct its fixed diagnostic primal once."""
    mesh = read_stl(source_path)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    primal_vertices, primal_tets = _make_star_primal(vertices, faces)
    return FixedPrimalFixture(
        name=source_path.stem,
        source_path=str(source_path),
        surface_vertices=vertices,
        surface_faces=faces,
        primal_vertices=primal_vertices,
        primal_tets=primal_tets,
        surface_area=_triangle_area(vertices, faces),
        volume=_surface_volume(vertices, faces),
    )


def _cell_volumes(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
) -> np.ndarray:
    n_cells = int(max(owner.max(), neighbour.max() if neighbour.size else 0)) + 1
    cell_faces: list[list[list[int]]] = [[] for _ in range(n_cells)]
    for face_id, face in enumerate(faces):
        owner_id = int(owner[face_id])
        if 0 <= owner_id < n_cells:
            cell_faces[owner_id].append(face)
        if face_id < len(neighbour):
            neighbour_id = int(neighbour[face_id])
            if 0 <= neighbour_id < n_cells:
                cell_faces[neighbour_id].append(face)

    volumes: np.ndarray = np.zeros(n_cells, dtype=np.float64)
    for cell_id, incident_faces in enumerate(cell_faces):
        vertex_ids = sorted({int(vertex) for face in incident_faces for vertex in face})
        if len(vertex_ids) < 4:
            continue
        centroid = points[np.asarray(vertex_ids, dtype=np.int64)].mean(axis=0)
        total = 0.0
        for face in incident_faces:
            face_points = points[np.asarray(face, dtype=np.int64)]
            for index in range(1, len(face) - 1):
                total += (
                    abs(
                        float(
                            np.dot(
                                face_points[0] - centroid,
                                np.cross(
                                    face_points[index] - centroid,
                                    face_points[index + 1] - centroid,
                                ),
                            )
                        )
                    )
                    / 6.0
                )
        volumes[cell_id] = total
    return volumes


def _boundary_area(points: np.ndarray, faces: list[list[int]], n_internal: int) -> float:
    area = 0.0
    for face in faces[n_internal:]:
        face_points = points[np.asarray(face, dtype=np.int64)]
        vector_area = np.cross(
            face_points[1:-1] - face_points[0],
            face_points[2:] - face_points[0],
        ).sum(axis=0)
        area += 0.5 * float(np.linalg.norm(vector_area))
    return area


def _census(
    fixture: FixedPrimalFixture,
    case_dir: Path,
    route: str,
    selected_route: str,
    repeat: int,
    result: object,
    drop: DropInvocation,
    fixed_primal_injected: bool,
) -> RouteMeshReport:
    poly_dir = case_dir / "constant" / "polyMesh"
    result_success = bool(getattr(result, "success", False))
    result_message = str(getattr(result, "message", ""))
    report = RouteMeshReport(
        fixture=fixture.name,
        route_requested=route,
        route_selected=selected_route,
        repeat=repeat,
        auto_escalate=False,
        fixed_primal_injected=fixed_primal_injected,
        primal_identity=_array_digest(fixture.primal_vertices, fixture.primal_tets),
        result_success=result_success,
        result_message=result_message,
        result_type=type(result).__name__,
        selected_mesh_identity=_mesh_digest(poly_dir) if poly_dir.is_dir() else "",
        drop=drop,
    )
    report.disk_mesh_identity = report.selected_mesh_identity
    report.disk_identity_matches_selected = bool(report.selected_mesh_identity)
    try:
        points = np.asarray(parse_foam_points(poly_dir / "points"), dtype=np.float64)
        faces = [list(face) for face in parse_foam_faces(poly_dir / "faces")]
        owner = np.asarray(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
        neighbour = np.asarray(parse_foam_labels(poly_dir / "neighbour"), dtype=np.int64)
        boundaries = parse_foam_boundary(poly_dir / "boundary")
        n_internal = int(len(neighbour))
        volumes = _cell_volumes(points, faces, owner, neighbour)
        check = NativeMeshChecker().run(case_dir)
        report.n_cells = int(check.cells)
        report.n_faces = int(check.faces)
        report.n_points = int(check.points)
        report.n_internal_faces = n_internal
        report.n_boundary_faces = max(0, len(faces) - n_internal)
        report.n_patches = len(boundaries)
        report.boundary_area = _boundary_area(points, faces, n_internal)
        report.surface_area_deviation_pct = (
            abs(report.boundary_area / max(fixture.surface_area, 1.0e-30) - 1.0) * 100.0
        )
        report.volume = float(volumes.sum())
        report.volume_relative_error_pct = (
            abs(report.volume / max(fixture.volume, 1.0e-30) - 1.0) * 100.0
        )
        report.negative_volumes = int(check.negative_volumes)
        report.quality = {
            "mesh_ok": bool(check.mesh_ok),
            "max_non_orthogonality": float(check.max_non_orthogonality),
            "avg_non_orthogonality": float(check.avg_non_orthogonality),
            "max_skewness": float(check.max_skewness),
            "max_aspect_ratio": float(check.max_aspect_ratio),
            "max_face_planar_deviation": check.max_face_planar_deviation,
            "max_face_normal_spread_deg": check.max_face_normal_spread_deg,
            "max_juretic_psi": check.max_juretic_psi,
            "mean_juretic_psi": check.mean_juretic_psi,
            "min_cell_h": check.min_cell_h,
            "mean_cell_h": check.mean_cell_h,
            "min_uniformity_factor": check.min_uniformity_factor,
            "mean_uniformity_factor": check.mean_uniformity_factor,
        }
    except Exception as exc:  # pragma: no cover - exercised by timeout/error fixtures
        report.error = f"{type(exc).__name__}: {exc}"
    return report


def _drop_tracker() -> tuple[DropInvocation, Callable[..., tuple[list[list[list[int]]], int]]]:
    from core.generator.native_poly import quality

    state = DropInvocation()
    original = quality.drop_degenerate_poly_cells

    def tracked(*args: Any, **kwargs: Any) -> tuple[list[list[list[int]]], int]:
        state.invoked = True
        state.calls += 1
        cells, dropped = original(*args, **kwargs)
        state.dropped_cells += int(dropped)
        return cells, dropped

    return state, tracked


def _run_direct(
    fixture: FixedPrimalFixture,
    case_dir: Path,
) -> object:
    return tet_to_poly_dual(fixture.primal_vertices, fixture.primal_tets, case_dir)


def _run_tier_fixed_primal(
    fixture: FixedPrimalFixture,
    case_dir: Path,
) -> object:
    def fixed_tet_generator(*_args: object, **_kwargs: object) -> NativeTetResult:
        return NativeTetResult(
            success=True,
            elapsed=0.0,
            n_cells=int(fixture.primal_tets.shape[0]),
            n_points=int(fixture.primal_vertices.shape[0]),
            message="POLY-ROUTE-ATTRIB1 fixed primal",
            tet_points=fixture.primal_vertices.copy(),
            tets=fixture.primal_tets.copy(),
        )

    with mock.patch.object(native_poly_harness, "generate_native_tet", fixed_tet_generator):
        return tier_native_poly._runner(
            fixture.surface_vertices,
            fixture.surface_faces,
            case_dir,
            seed_density=8,
            max_iter=1,
            n_lloyd=0,
            auto_escalate=False,
            auto_escalate_max=1,
            target_cells=None,
            max_cells=None,
            bl_layers=0,
            post_layers_num_layers=0,
        )


def run_fixture_comparison(
    fixture: FixedPrimalFixture,
    output_root: Path,
    *,
    repeats: int = 2,
) -> FixtureComparison:
    """Run both routes repeatedly on one fixed primal in the current process."""
    output_root.mkdir(parents=True, exist_ok=True)
    primal_identity = _array_digest(fixture.primal_vertices, fixture.primal_tets)
    comparison = FixtureComparison(
        fixture=fixture.name,
        primal_identity=primal_identity,
        primal_points=int(fixture.primal_vertices.shape[0]),
        primal_tets=int(fixture.primal_tets.shape[0]),
    )
    route_runs = (
        ("direct_tet_to_poly_dual", "direct_tet_to_poly_dual", _run_direct),
        ("tier_native_poly", "tier_native_poly:harness/tet_to_poly_dual", _run_tier_fixed_primal),
    )
    for route_name, selected_route, runner in route_runs:
        for repeat in range(1, int(repeats) + 1):
            case_dir = output_root / route_name / f"repeat-{repeat}"
            drop, tracked_drop = _drop_tracker()
            try:
                from core.generator.native_poly import quality

                with mock.patch.object(quality, "drop_degenerate_poly_cells", tracked_drop):
                    result = runner(fixture, case_dir)
                actual_selected_route = selected_route
                used_fixed_primal = True
                if (
                    route_name == "tier_native_poly"
                    and type(result).__name__ != "PolyHarnessResult"
                ):
                    actual_selected_route = "tier_native_poly:voronoi_fallback"
                    used_fixed_primal = False
                comparison.routes.append(
                    _census(
                        fixture,
                        case_dir,
                        route_name,
                        actual_selected_route,
                        repeat,
                        result,
                        drop,
                        used_fixed_primal,
                    )
                )
            except Exception as exc:  # keep one route failure diagnostic, not fatal
                comparison.routes.append(
                    RouteMeshReport(
                        fixture=fixture.name,
                        route_requested=route_name,
                        route_selected=selected_route,
                        repeat=repeat,
                        auto_escalate=False,
                        fixed_primal_injected=True,
                        primal_identity=primal_identity,
                        result_success=False,
                        result_message="",
                        result_type="",
                        drop=drop,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )

    for route_name, _selected_route, _runner in route_runs:
        route_reports = [item for item in comparison.routes if item.route_requested == route_name]
        if len(route_reports) >= 2:
            comparison.deterministic_repeat_identity[route_name] = (
                route_reports[0].disk_mesh_identity == route_reports[1].disk_mesh_identity
            )
    direct = [item for item in comparison.routes if item.route_requested == route_runs[0][0]]
    tier = [item for item in comparison.routes if item.route_requested == route_runs[1][0]]
    if direct and tier:
        comparison.direct_tier_identity_equal = (
            direct[0].disk_mesh_identity == tier[0].disk_mesh_identity
        )
    if (
        all(comparison.deterministic_repeat_identity.values())
        and comparison.direct_tier_identity_equal
    ):
        comparison.conclusion = (
            "fixed-primal direct and tier-native-poly routes select the same disk mesh; "
            "the historical cylinder discrepancy is not a route implementation difference "
            "on this shared primal"
        )
    else:
        comparison.conclusion = (
            "route or repeat identities differ; retain this fixture as attribution evidence "
            "before any optimization"
        )
    return comparison


def _fixture_worker(
    source_path: str,
    output_root: str,
    repeats: int,
    queue: Any,
) -> None:
    try:
        fixture = load_fixed_fixture(Path(source_path))
        comparison = run_fixture_comparison(fixture, Path(output_root), repeats=repeats)
        queue.put(asdict(comparison))
    except Exception as exc:  # pragma: no cover - child-process error transport
        queue.put({"fixture": Path(source_path).stem, "error": f"{type(exc).__name__}: {exc}"})


def run_fixture_with_timeout(
    source_path: Path,
    output_root: Path,
    *,
    timeout_seconds: float = 30.0,
    repeats: int = 2,
) -> FixtureComparison | dict[str, object]:
    """Run one fixture in a bounded child process."""
    ctx = mp.get_context("spawn")
    queue: Any = ctx.Queue()
    process = ctx.Process(
        target=_fixture_worker,
        args=(str(source_path), str(output_root), int(repeats), queue),
    )
    started = time.perf_counter()
    process.start()
    process.join(max(float(timeout_seconds), 0.01))
    if process.is_alive():
        process.terminate()
        process.join(2.0)
        return FixtureComparison(
            fixture=source_path.stem,
            primal_identity="",
            primal_points=0,
            primal_tets=0,
            timeout=True,
            timeout_seconds=float(time.perf_counter() - started),
            conclusion="fixture timeout; no route conclusion permitted",
        )
    try:
        payload: Any = queue.get(timeout=2.0)
        if "error" in payload:
            return cast(dict[str, object], payload)
        return _comparison_from_dict(payload)
    except queue_module.Empty:
        pass
    return {"fixture": source_path.stem, "error": "fixture child exited without a result"}


def _comparison_from_dict(payload: dict[str, Any]) -> FixtureComparison:
    routes = [
        RouteMeshReport(
            **{
                **item,
                "drop": DropInvocation(**item.get("drop", {})),
            }
        )
        for item in payload.get("routes", [])
    ]
    return FixtureComparison(
        fixture=str(payload["fixture"]),
        primal_identity=str(payload["primal_identity"]),
        primal_points=int(payload["primal_points"]),
        primal_tets=int(payload["primal_tets"]),
        timeout=bool(payload.get("timeout", False)),
        timeout_seconds=float(payload.get("timeout_seconds", 0.0)),
        routes=routes,
        deterministic_repeat_identity=dict(payload.get("deterministic_repeat_identity", {})),
        direct_tier_identity_equal=bool(payload.get("direct_tier_identity_equal", False)),
        conclusion=str(payload.get("conclusion", "")),
        error=str(payload.get("error", "")),
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        choices=("cube", "cylinder", "sphere", "all"),
        default="all",
    )
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo = _repo_root()
    names = ("cube", "cylinder", "sphere") if args.fixture == "all" else (args.fixture,)
    output_root = repo / ".cache" / "native_poly_route_attribution"
    results: list[object] = []
    for name in names:
        source = repo / "tests" / "benchmarks" / f"{name}.stl"
        result = run_fixture_with_timeout(
            source,
            output_root / name,
            timeout_seconds=args.timeout_s,
            repeats=args.repeats,
        )
        results.append(asdict(result) if isinstance(result, FixtureComparison) else result)
        print(json.dumps(results[-1], sort_keys=True, default=str))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
