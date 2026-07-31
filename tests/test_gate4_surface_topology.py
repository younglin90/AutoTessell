from __future__ import annotations

from pathlib import Path

from core.evaluator.gate4_surface_topology import audit_polymesh_surface


def _write_polymesh(
    case_dir: Path,
    *,
    points: list[tuple[float, float, float]],
    faces: list[list[int]],
    patches: list[tuple[str, int, int]],
) -> None:
    poly_mesh = case_dir / "constant" / "polyMesh"
    poly_mesh.mkdir(parents=True)
    (poly_mesh / "points").write_text(
        f"{len(points)}\n(\n" + "\n".join(f"({x} {y} {z})" for x, y, z in points) + "\n)\n",
        encoding="utf-8",
    )
    (poly_mesh / "faces").write_text(
        f"{len(faces)}\n(\n"
        + "\n".join(f"{len(face)}(" + " ".join(map(str, face)) + ")" for face in faces)
        + "\n)\n",
        encoding="utf-8",
    )
    (poly_mesh / "owner").write_text(
        f"{len(faces)}\n(\n" + "\n".join("0" for _ in faces) + "\n)\n",
        encoding="utf-8",
    )
    (poly_mesh / "neighbour").write_text("0\n(\n)\n", encoding="utf-8")
    (poly_mesh / "boundary").write_text(
        f"{len(patches)}\n(\n"
        + "\n".join(
            f"{name}\n{{\n type wall;\n nFaces {count};\n startFace {start};\n}}"
            for name, count, start in patches
        )
        + "\n)\n",
        encoding="utf-8",
    )


_TET_POINTS = [
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
]
_TET_FACES = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]


def test_closed_tetrahedron_reports_combinatorial_topology_without_si_claim(
    tmp_path: Path,
) -> None:
    _write_polymesh(
        tmp_path,
        points=_TET_POINTS,
        faces=_TET_FACES,
        patches=[("wall", 4, 0)],
    )

    audit = audit_polymesh_surface(tmp_path)

    assert audit.topology_valid
    assert audit.status == "unverified_self_intersection_not_checked"
    assert audit.self_intersection_status == "unverified_not_checked"
    assert audit.component_count == 1
    assert audit.boundary_loop_count == 0
    assert audit.euler_characteristic == 2
    assert audit.genus == 0
    assert audit.open_edge_count == 0
    assert audit.nonmanifold_edge_count == 0
    assert audit.nonmanifold_vertex_count == 0
    assert audit.artifact is not None


def test_disconnected_closed_tetrahedra_preserve_two_components(tmp_path: Path) -> None:
    points = _TET_POINTS + [(x + 3.0, y, z) for x, y, z in _TET_POINTS]
    faces = _TET_FACES + [[index + 4 for index in face] for face in _TET_FACES]
    _write_polymesh(tmp_path, points=points, faces=faces, patches=[("wall", 8, 0)])

    audit = audit_polymesh_surface(tmp_path)

    assert audit.topology_valid
    assert audit.component_count == 2
    assert audit.boundary_loop_count == 0
    assert audit.euler_characteristic == 4
    assert audit.genus == 0


def test_open_triangle_reports_one_boundary_loop_without_si_claim(tmp_path: Path) -> None:
    _write_polymesh(
        tmp_path,
        points=_TET_POINTS[:3],
        faces=[[0, 1, 2]],
        patches=[("wall", 1, 0)],
    )

    audit = audit_polymesh_surface(tmp_path)

    assert audit.topology_valid
    assert audit.boundary_loop_count == 1
    assert audit.euler_characteristic == 1
    assert audit.genus == 0
    assert audit.self_intersection_status == "unverified_not_checked"


def test_nonmanifold_edge_is_fail_closed(tmp_path: Path) -> None:
    _write_polymesh(
        tmp_path,
        points=_TET_POINTS + [(0.0, 0.0, -1.0)],
        faces=[[0, 1, 2], [1, 0, 3], [0, 1, 4]],
        patches=[("wall", 3, 0)],
    )

    audit = audit_polymesh_surface(tmp_path)

    assert not audit.topology_valid
    assert audit.status == "unverified_surface_topology_invalid"
    assert audit.nonmanifold_edge_count == 1
    assert audit.genus is None


def test_malformed_patch_partition_is_fail_closed(tmp_path: Path) -> None:
    _write_polymesh(
        tmp_path,
        points=_TET_POINTS,
        faces=_TET_FACES,
        patches=[("wall", 4, 1)],
    )

    audit = audit_polymesh_surface(tmp_path)

    assert not audit.topology_valid
    assert audit.status == "unverified_output_artifact_malformed"
    assert audit.malformed_reason == "invalid_patch_ranges"


def test_missing_required_file_is_fail_closed(tmp_path: Path) -> None:
    poly_mesh = tmp_path / "constant" / "polyMesh"
    poly_mesh.mkdir(parents=True)
    (poly_mesh / "points").write_text("0\n(\n)\n", encoding="utf-8")

    audit = audit_polymesh_surface(tmp_path)

    assert not audit.topology_valid
    assert audit.status == "unverified_output_artifact_missing_or_unsafe"
    assert audit.artifact is None
