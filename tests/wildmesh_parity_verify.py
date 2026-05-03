"""autoresearch metric: GUI tet mesher 결과 vs wildmesh 직접 호출 결과 match%.

자동화 verify command — exit 0 + stdout = match_pct (float).

방법:
    1. test STL load (cube, easy default).
    2. wildmesh 직접 호출 (generate_via_wildmeshing_cached) → V_lib, T_lib.
    3. GUI 가 사용하는 PipelineOrchestrator + PipelineWorker path 로 동일 STL 처리
       → polyMesh 결과 → V_gui, T_gui 추출.
    4. parity_compare_strict(V_lib, T_lib, V_gui, T_gui) → match_pct.
    5. stdout: match_pct (e.g. "85.32").
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

logging.disable(logging.CRITICAL)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _load_stl_VF(path: Path) -> tuple[np.ndarray, np.ndarray]:
    from core.analyzer.readers.stl import read_stl
    mesh = read_stl(str(path))
    V = np.asarray(mesh.vertices, dtype=np.float64)
    F = np.asarray(mesh.faces, dtype=np.int64)
    return V, F


def _read_polymesh_tets(case_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """polyMesh dir → V (Np, 3), T (Nt, 4) 추출. tet 가정."""
    from core.utils.ccmio_native_binary import _simple_polymesh_read
    V, faces, owner, neighbour, _ = _simple_polymesh_read(case_dir)
    if V is None:
        return np.zeros((0, 3)), np.zeros((0, 4), dtype=np.int64)
    n_cells = (
        max(int(max(owner)), int(max([n for n in neighbour if n >= 0],
                                     default=-1))) + 1
        if len(owner) > 0 else 0
    )
    cell_face_lists: list[list[int]] = [[] for _ in range(n_cells)]
    for fi, o in enumerate(owner):
        cell_face_lists[int(o)].append(fi)
    for fi, n in enumerate(neighbour):
        if int(n) >= 0:
            cell_face_lists[int(n)].append(fi)
    tets = []
    for ci in range(n_cells):
        f_ids = cell_face_lists[ci]
        if len(f_ids) != 4:
            continue
        verts = set()
        for fi in f_ids:
            verts.update(int(v) for v in faces[fi])
        if len(verts) == 4:
            tets.append(sorted(verts))
    if not tets:
        return V, np.zeros((0, 4), dtype=np.int64)
    return V, np.array(tets, dtype=np.int64)


def _gui_path_run(V: np.ndarray, F: np.ndarray, case_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """GUI PipelineWorker 가 호출하는 동일 path."""
    # write STL temp.
    from core.utils.stl_writer import write_stl_ascii
    stl_path = case_dir / "input.stl"
    write_stl_ascii(V, F, stl_path)

    from core.pipeline.orchestrator import PipelineOrchestrator
    orch = PipelineOrchestrator()
    out_dir = case_dir / "out"
    result = orch.run(stl_path, out_dir, mesh_type="tet", quality_level="draft")

    poly_dir = out_dir / "constant" / "polyMesh"
    if not poly_dir.exists():
        return np.zeros((0, 3)), np.zeros((0, 4), dtype=np.int64)
    return _read_polymesh_tets(poly_dir)


def _wildmesh_run(V: np.ndarray, F: np.ndarray, cache_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Reference 결과 — tier_wildmesh draft 와 동일 params 사용 → 동일 cache key."""
    from core.generator.native_tet.wildmesh_native_wrapper import (
        generate_via_wildmeshing_cached,
    )
    V_out, T_out, r = generate_via_wildmeshing_cached(
        V, F, cache_dir=str(cache_dir),
        # tier_wildmesh _get_quality_params("draft") 와 일치.
        stop_quality=20.0, edge_length_r=0.06, epsilon=0.002, max_its=40,
    )
    return V_out, T_out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stl", default=str(REPO / "tests" / "stl" / "01_easy_cube.stl"),
    )
    ap.add_argument(
        "--cache",
        # GUI tier_wildmesh 와 동일 cache_dir → SHA256(V,F,params) 공유.
        default=os.environ.get(
            "AUTO_TESSELL_WILDMESH_CACHE_DIR",
            str(Path.home() / ".cache" / "autotessell" / "wildmesh"),
        ),
    )
    args = ap.parse_args()

    stl_path = Path(args.stl)
    if not stl_path.exists():
        print("0.0")  # match% 0 if input missing.
        return 0

    cache_dir = Path(args.cache)
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        V, F = _load_stl_VF(stl_path)
    except Exception:
        print("0.0")
        return 0

    # wildmesh reference.
    V_lib, T_lib = _wildmesh_run(V, F, cache_dir)
    if T_lib.shape[0] == 0:
        print("0.0")
        return 0

    # GUI path.
    with tempfile.TemporaryDirectory() as td:
        try:
            V_gui, T_gui = _gui_path_run(V, F, Path(td))
        except Exception:
            V_gui, T_gui = np.zeros((0, 3)), np.zeros((0, 4), dtype=np.int64)

    if T_gui.shape[0] == 0:
        print("0.0")
        return 0

    # compute match%.
    from core.generator.native_tet.wildmesh_native_wrapper import (
        parity_compare_strict,
    )
    m = parity_compare_strict(V_lib, T_lib, V_gui, T_gui)
    overall = float(m.get("overall_match_pct", 0.0))
    print(f"{overall:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
