"""한 STL 단독 실행 — subprocess 진입점. 결과를 JSON 으로 stdout 출력."""
from __future__ import annotations
import os
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
os.environ.setdefault("AUTO_TESSELL_WILDMESH_USE_CACHED", "1")
import sys, json, time, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

def main() -> int:
    if len(sys.argv) < 3:
        print("usage: run_one.py <stl> <n_layers> [target_cells]", file=sys.stderr)
        return 1
    stl = Path(sys.argv[1])
    n_layers = int(sys.argv[2])
    target_cells = int(sys.argv[3]) if len(sys.argv) > 3 else None

    out = {
        "stl": stl.name, "ok": False, "verdict": "ERROR",
        "n_cells": 0, "n_wall_faces": 0, "n_prism": 0, "bl_layers_actual": 0,
        "max_skew": 0.0, "max_non_ortho": 0.0, "max_aspect": 0.0,
        "elapsed": 0.0, "err": "",
    }
    t0 = time.time()
    try:
        from core.pipeline.orchestrator import PipelineOrchestrator
        with tempfile.TemporaryDirectory(prefix="ver_") as td:
            case = Path(td) / "case"
            tsp = {
                "boundary_layers_enabled": True,
                "cfmesh_bl_n_layers": int(n_layers),
                "cfmesh_bl_thickness_ratio": 1.2,
            }
            res = PipelineOrchestrator().run(
                input_path=stl, output_dir=case,
                mesh_type="tet", quality_level="draft",
                tier_hint="tier_wildmesh",
                write_of_case=False,
                tier_specific_params=tsp,
                max_cells=int(target_cells * 1.5) if target_cells else None,
            )
            qr = getattr(res, "quality_report", None)
            es = getattr(qr, "evaluation_summary", None) if qr else None
            cm = getattr(es, "checkmesh", None) if es else None
            v = getattr(es, "verdict", None) if es else None
            verdict = str(getattr(v, "value", v)).upper() if v else "UNKNOWN"
            out["verdict"] = verdict
            if cm is not None:
                out["n_cells"] = int(getattr(cm, "cells", 0) or 0)
                out["max_skew"] = float(getattr(cm, "max_skewness", 0.0) or 0.0)
                out["max_non_ortho"] = float(getattr(cm, "max_non_orthogonality", 0.0) or 0.0)
                out["max_aspect"] = float(getattr(cm, "max_aspect_ratio", 0.0) or 0.0)
            bl_q = case / "native_bl_quality.json"
            if bl_q.exists():
                d = json.loads(bl_q.read_text())
                out["n_wall_faces"] = int(d.get("n_wall_faces", 0))
                out["n_prism"] = int(d.get("n_prism_cells", 0))
                if out["n_wall_faces"] > 0:
                    out["bl_layers_actual"] = int(round(out["n_prism"] / out["n_wall_faces"]))
            if out["bl_layers_actual"] == 0:
                bnd = case / "constant" / "polyMesh" / "boundary"
                if bnd.exists() and "bl_internal_domain" in bnd.read_text():
                    out["bl_layers_actual"] = 1
            out["ok"] = (verdict == "PASS")
    except Exception as exc:
        out["err"] = f"{type(exc).__name__}: {exc}"[:300]
    out["elapsed"] = round(time.time() - t0, 1)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
