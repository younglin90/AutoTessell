"""Autoresearch verify — test_cube.stl tet+BL composite metric.

Outputs ONE number on stdout (last line). Higher = better.

Composite (range ~0-100):
  surface_term = (1 - clamp(hausdorff_rel, 0, 1)) * 40   # 표면 보존 (40)
  verdict_term = (1 if PASS else 0) * 30                  # Evaluator 합격 (30)
  layers_term  = clamp(n_layers_achieved / 3, 0, 1) * 20  # BL 층 누적 (20)
  skew_term    = clamp(1 - max_skewness/200, 0, 1) * 10   # 메쉬 quality (10)

Guard 는 별도 — pytest 가 따로 호출됨.
"""
from __future__ import annotations
import sys, json, time, re, traceback
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    stl = ROOT / "test_cube.stl"
    if not stl.exists():
        print("ERR: test_cube.stl not found", file=sys.stderr)
        print(0.0)
        return 1

    try:
        from core.pipeline.orchestrator import PipelineOrchestrator
    except Exception as exc:
        print(f"ERR import: {exc}", file=sys.stderr)
        print(0.0)
        return 1

    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "case"
        orch = PipelineOrchestrator()
        try:
            res = orch.run(
                input_path=stl, output_dir=case,
                mesh_type="tet", quality_level="draft",
                write_of_case=False,
                tier_specific_params={
                    "boundary_layers_enabled": True,
                    "cfmesh_bl_n_layers": 3,
                    "cfmesh_bl_thickness_ratio": 1.2,
                    "post_layers_engine": "auto",
                },
            )
        except Exception as exc:
            print(f"ERR run: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            print(0.0)
            return 1

        qr = getattr(res, "quality_report", None)
        # ---------- 추출 ----------
        hausdorff_rel = 1.0
        verdict = "FAIL"
        max_skew = 999.0
        n_layers = 0
        cells = 0

        if qr is not None:
            es = getattr(qr, "evaluation_summary", None)
            if es is not None:
                v = getattr(es, "verdict", None)
                vv = getattr(v, "value", v)
                verdict = str(vv).upper() if vv is not None else "FAIL"
                cm = getattr(es, "checkmesh", None)
                if cm is not None:
                    cells = int(getattr(cm, "cells", 0) or 0)
                    sk = getattr(cm, "max_skewness", None)
                    if sk is not None:
                        max_skew = float(sk)
                fid = getattr(es, "geometry_fidelity", None)
                if fid is None:
                    fid = getattr(qr, "geometry_fidelity", None)
                if fid is not None:
                    h = getattr(fid, "hausdorff_relative", None)
                    if h is not None:
                        hausdorff_rel = float(h)

        # n_layers — bl_quality.json: n_prism_cells / n_wall_faces 가 실제 누적 layer.
        bl_q = case / "native_bl_quality.json"
        if bl_q.exists():
            try:
                d = json.loads(bl_q.read_text())
                n_pc = float(d.get("n_prism_cells", 0) or 0)
                n_wf = float(d.get("n_wall_faces", 0) or 0)
                if n_wf > 0:
                    n_layers = max(n_layers, int(round(n_pc / n_wf)))
                # config.num_layers 도 fallback
                cfg_d = d.get("config") or {}
                if isinstance(cfg_d, dict):
                    nl = cfg_d.get("num_layers")
                    if nl is not None and n_layers == 0:
                        n_layers = int(nl)
            except Exception:
                pass
        # fallback — boundary 에 bl_side 패치 있으면 최소 1
        if n_layers == 0:
            try:
                bnd = case / "constant" / "polyMesh" / "boundary"
                if bnd.exists():
                    txt = bnd.read_text()
                    if "bl_side" in txt or "bl_internal_domain" in txt or "bl_layer" in txt:
                        n_layers = 1
            except Exception:
                pass

        # ---------- composite ----------
        def _clamp(x, lo, hi):
            return max(lo, min(hi, x))

        surface_term = (1.0 - _clamp(hausdorff_rel, 0.0, 1.0)) * 40.0
        verdict_term = (1.0 if verdict == "PASS" else 0.0) * 30.0
        layers_term  = _clamp(n_layers / 3.0, 0.0, 1.0) * 20.0
        skew_term    = _clamp(1.0 - (max_skew / 200.0), 0.0, 1.0) * 10.0
        score = surface_term + verdict_term + layers_term + skew_term

        # 진단 (stderr) — 점수만 stdout 마지막 줄
        print(
            f"DIAG hausdorff={hausdorff_rel:.4f} verdict={verdict} "
            f"n_layers={n_layers} max_skew={max_skew:.2f} cells={cells} "
            f"surface={surface_term:.1f} verdict_t={verdict_term:.1f} "
            f"layers_t={layers_term:.1f} skew_t={skew_term:.1f}",
            file=sys.stderr,
        )
        print(f"{score:.3f}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
