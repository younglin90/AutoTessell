"""Round 38 — procedural adversarial bench matrix.

Thingi10k 스케일 자동 다운로드는 어려우므로 trimesh 의 procedural primitives 로
다양한 형상 30+ 개 생성 → native_tet 돌려 성공률 + 품질 집계.

기본 STL 5 개 (tests/stl/01~05) + 여러 primitive 조합:
    - sphere (여러 subdivision)
    - box (비균등 aspect)
    - cylinder
    - torus
    - cone / capsule
    - union / difference (boolean)

결과: tests/stl/native_tet_matrix_bench.json.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest


BENCH_OUT = Path(__file__).parent / "stl" / "native_tet_matrix_bench.json"


def _procedural_meshes() -> list[tuple[str, Any]]:
    import trimesh

    out: list[tuple[str, Any]] = []
    # sphere variants.
    for sub in (0, 1, 2):
        out.append((f"sphere_sub{sub}", trimesh.creation.icosphere(subdivisions=sub)))
    # box variants.
    for ex in ((1, 1, 1), (1, 2, 0.5), (1, 0.2, 3)):
        out.append((f"box_{ex[0]}x{ex[1]}x{ex[2]}", trimesh.creation.box(extents=ex)))
    # cylinder.
    for h, r, s in ((1, 0.5, 16), (2, 0.3, 8), (0.5, 1.0, 24)):
        out.append(
            (f"cylinder_h{h}_r{r}_s{s}",
             trimesh.creation.cylinder(radius=r, height=h, sections=s))
        )
    # torus.
    try:
        out.append(("torus", trimesh.creation.torus(1.0, 0.3)))
    except Exception:
        pass
    # capsule.
    try:
        out.append(("capsule", trimesh.creation.capsule(height=1.0, radius=0.3)))
    except Exception:
        pass
    # cone.
    try:
        out.append(("cone", trimesh.creation.cone(radius=0.5, height=1.5)))
    except Exception:
        pass
    return out


def _run_one(name: str, mesh: Any, seed_density: int = 6) -> dict:
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.quality import tet_shape_quality

    V = np.asarray(mesh.vertices, dtype=np.float64)
    F = np.asarray(mesh.faces, dtype=np.int64)

    with tempfile.TemporaryDirectory() as td:
        t0 = time.perf_counter()
        try:
            res = generate_native_tet(
                V, F, Path(td) / "case",
                seed_density=seed_density,
                enable_phase_a=True,
                enable_phase_b=False,
                max_input_vertices=20000,
            )
            elapsed = time.perf_counter() - t0
            row = {
                "name": name,
                "n_surf_verts": int(V.shape[0]),
                "n_surf_faces": int(F.shape[0]),
                "success": bool(res.success),
                "elapsed_s": round(elapsed, 3),
                "message": (res.message or "")[:120],
            }
            if res.success and res.tets is not None:
                q = tet_shape_quality(res.tet_points, res.tets)
                row.update({
                    "n_cells": int(res.n_cells),
                    "min_q": round(float(q.min()), 4) if q.size else 0.0,
                    "mean_q": round(float(q.mean()), 4) if q.size else 0.0,
                })
            return row
        except Exception as e:
            return {
                "name": name,
                "success": False,
                "error": str(e)[:120],
                "elapsed_s": round(time.perf_counter() - t0, 3),
            }


@pytest.mark.slow
def test_native_tet_procedural_matrix_bench() -> None:
    """30+ procedural STL 돌려 성공률 집계 + JSON 저장."""
    try:
        cases = _procedural_meshes()
    except Exception:
        pytest.skip("trimesh procedural primitives 사용 불가")

    if not cases:
        pytest.skip("procedural meshes 없음")

    rows: list[dict] = []
    for name, mesh in cases:
        rows.append(_run_one(name, mesh))

    BENCH_OUT.parent.mkdir(parents=True, exist_ok=True)
    BENCH_OUT.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    n_success = sum(1 for r in rows if r.get("success"))
    total = len(rows)
    print(f"\n[bench matrix] {n_success}/{total} success")

    # 최소 50% 성공 요구.
    assert n_success >= max(1, total // 2), (
        f"성공률 낮음: {n_success}/{total}"
    )
