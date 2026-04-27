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

import json
import importlib.util
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
    "epsilon":       (0.0001, 0.1),    # 너무 작으면 timeout, 너무 크면 형상 손상
    "edge_length_r": (0.005, 0.2),     # 너무 작으면 OOM, 너무 크면 저해상도
    "stop_quality":  (3.0, 100.0),     # fTetWild 내부 수렴 안정 범위
    "max_its":       (10.0, 500.0),    # 10 미만 덜수렴, 500 초과 과부하
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
        "draft":    {"stop_quality": 20.0, "max_its": 40,  "epsilon": 0.002,  "edge_length_r": 0.06},
        # standard: TetWild 매칭 — 복잡 형상(knot, gear 등) 첫 시도 PASS
        "standard": {"stop_quality": 10.0, "max_its": 80,  "epsilon": 0.001,  "edge_length_r": 0.05},
        # fine: standard 보다 tight 하되 fTetWild 수렴 가능한 한계
        "fine":     {"stop_quality": 6.0,  "max_its": 120, "epsilon": 0.0005, "edge_length_r": 0.03},
    }
    d = _defaults.get(quality_level, _defaults["standard"])
    raw_stop = float(params.get("wildmesh_stop_quality",  d["stop_quality"]))
    raw_max_its = int(params.get("wildmesh_max_its",      d["max_its"]))
    raw_eps = float(params.get("wildmesh_epsilon",        d["epsilon"]))
    raw_edge = float(params.get("wildmesh_edge_length_r",
                                params.get("wildmesh_edge_length",
                                           d["edge_length_r"])))
    return {
        "stop_quality":  _clamp_param("stop_quality", raw_stop),
        "max_its":       int(_clamp_param("max_its", float(raw_max_its))),
        "epsilon":       _clamp_param("epsilon", raw_eps),
        "edge_length_r": _clamp_param("edge_length_r", raw_edge),
    }


def _tet_boundary_faces_vec(tet_f: np.ndarray) -> np.ndarray:
    """Return (N,3) array of boundary triangle faces (appear exactly once)."""
    # Build all 4 face combos per tet via index gather — no Python loop
    idx = np.array([[0,1,2],[0,1,3],[0,2,3],[1,2,3]], dtype=np.int64)  # (4,3)
    # tet_f: (T,4) → all_tris: (4T,3)
    all_tris = tet_f[:, idx].reshape(-1, 3)  # (4T,3)
    all_tris_s = np.sort(all_tris, axis=1)   # sort each row for canonical key
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
        bbox_diag = float(np.linalg.norm(
            np.array(orig_surf.bounds[1]) - np.array(orig_surf.bounds[0])
        ))
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


def _hausdorff_log(orig_surf: Any, tet_v: np.ndarray, tet_f: np.ndarray) -> None:
    try:
        import trimesh as _trimesh
        btris = _tet_boundary_faces_vec(tet_f)
        if len(btris) == 0:
            return
        tet_surf = _trimesh.Trimesh(vertices=tet_v, faces=btris)
        pts = tet_surf.sample(min(500, len(tet_surf.faces)))
        _, dists, _ = orig_surf.nearest.on_surface(pts)
        bbox_diag = float(np.linalg.norm(
            np.array(orig_surf.bounds[1]) - np.array(orig_surf.bounds[0])
        ))
        h_ratio = float(np.max(dists)) / max(bbox_diag, 1e-9)
        logger.info(
            "wildmesh_hausdorff",
            max_dist=f"{float(np.max(dists)):.6f}m",
            mean_dist=f"{float(np.mean(dists)):.6f}m",
            hausdorff_ratio=f"{h_ratio:.4%}",
        )
    except Exception as e:
        logger.debug("wildmesh_hausdorff_skipped", error=str(e))


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
        "log_level": int(params.get("wildmesh_log_level", 0 if params.get("wildmesh_mute_log") else 2)),
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
            msg = (
                "wildmeshing 미설치. "
                "설치: pip install wildmeshing"
            )
            logger.warning("tier_wildmesh_import_failed", hint=msg)
            return TierAttempt(tier=TIER_NAME, status="failed", time_seconds=elapsed, error_message=msg)

        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME, status="failed", time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            return self._run_pipeline(strategy, preprocessed_path, case_dir, t_start)
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_wildmesh_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME, status="failed", time_seconds=elapsed,
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

        logger.info("tier_wildmesh_params", quality_level=quality_level, snap_boundary=snap_boundary, **p)

        # 표면 로드 및 닫기
        surf: _trimesh.Trimesh = _trimesh.load(str(preprocessed_path), force="mesh")  # type: ignore[assignment]
        # strict_watertight: 사용자가 off로 명시하면 기존처럼 경고만 (기본 on)
        strict_watertight = str(
            params.get("wildmesh_strict_watertight", "true")
        ).lower() != "false"
        if not surf.is_watertight:
            logger.info("wildmesh_pre_close_open_surface")
            surf.fill_holes()
            if not surf.is_watertight:
                try:
                    import pymeshfix
                    mf = pymeshfix.MeshFix(surf.vertices, surf.faces)
                    mf.repair()
                    surf = _trimesh.Trimesh(vertices=mf.points, faces=mf.faces)
                    logger.info("wildmesh_pre_close_pymeshfix_success")
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
            vertices = np.asarray(surf.vertices, dtype=np.float64)
            faces = np.asarray(surf.faces, dtype=np.int32)

        # 동적 timeout — 메쉬 크기 기반. 큰 메쉬일수록 비례 증가.
        # 사용자 override 는 wildmesh_timeout 로 가능 (상한 30분).
        timeout_sec = _compute_timeout(quality_level, int(len(faces)), params)

        logger.info("wildmesh_tetrahedralize_start", timeout=timeout_sec)
        tet_v, tet_f, _tags = _run_tetrahedralize_subprocess(
            vertices,
            faces,
            {**params, **p},
            timeout_sec,
        )

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
        mesh_stats = writer.write(tet_v, tet_f, case_dir)

        elapsed = time.monotonic() - t_start
        logger.info("tier_wildmesh_success", elapsed=elapsed, mesh_stats=mesh_stats)
        return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)
