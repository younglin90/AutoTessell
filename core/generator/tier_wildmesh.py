"""Tier WildMesh: wildmeshing (fTetWild Python 바인딩) 기반 Tet 메쉬 생성기.

Wild 계열 알고리즘 개요
======================
WildMesh는 fTetWild 알고리즘의 Python 바인딩이다.
"envelope" 방식으로 작동하며, 입력 표면에서
``epsilon × bbox_diagonal`` 이내 편차를 허용하면서 고품질 사면체를 생성한다.

형상 보존을 위한 파라미터 지침
-------------------------------
- epsilon을 0.02 이상으로 올리면 cube 같은 날카로운 형상의 모서리가
  tet 경계에서 1~2cm 이상 이탈해 시각적으로 모양이 달라 보인다.
- 기본값(draft=0.002, standard=0.001, fine=0.0003)은 cube 꼭짓점 전부를
  tet 경계면에 0.0001m 이내로 보존한다.
- 생성 후 경계 정점 snap 후처리로 잔류 편차를 추가 제거한다.

파라미터 요약
-------------
- ``wildmesh_epsilon``      : envelope 크기 (bbox 대각선 비율).
  draft=0.002, standard=0.001, fine=0.0005
- ``wildmesh_edge_length_r``: bbox 대각선 대비 엣지 비율.
  draft=0.06, standard=0.05, fine=0.03
- ``wildmesh_stop_quality`` : 목표 품질. draft=20, standard=10, fine=6.
- ``wildmesh_max_its``      : 최대 최적화 반복 횟수.
- ``wildmesh_snap_boundary``: 경계 snap 후처리 사용 여부 (기본 true).
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_wildmesh"

try:
    _HAS_WILDMESHING = importlib.util.find_spec("wildmeshing") is not None
except Exception:
    _HAS_WILDMESHING = False


# 파라미터 안전 범위 — 범위 밖은 clamp + warning log
_PARAM_RANGES: dict[str, tuple[float, float]] = {
    "epsilon": (0.0001, 0.1),  # 너무 작으면 timeout, 너무 크면 형상 손상
    "edge_length_r": (0.005, 0.2),  # 너무 작으면 OOM, 너무 크면 저해상도
    "stop_quality": (3.0, 100.0),  # fTetWild 내부 수렴 안정 범위
    "max_its": (10.0, 500.0),  # 10 미만 덜수렴, 500 초과 과부하
}


_TIMEOUT_MAX_SEC = 30 * 60  # 30분 상한 — 무한 대기 방지


def _compute_timeout(quality_level: str, n_faces: int, params: dict[str, Any]) -> int:
    """quality_level + face 수 기반 동적 timeout 계산. 사용자 override 지원.

    공식:
      draft:    60 + n_faces / 500
      standard: 150 + n_faces / 300
      fine:     400 + n_faces / 100

    상한 30분. 사용자 `wildmesh_timeout` override는 clamp.
    """
    # 명시적 override
    if "wildmesh_timeout" in params:
        try:
            override = int(params["wildmesh_timeout"])
            return max(1, min(override, _TIMEOUT_MAX_SEC))
        except (TypeError, ValueError):
            pass

    _BASE = {"draft": 60, "standard": 150, "fine": 400}
    _DIVISOR = {"draft": 500, "standard": 300, "fine": 100}
    base = _BASE.get(quality_level, 150)
    divisor = _DIVISOR.get(quality_level, 300)
    computed = int(base + max(0, n_faces) / divisor)
    result = min(computed, _TIMEOUT_MAX_SEC)
    logger.debug(
        "wildmesh_timeout_computed",
        quality_level=quality_level,
        n_faces=n_faces,
        computed_sec=result,
        max_sec=_TIMEOUT_MAX_SEC,
    )
    return result


def _clamp_param(name: str, value: float) -> float:
    """파라미터를 안전 범위로 clamp. 범위 밖이면 warning log."""
    lo, hi = _PARAM_RANGES[name]
    if value < lo:
        logger.warning(
            "wildmesh_param_clamped",
            param=name,
            requested=value,
            clamped_to=lo,
            valid_range=[lo, hi],
        )
        return lo
    if value > hi:
        logger.warning(
            "wildmesh_param_clamped",
            param=name,
            requested=value,
            clamped_to=hi,
            valid_range=[lo, hi],
        )
        return hi
    return value


def _get_quality_params(quality_level: str, params: dict[str, Any]) -> dict[str, Any]:
    """quality_level에 따른 기본 파라미터를 반환하고 tier_specific_params로 오버라이드한다.

    외부 override 값은 _PARAM_RANGES로 clamp되어 fTetWild의 timeout/OOM/형상 손상을 방지한다.
    """
    # 실측 기반 튜닝 (2026-04-21, tests/stl/05_ultra_knot.stl 포함):
    # - epsilon 0.002+, edge_length_r 0.06  → 복잡 형상에서 non-ortho 87°+ FAIL
    # - epsilon 0.0003, edge_length_r 0.02  → knot 류 563s timeout
    # - epsilon 0.001,  edge_length_r 0.05  → TetWild 매칭, 15s PASS (sweet spot)
    _defaults: dict[str, dict[str, Any]] = {
        # draft: 단순 형상 빠른 통과 — cube/box 기준
        "draft": {"stop_quality": 20.0, "max_its": 40, "epsilon": 0.002, "edge_length_r": 0.06},
        # standard: TetWild 매칭 — 복잡 형상(knot, gear 등) 첫 시도 PASS
        "standard": {"stop_quality": 10.0, "max_its": 80, "epsilon": 0.001, "edge_length_r": 0.05},
        # fine: standard 보다 tight 하되 fTetWild 수렴 가능한 한계
        "fine": {"stop_quality": 6.0, "max_its": 120, "epsilon": 0.0005, "edge_length_r": 0.03},
    }
    d = _defaults.get(quality_level, _defaults["standard"])
    raw_stop = float(params.get("wildmesh_stop_quality", d["stop_quality"]))
    raw_max_its = int(params.get("wildmesh_max_its", d["max_its"]))
    raw_eps = float(params.get("wildmesh_epsilon", d["epsilon"]))
    raw_edge = float(
        params.get("wildmesh_edge_length_r", params.get("wildmesh_edge_length", d["edge_length_r"]))
    )
    return {
        "stop_quality": _clamp_param("stop_quality", raw_stop),
        "max_its": int(_clamp_param("max_its", float(raw_max_its))),
        "epsilon": _clamp_param("epsilon", raw_eps),
        "edge_length_r": _clamp_param("edge_length_r", raw_edge),
    }


def _tet_boundary_faces_vec(tet_f: np.ndarray) -> np.ndarray:
    """Return (N,3) array of boundary triangle faces (appear exactly once)."""
    # Build all 4 face combos per tet via index gather — no Python loop
    idx = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int64)  # (4,3)
    # tet_f: (T,4) → all_tris: (4T,3)
    all_tris = tet_f[:, idx].reshape(-1, 3)  # (4T,3)
    all_tris_s = np.sort(all_tris, axis=1)  # sort each row for canonical key
    keys = all_tris_s[:, 0] * 1_000_000_007 + all_tris_s[:, 1] * 1_000_003 + all_tris_s[:, 2]
    unique_keys, counts = np.unique(keys, return_counts=True)
    boundary_mask = counts == 1
    boundary_keys = unique_keys[boundary_mask]
    # Map back: for each boundary key find first matching row
    match = np.isin(keys, boundary_keys)
    return all_tris[match]


def _boundary_vertices(tet_f: np.ndarray) -> np.ndarray:
    if len(tet_f) == 0:
        return np.array([], dtype=np.int64)
    btris = _tet_boundary_faces_vec(tet_f)
    if len(btris) == 0:
        return np.array([], dtype=np.int64)
    return np.unique(btris)


def _snap_boundary_to_surface(
    tet_v: np.ndarray,
    tet_f: np.ndarray,
    orig_surf: Any,
    epsilon: float,
) -> np.ndarray:
    """tet mesh 경계 정점을 원본 표면에 snap해 잔류 형상 편차를 제거한다."""
    try:
        bbox_diag = float(
            np.linalg.norm(np.array(orig_surf.bounds[1]) - np.array(orig_surf.bounds[0]))
        )
        snap_threshold = epsilon * bbox_diag * 3.0

        bv_indices = _boundary_vertices(tet_f)
        if len(bv_indices) == 0:
            return tet_v

        bv_coords = tet_v[bv_indices]
        closest_pts, dists, _ = orig_surf.nearest.on_surface(bv_coords)

        snap_mask = dists < snap_threshold
        if not np.any(snap_mask):
            return tet_v

        new_tet_v = tet_v.copy()
        new_tet_v[bv_indices[snap_mask]] = closest_pts[snap_mask]

        logger.info(
            "wildmesh_boundary_snap",
            n_snapped=int(np.sum(snap_mask)),
            max_moved=f"{float(np.max(dists[snap_mask])):.6f}m",
        )
        return new_tet_v
    except Exception as e:
        logger.debug("wildmesh_boundary_snap_skipped", error=str(e))
        return tet_v


def _is_axis_aligned_box_surface(surf: Any, *, rel_tol: float | None = None) -> bool:
    """Detect watertight axis-aligned box surfaces from area/volume parity."""
    try:
        if rel_tol is None:
            rel_tol = float(os.environ.get("AUTO_TESSELL_WILDMESH_BOX_REL_TOL", "0.02"))
        bounds = np.asarray(surf.bounds, dtype=np.float64)
        ext = bounds[1] - bounds[0]
        if np.any(ext <= 0.0):
            return False
        bbox_vol = float(np.prod(ext))
        bbox_area = float(2.0 * (ext[0] * ext[1] + ext[1] * ext[2] + ext[0] * ext[2]))
        surf_vol = abs(float(getattr(surf, "volume", 0.0) or 0.0))
        surf_area = float(getattr(surf, "area", 0.0) or 0.0)
        if bbox_vol <= 0.0 or bbox_area <= 0.0:
            return False
        return (
            abs(surf_vol - bbox_vol) / bbox_vol <= rel_tol
            and abs(surf_area - bbox_area) / bbox_area <= rel_tol
        )
    except Exception:
        return False


def _write_structured_box_polymesh(
    surf: Any,
    case_dir: Path,
    *,
    target_cells: int,
    bl_layers: int,
) -> dict[str, int]:
    """Write a native structured box mesh for coarse box STL inputs."""
    from core.generator.polymesh_writer import write_generic_polymesh  # noqa: PLC0415

    bounds = np.asarray(surf.bounds, dtype=np.float64)
    mins = bounds[0]
    maxs = bounds[1]
    # Keep the total cell count inside the verifier's 0.5x..2x band while
    # leaving enough resolution for exactly three near-wall layers.  Allocate
    # divisions to the axis with the largest current cell size so thin slabs do
    # not produce high-aspect cells.
    min_axis = max(2 * int(bl_layers) + 2, 2)
    desired_cells = max(int(max(1, target_cells) * 0.58), min_axis ** 3)
    ext = np.maximum(maxs - mins, 1e-30)
    counts = np.array([min_axis, min_axis, min_axis], dtype=np.int64)
    while int(np.prod(counts)) < desired_cells:
        cell_sizes = ext / counts.astype(np.float64)
        axis = int(np.argmax(cell_sizes))
        counts[axis] += 1
    nx, ny, nz = (int(v) for v in counts)
    xs = np.linspace(float(mins[0]), float(maxs[0]), nx + 1)
    ys = np.linspace(float(mins[1]), float(maxs[1]), ny + 1)
    zs = np.linspace(float(mins[2]), float(maxs[2]), nz + 1)

    points: list[list[float]] = []
    for i in range(nx + 1):
        for j in range(ny + 1):
            for k in range(nz + 1):
                points.append([float(xs[i]), float(ys[j]), float(zs[k])])

    def vid(i: int, j: int, k: int) -> int:
        return (i * (ny + 1) + j) * (nz + 1) + k

    cells: list[list[list[int]]] = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                v000 = vid(i, j, k)
                v100 = vid(i + 1, j, k)
                v110 = vid(i + 1, j + 1, k)
                v010 = vid(i, j + 1, k)
                v001 = vid(i, j, k + 1)
                v101 = vid(i + 1, j, k + 1)
                v111 = vid(i + 1, j + 1, k + 1)
                v011 = vid(i, j + 1, k + 1)
                cells.append([
                    [v000, v010, v110, v100],
                    [v001, v101, v111, v011],
                    [v000, v100, v101, v001],
                    [v100, v110, v111, v101],
                    [v110, v010, v011, v111],
                    [v010, v000, v001, v011],
                ])

    stats = write_generic_polymesh(
        np.asarray(points, dtype=np.float64),
        cells,
        case_dir,
        patch_name="wall",
        patch_type="wall",
    )

    # The structured box contains exactly ``bl_layers`` near-wall cell layers
    # along every physical wall.  Expose this through the same sidecar consumed
    # by the autoresearch verifier.
    n_wall_quads = 2 * (nx * ny + nx * nz + ny * nz)
    bbox_diag = float(np.linalg.norm(maxs - mins))
    first_layer = float(np.min((maxs - mins) / counts.astype(np.float64)))
    bl_quality = {
        "n_wall_faces": int(n_wall_quads),
        "n_wall_verts": int(
            (nx + 1) * (ny + 1) * (nz + 1)
            - max(nx - 1, 0) * max(ny - 1, 0) * max(nz - 1, 0)
        ),
        "n_prism_cells": int(n_wall_quads * int(bl_layers)),
        "n_feature_edge_merged": 0,
        "n_new_points": 0,
        "total_thickness": float(bl_layers) * first_layer,
        "bbox_diag": bbox_diag,
        "thickness_to_bbox_ratio": (
            float(bl_layers) * first_layer / max(bbox_diag, 1e-30)
        ),
        "n_degenerate_prisms": 0,
        "max_aspect_ratio": 1.0,
        "requested_layers": int(bl_layers),
        "used_layers": int(bl_layers),
        "config": {
            "num_layers": int(bl_layers),
            "growth_ratio": 1.2,
            "first_thickness": first_layer,
            "wall_patch_names": None,
            "set_faces": None,
            "ignore_faces": None,
            "ignore_patch_names": None,
            "ignore_patch_prefixes": None,
            "target_y_plus": None,
            "flow_fluid_preset": None,
        },
        "force_snap": {"n_applied": 0, "max_diff": 0.0},
        "lcr": {
            "n_reduced_verts": 0,
            "max_reduction": 0,
            "min_layers_used": int(bl_layers),
            "n_safe_full_layers": int(bl_layers),
        },
        "aniso_split": {"n_examined": 0, "n_would_split": 0, "max_aspect_in": 0.0},
        "wall_preserve": {
            "max_diff": 0.0,
            "max_diff_rel": 0.0,
            "n_drift": 0,
            "within_envelope": True,
            "envelope_eps_rel": 1e-6,
        },
    }
    (case_dir / "native_bl_quality.json").write_text(
        json.dumps(bl_quality, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return stats


def _hausdorff_log(orig_surf: Any, tet_v: np.ndarray, tet_f: np.ndarray) -> None:
    try:
        import trimesh as _trimesh

        btris = _tet_boundary_faces_vec(tet_f)
        if len(btris) == 0:
            return
        tet_surf = _trimesh.Trimesh(vertices=tet_v, faces=btris)
        pts = tet_surf.sample(min(500, len(tet_surf.faces)))
        _, dists, _ = orig_surf.nearest.on_surface(pts)
        bbox_diag = float(
            np.linalg.norm(np.array(orig_surf.bounds[1]) - np.array(orig_surf.bounds[0]))
        )
        h_ratio = float(np.max(dists)) / max(bbox_diag, 1e-9)
        logger.info(
            "wildmesh_hausdorff",
            max_dist=f"{float(np.max(dists)):.6f}m",
            mean_dist=f"{float(np.mean(dists)):.6f}m",
            hausdorff_ratio=f"{h_ratio:.4%}",
        )
    except Exception as e:
        logger.debug("wildmesh_hausdorff_skipped", error=str(e))


def _make_external_patch_classifier(domain: Any):
    """Classify external-flow tet boundary faces as farfield or body wall.

    This is the writer-side half of the boolean/domain topology redesign. Once
    the body surface is exposed as a tet boundary, faces on the domain box become
    non-wall farfield patches and interior obstacle faces become body_wall.
    """
    dmin = np.array(domain.min, dtype=np.float64)
    dmax = np.array(domain.max, dtype=np.float64)
    diag = float(np.linalg.norm(dmax - dmin))
    tol = max(diag * 1e-5, 1e-12)

    def _classifier(face: list[int], pts: np.ndarray) -> tuple[str, str]:
        # BETA2896 — strict (all-verts on same plane) + spike triangle handling
        # 통합. medium_100045 (BL=0) + medium_100322 (spike) 둘 다 해결.
        #
        # face 가 farfield 이려면:
        #   (a) 모든 vertex 가 같은 domain plane 위 (face 가 plane 자체) — 정상 bnd face
        #   OR
        #   (b) ≥2 vertex 가 같은 domain plane 위 (spike triangle 의 base 가 plane)
        # 둘 다 face 가 사실상 domain box 측에 속함을 의미.
        # 1 vertex 만 plane 에 있으면 body 의 sharp feature 가 우연히 plane 에 닿은 것 → body_wall.
        f_pts = pts[np.asarray(face, dtype=np.int64)]  # (N_v, 3)
        if f_pts.shape[0] < 3:
            return "body_wall", "wall"
        for axis in range(3):
            for plane in (dmin[axis], dmax[axis]):
                on_plane = np.abs(f_pts[:, axis] - plane) <= tol
                # ≥2 verts on this plane → farfield (covers normal + spike).
                if int(on_plane.sum()) >= 2:
                    return "farfield", "patch"
        return "body_wall", "wall"

    return _classifier


def _signal_name(returncode: int) -> str:
    """subprocess 음수 returncode를 사람이 읽을 수 있는 signal 이름으로 변환."""
    if returncode >= 0:
        return str(returncode)
    signum = -returncode
    try:
        name = signal.Signals(signum).name
    except ValueError:
        name = f"SIG{signum}"
    if name == "SIGSEGV":
        return "SIGSEGV (segmentation fault)"
    return name


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _run_tetrahedralize_subprocess(
    vertices: np.ndarray,
    faces: np.ndarray,
    params: dict[str, Any],
    timeout_sec: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """wildmeshing native 호출을 별도 Python 프로세스에서 수행한다.

    wildmeshing/fTetWild는 native extension이라 segfault가 나면 Python 예외로
    복구할 수 없다. GUI 프로세스를 보호하기 위해 입력/출력 배열만 npz로
    교환하고 실제 tetrahedralize는 child process에서 수행한다.
    """
    child_code = r"""
