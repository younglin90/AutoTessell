"""R1 / beta2681 — Failed mesh postmortem diagnostic JSON.

mesh 생성 실패 시 입력 mesh 통계 + 실패 reason + 권장 조치를 JSON 으로 dump.
사용자 troubleshooting + 자동 retry 의사결정 입력.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


@dataclass
class DiagJSONResult:
    success: bool
    output_path: str = ""
    n_keys: int = 0
    elapsed_s: float = 0.0
    message: str = ""


def write_failed_mesh_diagnostic(
    output_path: str | Path,
    *,
    V: NDArray[np.float64] | None = None,
    F: NDArray[np.int64] | None = None,
    failure_reason: str = "",
    engine: str = "",
    seed_density: int | None = None,
    extra: dict | None = None,
) -> DiagJSONResult:
    """실패한 mesh run 의 종합 진단 JSON 작성.

    포함 항목:
        - input mesh stats (V/F count, bbox, watertight, manifold).
        - feature edges count (sharp).
        - aspect ratio max.
        - signed volume (closed mesh check).
        - failure_reason / engine / seed_density.
        - error_catalog 추천.
        - extra dict (caller 가 추가 컨텍스트).
    """
    t0 = time.perf_counter()
    out = Path(output_path)

    diag: dict = {
        "schema_version": "1.0",
        "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
        "engine": engine,
        "seed_density": seed_density,
        "failure_reason": failure_reason,
        "input_stats": {},
        "recommendations": [],
    }

    if V is not None and F is not None:
        try:
            V = np.asarray(V, dtype=np.float64)
            F = np.asarray(F, dtype=np.int64)
            n_v = int(V.shape[0])
            n_f = int(F.shape[0])
            diag["input_stats"]["n_vertices"] = n_v
            diag["input_stats"]["n_faces"] = n_f
            if n_v > 0:
                bmin = V.min(axis=0).tolist()
                bmax = V.max(axis=0).tolist()
                diag["input_stats"]["bbox_min"] = [float(x) for x in bmin]
                diag["input_stats"]["bbox_max"] = [float(x) for x in bmax]
                extents = np.array(bmax) - np.array(bmin)
                diag["input_stats"]["bbox_diag"] = float(np.linalg.norm(extents))
                if extents.min() > 0:
                    diag["input_stats"]["aspect_ratio"] = float(extents.max() / extents.min())

            if n_f > 0:
                # surface area + signed volume.
                e1 = V[F[:, 1]] - V[F[:, 0]]
                e2 = V[F[:, 2]] - V[F[:, 0]]
                fa = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
                diag["input_stats"]["surface_area"] = float(fa.sum())
                diag["input_stats"]["face_area_min"] = float(fa.min())
                diag["input_stats"]["face_area_max"] = float(fa.max())
                p0 = V[F[:, 0]]; p1 = V[F[:, 1]]; p2 = V[F[:, 2]]
                signed_vol = float(((np.cross(p0, p1) * p2).sum(axis=1)).sum()) / 6.0
                diag["input_stats"]["signed_volume"] = signed_vol

            # topology.
            try:
                from core.analyzer.topology import is_watertight, is_manifold
                diag["input_stats"]["watertight"] = bool(is_watertight(F))
                diag["input_stats"]["manifold"] = bool(is_manifold(F))
            except Exception:
                pass

            # feature edges.
            try:
                from core.analyzer.feature_edges import extract_feature_edges
                fe = extract_feature_edges(V, F)
                diag["input_stats"]["n_boundary_edges"] = fe.n_boundary_edges
                diag["input_stats"]["n_sharp_edges"] = fe.n_sharp_dihedral_edges
                diag["input_stats"]["n_corners"] = fe.n_corner_vertices
            except Exception:
                pass
        except Exception as exc:
            diag["input_stats"]["error"] = f"compute fail: {exc!s:.60}"

    # recommendation derivation.
    recs: list[str] = []
    stats = diag["input_stats"]
    if stats.get("n_vertices", 999) < 4:
        recs.append("INPUT_TOO_SMALL: 입력 vertex 수 < 4. 다른 mesh source 사용.")
    elif stats.get("watertight") is False:
        recs.append("INPUT_NOT_WATERTIGHT: --force-repair 또는 --mesh-type tet 권장.")
    if stats.get("manifold") is False:
        recs.append("INPUT_NON_MANIFOLD: --force-repair 자동 수리.")
    if stats.get("aspect_ratio", 0) > 100:
        recs.append(f"thin geometry (aspect={stats.get('aspect_ratio'):.1f}): --mesh-type tet 권장.")
    if abs(stats.get("signed_volume", 0)) < 1e-12 and stats.get("n_faces", 0) > 0:
        recs.append("near-zero signed volume: surface inverted 또는 not closed.")
    if not recs:
        recs.append("입력 mesh 자체는 합리적 — engine-specific issue 의심.")

    diag["recommendations"] = recs

    if extra:
        diag["extra"] = extra

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")

    return DiagJSONResult(
        success=True, output_path=str(out),
        n_keys=len(diag),
        elapsed_s=time.perf_counter() - t0,
        message=f"diagnostic written: {len(recs)} recommendations",
    )
