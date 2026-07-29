"""Temporary diagnostic for the post-BSP flip lane; log-only."""

from pathlib import Path

import numpy as np

from core.analyzer.file_reader import load_mesh
from core.generator.native_tet.boundary_invariant import check_boundary_invariant
from core.generator.native_tet.mesher import generate_native_tet


def test_report_each_post_bsp_flip_boundary_effect(tmp_path, monkeypatch, capsys) -> None:
    import core.generator.native_tet.flip as flip_module

    for name in ("flip_faces_23", "flip_edges_32", "flip_edges_44"):
        original = getattr(flip_module, name)

        def wrapped(points, tets, *args, __name=name, __original=original, **kwargs):
            out_tets, count = __original(points, tets, *args, **kwargs)
            report = check_boundary_invariant(
                points, tets, points, out_tets,
                f"wrapped_{__name}", log_only=True,
            )
            print(
                "EEE_DIAG",
                __name,
                "count", int(count),
                "before", report.before_face_count,
                "after", report.after_face_count,
                "added", report.added_faces,
                "removed", report.removed_faces,
            )
            return out_tets, count

        monkeypatch.setattr(flip_module, name, wrapped)

    mesh = load_mesh(Path(__file__).resolve().parent / "benchmarks" / "naca0012.stl")
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    result = generate_native_tet(
        np.asarray(mesh.vertices, dtype=float),
        np.asarray(mesh.faces, dtype=np.int64),
        tmp_path / "naca",
        target_cells=2000,
    )
    assert result.success, result.message
    print(capsys.readouterr().out)