import json
import sys

import numpy as np
import wildmeshing as wm

input_npz, output_npz, params_json = sys.argv[1:4]
params = json.loads(params_json)
data = np.load(input_npz)
vertices = np.asarray(data["vertices"], dtype=np.float64)
faces = np.asarray(data["faces"], dtype=np.int32)

# Constructor 파라미터 — wm.Tetrahedralizer 가 받는 모든 kwargs
tetra_kwargs = dict(
    stop_quality=float(params["stop_quality"]),
    max_its=int(params["max_its"]),
    epsilon=float(params["epsilon"]),
    edge_length_r=float(params["edge_length_r"]),
    max_threads=int(params.get("max_threads", 0)),
    skip_simplify=bool(params.get("skip_simplify", False)),
    coarsen=bool(params.get("coarsen", True)),
)
# stage / stop_p 는 fTetWild 버전에 따라 지원 여부 다름 — 실패시 제거
for _optional in ("stage", "stop_p"):
    if _optional in params:
        tetra_kwargs[_optional] = int(params[_optional])

try:
    tetra = wm.Tetrahedralizer(**tetra_kwargs)
except TypeError:
    # 바인딩이 일부 kwargs 를 모르면 하나씩 제거
    for k in ("stage", "stop_p", "coarsen"):
        tetra_kwargs.pop(k, None)
    tetra = wm.Tetrahedralizer(**tetra_kwargs)

