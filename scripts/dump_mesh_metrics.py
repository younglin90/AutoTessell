"""O4 / beta2663 — Mesh metrics JSON dump.

case_dir 의 polyMesh + native_bl_quality.json + 생성된 voxel_size 등 종합 →
단일 JSON 으로 통합 export. CI/CD pipeline 에 mesh quality gate 로 사용.

Usage:
    python3 scripts/dump_mesh_metrics.py case_dir [-o metrics.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()

    case = args.case_dir
    pm_dir = case / "constant" / "polyMesh"
    if not pm_dir.exists():
        pm_dir = case
    if not (pm_dir / "points").exists():
        print(f"[ERR] polyMesh 없음: {pm_dir}", file=sys.stderr)
        return 1

    metrics: dict = {
        "case_dir": str(case),
        "polymesh_dir": str(pm_dir),
        "files": {},
        "quality": {},
    }

    # polyMesh file sizes / line counts.
    for fname in ("points", "faces", "owner", "neighbour", "boundary"):
        fpath = pm_dir / fname
        if fpath.exists():
            metrics["files"][fname] = {
                "bytes": fpath.stat().st_size,
                "lines": sum(1 for _ in fpath.open(encoding="utf-8", errors="replace")),
            }
        else:
            metrics["files"][fname] = None

    # native_bl_quality.json 통합.
    work_dir = case / "_work"
    quality_json = work_dir / "native_bl_quality.json"
    if not quality_json.exists():
        quality_json = case / "native_bl_quality.json"
    if quality_json.exists():
        try:
            qd = json.loads(quality_json.read_text(encoding="utf-8"))
            # numeric 필드 추출.
            for k in (
                "n_wall_faces", "n_wall_verts", "n_prism_cells",
                "max_aspect_ratio", "n_degenerate_prisms",
                "wall_preserve_max_diff", "wall_preserve_within_envelope",
                "lcr_n_reduced_verts", "aniso_split_max_aspect_in",
            ):
                if k in qd:
                    metrics["quality"][k] = qd[k]
            if "quality" in qd and isinstance(qd["quality"], list):
                qs = qd["quality"]
                if qs:
                    metrics["quality"]["q_count"] = len(qs)
                    metrics["quality"]["q_min"] = float(min(qs))
                    metrics["quality"]["q_max"] = float(max(qs))
                    metrics["quality"]["q_mean"] = float(sum(qs) / len(qs))
        except Exception as exc:
            metrics["quality"]["error"] = f"parse: {exc!s:.50}"
    else:
        metrics["quality"]["note"] = "native_bl_quality.json 없음"

    # output.
    out = args.output
    if out is None:
        out = case / "mesh_metrics.json"
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {out}")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
