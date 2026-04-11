"""다양한 입력 포맷/불량 메쉬에 대한 강건성 테스트."""

from __future__ import annotations

from pathlib import Path

import meshio
import numpy as np
import pytest
import trimesh

from core.analyzer.geometry_analyzer import GeometryAnalyzer
from core.pipeline.orchestrator import PipelineOrchestrator
from core.preprocessor.pipeline import Preprocessor


def _export_all(base: Path, name: str, mesh: trimesh.Trimesh) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for ext in (".stl", ".obj", ".ply", ".off"):
        p = base / f"{name}{ext}"
        mesh.export(str(p))
        paths[ext] = p
    return paths


def _make_diverse_cases(tmp_path: Path) -> dict[str, Path]:
    cases: dict[str, Path] = {}

    # clean primitives
    box = trimesh.creation.box(extents=(1.0, 1.2, 0.9))
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=0.8)
    cyl = trimesh.creation.cylinder(radius=0.4, height=1.5, sections=24)
    cases.update({f"box{ext}": p for ext, p in _export_all(tmp_path, "box", box).items()})
    cases.update({f"sphere{ext}": p for ext, p in _export_all(tmp_path, "sphere", sphere).items()})
    cases.update({f"cyl{ext}": p for ext, p in _export_all(tmp_path, "cyl", cyl).items()})

    # open surface (remove one face)
    open_box = box.copy()
    keep = np.arange(len(open_box.faces) - 1)
    open_box.update_faces(keep)
    open_box.remove_unreferenced_vertices()
    cases["open_box.stl"] = tmp_path / "open_box.stl"
    open_box.export(str(cases["open_box.stl"]))

    # self-intersection-ish (overlapping solids concatenation)
    b1 = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    b2 = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    b2.apply_translation((0.45, 0.0, 0.0))
    overlap = trimesh.util.concatenate([b1, b2])
    cases["overlap_boxes.stl"] = tmp_path / "overlap_boxes.stl"
    overlap.export(str(cases["overlap_boxes.stl"]))

    # degenerate triangle 포함
    deg_faces = np.vstack([box.faces, np.array([[0, 0, 1]], dtype=np.int64)])
    deg_mesh = trimesh.Trimesh(vertices=box.vertices.copy(), faces=deg_faces, process=False)
    cases["degenerate.stl"] = tmp_path / "degenerate.stl"
    deg_mesh.export(str(cases["degenerate.stl"]))

    # inverted winding
    inv_mesh = trimesh.Trimesh(vertices=box.vertices.copy(), faces=box.faces[:, ::-1], process=False)
    cases["inverted_winding.obj"] = tmp_path / "inverted_winding.obj"
    inv_mesh.export(str(cases["inverted_winding.obj"]))

    # meshio 포맷 (surface triangles)
    tri_mesh = meshio.Mesh(points=sphere.vertices, cells=[("triangle", sphere.faces.astype(np.int64))])
    for ext in (".vtk", ".vtu", ".msh"):
        p = tmp_path / f"sphere_surface{ext}"
        meshio.write(p, tri_mesh)
        cases[f"sphere_surface{ext}"] = p

    # invalid/corrupt files
    bad_stl = tmp_path / "bad_ascii.stl"
    bad_stl.write_text("solid bad\nfacet normal x y z\nendfacet\nendsolid\n")
    cases["bad_ascii.stl"] = bad_stl

    bad_obj = tmp_path / "bad.obj"
    bad_obj.write_text("v a b c\nf 1 2\n")
    cases["bad.obj"] = bad_obj
    return cases


def test_geometry_analyzer_handles_diverse_cases(tmp_path: Path) -> None:
    analyzer = GeometryAnalyzer()
    cases = _make_diverse_cases(tmp_path)
    expected_fail = {"bad_ascii.stl", "bad.obj"}

    for name, path in cases.items():
        if name in expected_fail:
            with pytest.raises(Exception):
                analyzer.analyze(path)
            continue
        report = analyzer.analyze(path)
        assert report.geometry.surface.num_faces > 0, name


def test_preprocessor_survives_rough_meshes(tmp_path: Path) -> None:
    analyzer = GeometryAnalyzer()
    preprocessor = Preprocessor()
    cases = _make_diverse_cases(tmp_path)

    rough_inputs = [
        "open_box.stl",
        "overlap_boxes.stl",
        "degenerate.stl",
        "inverted_winding.obj",
    ]
    for name in rough_inputs:
        src = cases[name]
        report = analyzer.analyze(src)
        out_dir = tmp_path / f"pre_{src.stem}"
        out_stl, out_report = preprocessor.run(
            src,
            report,
            out_dir,
            no_repair=False,
            surface_remesh=False,
            remesh_engine="auto",
        )
        assert out_stl.exists(), name
        assert out_report.preprocessing_summary.output_file.endswith("preprocessed.stl"), name


def test_orchestrator_dry_run_varied_formats(tmp_path: Path) -> None:
    orch = PipelineOrchestrator()
    cases = _make_diverse_cases(tmp_path)
    inputs = [
        "box.stl",
        "sphere.obj",
        "cyl.ply",
        "box.off",
        "sphere_surface.vtk",
        "sphere_surface.vtu",
        "sphere_surface.msh",
    ]
    for name in inputs:
        src = cases[name]
        out_dir = tmp_path / f"case_{src.stem}"
        result = orch.run(
            input_path=src,
            output_dir=out_dir,
            quality_level="draft",
            tier_hint="auto",
            dry_run=True,
            no_repair=True,
            surface_remesh=False,
            remesh_engine="auto",
        )
        assert result.success, f"{name}: {result.error}"
        assert result.strategy is not None, name