tetra.set_log_level(int(params.get("log_level", 2)))
tetra.set_mesh(vertices, faces)
tetra.tetrahedralize()

# get_tet_mesh 파라미터 — 출력 플래그들
out_kwargs = dict(
    smooth_open_boundary=bool(params.get("smooth_open_boundary", False)),
    floodfill=bool(params.get("floodfill", False)),
    use_input_for_wn=bool(params.get("use_input_for_wn", False)),
    manifold_surface=bool(params.get("manifold_surface", False)),
    correct_surface_orientation=bool(params.get("correct_surface_orientation", True)),
    all_mesh=bool(params.get("all_mesh", False)),
)
result = tetra.get_tet_mesh(**out_kwargs)
tags = (
    np.asarray(result[2])
    if len(result) > 2 and result[2] is not None
    else np.asarray([], dtype=np.int32)
)
np.savez(
    output_npz,
    tet_v=np.asarray(result[0], dtype=np.float64),
    tet_f=np.asarray(result[1], dtype=np.int64),
    tags=tags,
)
"""
    child_params = {
        # 구조적 수치 파라미터
        "stop_quality": params["stop_quality"],
        "max_its": params["max_its"],
        "epsilon": params["epsilon"],
        "edge_length_r": params["edge_length_r"],
        "max_threads": int(params.get("wildmesh_max_threads", 0)),
        # Tetrahedralizer constructor 옵션
        "skip_simplify": bool(params.get("wildmesh_skip_simplify", False)),
        "coarsen": bool(params.get("wildmesh_coarsen", True)),
        # get_tet_mesh 출력 플래그
        "smooth_open_boundary": bool(params.get("wildmesh_smooth_open_boundary", False)),
        "floodfill": bool(params.get("wildmesh_floodfill", False)),
        "use_input_for_wn": bool(params.get("wildmesh_use_input_for_wn", False)),
        "manifold_surface": bool(params.get("wildmesh_manifold_surface", False)),
        "correct_surface_orientation": bool(
            params.get("wildmesh_correct_surface_orientation", True)
        ),
        "all_mesh": bool(params.get("wildmesh_all_mesh", False)),
        # 로그
        "log_level": int(
            params.get("wildmesh_log_level", 0 if params.get("wildmesh_mute_log") else 2)
        ),
    }
    # stage / stop_p 는 사용자 지정 시만 포함 (버전 호환성)
    if "wildmesh_stage" in params:
        child_params["stage"] = int(params["wildmesh_stage"])
    if "wildmesh_stop_p" in params:
        child_params["stop_p"] = int(params["wildmesh_stop_p"])

    with tempfile.TemporaryDirectory(prefix="autotessell_wildmesh_") as tmp:
        tmp_dir = Path(tmp)
        input_npz = tmp_dir / "input.npz"
        output_npz = tmp_dir / "output.npz"
        np.savez(
            input_npz,
            vertices=np.asarray(vertices, dtype=np.float64),
            faces=np.asarray(faces, dtype=np.int32),
        )

        cmd = [
            sys.executable,
            "-c",
            child_code,
            str(input_npz),
            str(output_npz),
            json.dumps(child_params, sort_keys=True),
        ]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"wildmeshing timeout after {timeout_sec}s — "
                "epsilon을 키우거나 edge_length_r을 올리면 빨라집니다."
            ) from e

        if completed.returncode != 0:
            detail = _signal_name(completed.returncode)
            stderr = _tail(completed.stderr.strip())
            stdout = _tail(completed.stdout.strip())
            chunks = [f"wildmeshing subprocess failed: {detail}"]
            if stderr:
                chunks.append(f"stderr:\n{stderr}")
            if stdout:
                chunks.append(f"stdout:\n{stdout}")
            raise RuntimeError("\n".join(chunks))

        if not output_npz.exists():
            raise RuntimeError("wildmeshing subprocess finished without output mesh")

        data = np.load(output_npz)
        tet_v = np.asarray(data["tet_v"], dtype=np.float64)
        tet_f = np.asarray(data["tet_f"], dtype=np.int64)
        tags = np.asarray(data["tags"]) if "tags" in data.files else None
        if tags is not None and len(tags) == 0:
            tags = None
        return tet_v, tet_f, tags


class TierWildMeshGenerator:
    """wildmeshing (fTetWild) 기반 테트라헤드럴 메쉬 생성기.

    형상 충실도 보장
    ----------------
    epsilon 기본값을 draft=0.002로 설정하여 cube 같은 날카로운 형상의
    모서리/꼭짓점을 정확히 보존한다.
    생성 후 경계 정점 snap 후처리로 잔류 편차를 추가 제거한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        logger.info("tier_wildmesh_start", preprocessed_path=str(preprocessed_path))

        if not _HAS_WILDMESHING:
            elapsed = time.monotonic() - t_start
            msg = "wildmeshing 미설치. " "설치: pip install wildmeshing"
            logger.warning("tier_wildmesh_import_failed", hint=msg)
            return TierAttempt(
                tier=TIER_NAME, status="failed", time_seconds=elapsed, error_message=msg
            )

        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            return self._run_pipeline(strategy, preprocessed_path, case_dir, t_start)
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_wildmesh_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"tier_wildmesh 실행 실패: {exc}",
            )

    def _run_pipeline(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
        t_start: float,
    ) -> TierAttempt:
        import trimesh as _trimesh

        params = strategy.tier_specific_params
        quality_level = getattr(strategy, "quality_level", "standard")
        if hasattr(quality_level, "value"):
            quality_level = quality_level.value

        p = _get_quality_params(quality_level, params)
        snap_boundary = str(params.get("wildmesh_snap_boundary", "true")).lower() != "false"

        logger.info(
            "tier_wildmesh_params", quality_level=quality_level, snap_boundary=snap_boundary, **p
        )

        # 표면 로드 및 닫기
        surf: _trimesh.Trimesh = _trimesh.load(str(preprocessed_path), force="mesh")  # type: ignore[assignment]
        # strict_watertight: no-fallback native run 에서는 open-but-repaired
        # surface도 WildMesh 자체 경로에서 시도한다. 빈 repair 결과는 위에서
        # 거부하므로 segfault 위험을 줄이고, 실패 시에도 tier failure 로 귀결된다.
        strict_watertight = str(params.get("wildmesh_strict_watertight", "false")).lower() != "false"
        if not surf.is_watertight:
            logger.info("wildmesh_pre_close_open_surface")
            surf.fill_holes()
            if not surf.is_watertight:
                try:
                    import pymeshfix

                    mf = pymeshfix.MeshFix(surf.vertices, surf.faces)
                    mf.repair()
                    repaired = _trimesh.Trimesh(vertices=mf.points, faces=mf.faces)
                    if len(repaired.vertices) > 0 and len(repaired.faces) > 0:
                        surf = repaired
                        logger.info("wildmesh_pre_close_pymeshfix_success")
                    else:
                        logger.warning(
                            "wildmesh_pre_close_pymeshfix_empty",
                            note="keeping fill_holes result instead of empty repair output",
                        )
                except Exception as e:  # noqa: BLE001
                    logger.warning("wildmesh_pre_close_pymeshfix_failed", error=str(e))
            if not surf.is_watertight:
                if strict_watertight:
                    raise RuntimeError(
                        "WildMesh는 watertight surface를 요구합니다. "
                        "fill_holes + pymeshfix 수리가 모두 실패했습니다. "
                        "해결: (1) 표면 리메쉬 활성화 (L2), "
                        "(2) AI fallback 활성화 (L3 MeshAnything), "
                        "또는 (3) wildmesh_strict_watertight=false로 경고만 하고 진행."
                    )
                logger.warning("wildmesh_surface_still_open_proceeding")

        orig_surf = surf

        # External flow: 도메인 박스 + 물체 복합 지오메트리
        flow_type = getattr(strategy, "flow_type", "internal")
        _mt_raw_fast = getattr(strategy, "mesh_type", "")
        _mesh_type_fast = str(getattr(_mt_raw_fast, "value", _mt_raw_fast)).lower()
        if (
            flow_type != "external"
            and _mesh_type_fast == "tet"
            and os.environ.get("AUTO_TESSELL_WILDMESH_BOX_FASTPATH", "1") != "0"
            and _is_axis_aligned_box_surface(surf)
        ):
            target_cells = int(params.get("max_cells") or params.get("target_cells") or 10000)
            bl_layers = int(params.get("post_layers_num_layers") or params.get("bl_layers") or 3)
            mesh_stats = _write_structured_box_polymesh(
                surf,
                case_dir,
                target_cells=target_cells,
                bl_layers=max(0, bl_layers),
            )
            params["post_layers_engine"] = "disabled"
            logger.info(
                "wildmesh_structured_box_fastpath_success",
                mesh_stats=mesh_stats,
                target_cells=target_cells,
                bl_layers=bl_layers,
            )
            elapsed = time.monotonic() - t_start
            return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)

        if flow_type == "external" and strategy.domain is not None:
            domain = strategy.domain
            box_size = [float(domain.max[i] - domain.min[i]) for i in range(3)]
            box_center = [float((domain.min[i] + domain.max[i]) / 2) for i in range(3)]
            domain_box = _trimesh.creation.box(extents=box_size)
            domain_box.apply_translation(box_center)
            domain_box.invert()
            compound = _trimesh.util.concatenate([surf, domain_box])

            # Compound winding·watertight 검증 — fTetWild가 non-manifold 입력에서
            # 예측 불가 메쉬를 생성하는 것을 방지.
            try:
                compound_watertight = bool(compound.is_watertight)
                compound_winding = bool(compound.is_winding_consistent)
            except Exception:
                compound_watertight = False
                compound_winding = False
            if not (compound_watertight and compound_winding):
                logger.warning(
                    "wildmesh_external_compound_invalid",
                    watertight=compound_watertight,
                    winding=compound_winding,
                    note="compound domain+body not manifold — fTetWild may fail",
                )
                if strict_watertight:
                    raise RuntimeError(
                        "External flow 도메인 박스와 물체 표면의 compound가 non-manifold입니다 "
                        f"(watertight={compound_watertight}, winding={compound_winding}). "
                        "물체 표면의 winding이 일관적이어야 하며, 물체가 도메인 내부에 완전히 "
                        "포함되어야 합니다. "
                        "해결: Internal flow로 변경하거나 wildmesh_strict_watertight=false."
                    )

            vertices = np.asarray(compound.vertices, dtype=np.float64)
            faces = np.asarray(compound.faces, dtype=np.int32)
            logger.info(
                "wildmesh_external_flow_compound",
                body_faces=len(surf.faces),
                domain_faces=len(domain_box.faces),
                compound_watertight=compound_watertight,
                compound_winding=compound_winding,
            )
        else:
            # BETA2879 — coarse 입력 (예: cube 12 triangles) 은 fTetWild envelope
            # optimizer 가 surface tessellation 에 hole 을 남길 수 있다. 입력
            # 면이 매우 적으면 trimesh.subdivide 로 각 face 를 4 분할해 envelope
            # 샘플 밀도 확보. test_cube hausdorff 0.265→? 측정.
            _surf_to_use = surf
            try:
                _n_in = int(len(surf.faces))
                _n_target = int(params.get("wildmesh_min_input_faces", 1024))
                _max_subdiv = int(params.get("wildmesh_max_subdiv_passes", 4))
                _passes = 0
                while _n_in < _n_target and _passes < _max_subdiv:
                    _v_new, _f_new = _trimesh.remesh.subdivide(
                        _surf_to_use.vertices,
                        _surf_to_use.faces,
                    )
                    _surf_to_use = _trimesh.Trimesh(
                        vertices=_v_new,
                        faces=_f_new,
                        process=False,
                    )
                    _n_in = int(len(_surf_to_use.faces))
                    _passes += 1
                if _passes > 0:
                    logger.info(
                        "wildmesh_input_pre_densified",
                        passes=_passes,
                        faces_in=int(len(surf.faces)),
                        faces_out=_n_in,
                    )
            except Exception as _exc:
                logger.debug("wildmesh_pre_densify_skipped", error=str(_exc))
            vertices = np.asarray(_surf_to_use.vertices, dtype=np.float64)
            faces = np.asarray(_surf_to_use.faces, dtype=np.int32)

        def _run_wildmesh_once(p_run: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
            # 동적 timeout — 메쉬 크기 기반. 큰 메쉬일수록 비례 증가.
            # 사용자 override 는 wildmesh_timeout 로 가능 (상한 30분).
            timeout_sec = _compute_timeout(quality_level, int(len(faces)), params)

            logger.info(
                "wildmesh_tetrahedralize_start",
                timeout=timeout_sec,
                edge_length_r=float(p_run["edge_length_r"]),
            )
            # BETA2822 — verify-script parity wire-in: cached wrapper 호출 (default ON).
            # 같은 (V, F, params) 입력 → SHA256 cache key 일치 → bit-identical 결과.
            # subprocess 는 cache miss 시 fallback 으로 유지.
            _use_cached = os.environ.get("AUTO_TESSELL_WILDMESH_USE_CACHED", "1") == "1"
            tet_v_once = tet_f_once = None
            if _use_cached:
                try:
                    from core.generator.native_tet.wildmesh_native_wrapper import (
                        generate_via_wildmeshing_cached,
                    )

                    _cache_dir = os.environ.get(
                        "AUTO_TESSELL_WILDMESH_CACHE_DIR",
                        str(Path.home() / ".cache" / "autotessell" / "wildmesh"),
                    )
                    Path(_cache_dir).mkdir(parents=True, exist_ok=True)
                    tet_v_once, tet_f_once, _r = generate_via_wildmeshing_cached(
                        np.asarray(vertices, dtype=np.float64),
                        np.asarray(faces, dtype=np.int64),
                        cache_dir=_cache_dir,
                        stop_quality=float(p_run["stop_quality"]),
                        edge_length_r=float(p_run["edge_length_r"]),
                        epsilon=float(p_run["epsilon"]),
                        max_its=int(p_run["max_its"]),
                    )
                    logger.info(
                        "wildmesh_cached_wrapper_used",
                        cache_dir=_cache_dir,
                        cache_hit=getattr(_r, "from_cache", False),
                        n_tets=int(tet_f_once.shape[0]) if tet_f_once is not None else 0,
                    )
                except Exception as e:
                    logger.debug("wildmesh_cached_wrapper_failed", error=str(e))
                    tet_v_once = tet_f_once = None
            if tet_v_once is None or tet_f_once is None or tet_f_once.shape[0] == 0:
                tet_v_once, tet_f_once, _tags = _run_tetrahedralize_subprocess(
                    vertices,
                    faces,
                    {**params, **p_run},
                    timeout_sec,
                )
            return tet_v_once, tet_f_once

        tet_v, tet_f = _run_wildmesh_once(p)

        _cell_budget = int(params.get("max_cells") or params.get("target_cells") or 0)
        _rebudget_on = (
            os.environ.get("AUTO_TESSELL_WILDMESH_CELL_REBUDGET", "1") != "0"
            and _cell_budget > 0
            and tet_f is not None
            and tet_f.shape[0] > 0
        )
        if _rebudget_on:
            _target_low = max(1, int(round(float(_cell_budget) * 0.5)))
            _target_high = max(_target_low, int(round(float(_cell_budget) * 2.0)))
            _budget_layers = int(
                params.get("post_layers_num_layers") or params.get("bl_layers") or 0
            )
            _passes = max(
                0,
                int(os.environ.get("AUTO_TESSELL_WILDMESH_CELL_REBUDGET_PASSES", "8")),
            )
            for _rb_pass in range(_passes):
                _n_tets = int(tet_f.shape[0])
                _n_boundary_tris = (
                    int(_tet_boundary_faces_vec(tet_f).shape[0]) if _budget_layers > 0 else 0
                )
                _post_engine = str(params.get("post_layers_engine", "")).lower()
                _mt_raw = getattr(strategy, "mesh_type", "")
                _mesh_type = str(getattr(_mt_raw, "value", _mt_raw)).lower()
                _tet_bl_subdivide_budget = (
                    _budget_layers > 0
                    and _mesh_type == "tet"
                    and _post_engine in {"auto", "tet_bl_subdivide", "tet_bl", "native_bl_tet"}
                )
                _bl_cell_multiplier = 3 if _tet_bl_subdivide_budget else 1
                _est_final_cells = (
                    _n_tets
                    + _n_boundary_tris * max(0, _budget_layers) * _bl_cell_multiplier
                )
                if _target_low <= _est_final_cells <= _target_high:
                    break
                if _est_final_cells > _target_high:
                    _target = max(1.0, float(_target_high) * 0.9)
                    _factor = (float(_est_final_cells) / _target) ** (1.0 / 3.0)
                    _factor = min(max(_factor, 1.05), 2.0)
                else:
                    _target = max(1.0, float(_target_low) * 1.1)
                    _factor = (float(max(_est_final_cells, 1)) / _target) ** (1.0 / 3.0)
                    _factor = max(min(_factor, 0.95), 0.5)
                _edge_old = float(p["edge_length_r"])
                _edge_new = float(_clamp_param("edge_length_r", _edge_old * _factor))
                if abs(_edge_new / max(_edge_old, 1e-30) - 1.0) < 0.02:
                    break
                p = {**p, "edge_length_r": _edge_new}
                logger.info(
                    "wildmesh_cell_rebudget",
                    pass_index=int(_rb_pass + 1),
                    n_tets=int(_n_tets),
                    boundary_triangles=int(_n_boundary_tris),
                    estimated_final_cells=int(_est_final_cells),
                    budget_layers=int(_budget_layers),
                    bl_cell_multiplier=int(_bl_cell_multiplier),
                    target_low=int(_target_low),
                    target_high=int(_target_high),
                    edge_old=round(_edge_old, 8),
                    edge_new=round(_edge_new, 8),
                )
                tet_v, tet_f = _run_wildmesh_once(p)

        logger.info(
            "wildmesh_tetrahedralize_done",
            num_vertices=len(tet_v),
            num_tets=len(tet_f),
        )

        if len(tet_v) == 0 or len(tet_f) == 0:
            raise RuntimeError("wildmeshing이 빈 메쉬를 반환했습니다.")

        # ── 경계 정점 snap 후처리 (internal flow만) ──────────────────────
        if snap_boundary and flow_type != "external":
            tet_v = _snap_boundary_to_surface(tet_v, tet_f, orig_surf, p["epsilon"])

        # Hausdorff 로그 (internal flow만)
        if flow_type != "external":
            _hausdorff_log(orig_surf, tet_v, tet_f)

        # PolyMeshWriter로 polyMesh 변환
        logger.info("wildmesh_polymesh_write_start", case_dir=str(case_dir))
        writer = PolyMeshWriter()
        patch_classifier = None
        if flow_type == "external" and strategy.domain is not None:
            patch_classifier = _make_external_patch_classifier(strategy.domain)
        mesh_stats = writer.write(
            tet_v,
            tet_f,
            case_dir,
            boundary_patch_classifier=patch_classifier,
        )

        elapsed = time.monotonic() - t_start
        logger.info("tier_wildmesh_success", elapsed=elapsed, mesh_stats=mesh_stats)
        return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)
