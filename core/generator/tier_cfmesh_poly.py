"""Tier cfMesh pMesh — vendored cfMesh pMesh exe wrapper for mesh_type=poly.

Primary backend for polyhedral mesh generation. Calls
auto_tessell_core/build/cfmesh_native.so which runs
third_party/cfmesh/build/pMesh on a prepared OpenFOAM case.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from core.generator.openfoam_writer import OpenFOAMWriter
from core.generator.tier15_cfmesh import _hex_repair_surface  # noqa: F401
from core.schemas import GeneratorStep, MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_cfmesh_poly"


def _import_vendored():
    import sys
    build_dir = Path(__file__).resolve().parents[2] / "auto_tessell_core" / "build"
    if str(build_dir) not in sys.path:
        sys.path.insert(0, str(build_dir))
    import cfmesh_native  # type: ignore
    return cfmesh_native


class CfMeshPolyGenerator:
    def __init__(self) -> None:
        self._writer = OpenFOAMWriter()

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path | None = None,
        case_dir: Path | None = None,
        **_kwargs,
    ) -> TierAttempt:
        t_start = time.monotonic()
        try:
            cfm = _import_vendored()
        except Exception as exc:
            if os.environ.get("AUTO_TESSELL_POLY_CFMESH_IMPORT_FALLBACK", "1") != "0":
                logger.warning(
                    "poly_cfmesh_native_import_failed_try_native_poly",
                    error=str(exc),
                )
                try:
                    from core.generator.tier_native_poly import (  # noqa: PLC0415
                        TierNativePolyGenerator,
                    )

                    fallback_case_dir = case_dir if case_dir is not None else Path("./case")
                    fallback = TierNativePolyGenerator().run(
                        strategy,
                        preprocessed_path=preprocessed_path,
                        case_dir=fallback_case_dir,
                    )
                    fallback.steps.insert(
                        0,
                        GeneratorStep(
                            name="import_cfmesh_native",
                            status="failed",
                            time=0.0,
                        ),
                    )
                    if fallback.status == "success":
                        return fallback
                    logger.warning(
                        "poly_cfmesh_native_fallback_failed",
                        error=fallback.error_message,
                    )
                except Exception as fallback_exc:  # noqa: BLE001
                    logger.warning(
                        "poly_cfmesh_native_fallback_exception",
                        error=str(fallback_exc),
                    )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=time.monotonic() - t_start,
                steps=[GeneratorStep(name="import_cfmesh_native", status="failed", time=0.0)],
                error_message=f"cfmesh_native import 실패: {exc}",
            )

        if case_dir is None:
            case_dir = Path("./case")
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "constant" / "triSurface").mkdir(parents=True, exist_ok=True)

        stl_path = (
            preprocessed_path if preprocessed_path is not None
            else (strategy.surface_mesh.path if strategy.surface_mesh else None)
        )
        if stl_path is None or not Path(stl_path).exists():
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=time.monotonic() - t_start,
                error_message="surface_mesh.path 없음",
            )

        # P-1 (autoresearch-deep poly loop, 2026-05-12) — WildMesh-style
        # STL repair before cfMesh pMesh.  Many broken multi-shell STLs
        # cause pMesh to segfault during BL detection; running
        # trimesh.fill_holes + pymeshfix.MeshFix.repair (same recipe as
        # tier15_cfmesh H-10) on the input STL converts them to closed
        # single-body surfaces that pMesh can mesh.
        if os.environ.get(
            "AUTO_TESSELL_POLY_CFMESH_REPAIR_SURFACE", "1",
        ) == "1":
            try:
                _hex_repair_surface(Path(stl_path))
            except Exception as _exc:
                logger.warning(
                    "poly_cfmesh_repair_surface_failed",
                    error=str(_exc)[:120],
                )

        params = strategy.tier_specific_params or {}
        sm = strategy.surface_mesh
        bl = getattr(strategy, "boundary_layers", None)
        # BETA2869 — max_cell = target*4 (draft coarseness). sparse refinement
        # 은 min_cell + boundary_cell 로 처리.
        _target = float(getattr(sm, "target_cell_size", 0.0) or 0.0) if sm else 0.0
        max_cell = float(params.get(
            "cfmesh_max_cell_size",
            _target * 4 if _target > 0 else 0.2,
        ))
        # P-2 (autoresearch-deep poly loop, 2026-05-12) — target_cells
        # aware maxCellSize remap (mirror tier15_cfmesh H-1+H-2).
        # cfMesh default max=target_cell_size*4 gives ≪ target cells on
        # broken-input STLs; remap to (domain_vol / target_cells)^(1/3) *
        # calib (default 0.85) to push toward target.
        _target_cells = int(params.get("target_cells", 0) or 0)
        if _target_cells > 0 and not params.get("cfmesh_max_cell_size"):
            try:
                _dom = getattr(strategy, "domain", None)
                _dmin = list(getattr(_dom, "min", []) or [])
                _dmax = list(getattr(_dom, "max", []) or [])
                if len(_dmin) == 3 and len(_dmax) == 3:
                    _dvol = max(
                        (_dmax[0] - _dmin[0])
                        * (_dmax[1] - _dmin[1])
                        * (_dmax[2] - _dmin[2]),
                        1e-30,
                    )
                    # pMesh produces ~2× cells/vol than cartesianMesh
                    # because polyhedral merging adds intermediate
                    # surface cells.  CALIB=1.4 (was 0.85, hex value)
                    # compensates: test_cube 122k → ~10k cells.
                    _calib = float(os.environ.get(
                        "AUTO_TESSELL_POLY_CFMESH_TARGET_CALIB",
                        "1.4",
                    ))
                    _max_from_target = (
                        (_dvol / _target_cells) ** (1.0 / 3.0)
                    ) * _calib
                    # QA-fix (2026-05-13) — user reported "cell count 안먹힘"
                    # for small target_cells (e.g. 2000) because the previous
                    # guard ``_max_from_target < max_cell`` only allowed
                    # refinement, never coarsening.  When the user explicitly
                    # passes target_cells we honor it bidirectionally.
                    logger.info(
                        "cfmesh_poly_max_remap_from_target",
                        target_cells=_target_cells,
                        domain_vol=_dvol,
                        prev_max=max_cell,
                        new_max=_max_from_target,
                    )
                    max_cell = _max_from_target
            except Exception as _exc:
                logger.debug(
                    "cfmesh_poly_remap_skipped", error=str(_exc)[:120],
                )
        # BETA2876 — poly 는 polyhedral 변환에서 surface refinement 가 없으면
        # corner / sharp feature 가 뭉개진다 (사용자 QA: "원래 형상을 보존하지 못함").
        # cfMesh octree 는 cell 을 절반씩 분할 — bnd >= max/2 면 같은 레벨 (refine
        # 없이 sizing 힌트만), bnd < max/2 면 +1 level (≈8× cells in shell).
        # default = max_cell * 0.7 → 같은 octree 레벨 유지 + boundary cell 정렬
        # 으로 corner 보존, cell 폭증 회피. (원래 0.5 default 는 cube 122k 폭증.)
        if "cfmesh_boundary_cell_size" in params:
            boundary_cell = float(params["cfmesh_boundary_cell_size"])
        else:
            boundary_cell = max_cell * 0.7
        if "cfmesh_min_cell_size" in params:
            min_cell = float(params["cfmesh_min_cell_size"])
        else:
            min_cell = boundary_cell
        n_layers = 0
        thickness_ratio = 1.2
        max_first = 0.0
        if bl and getattr(bl, "enabled", False):
            n_layers = int(getattr(bl, "num_layers", 0) or 0)
            thickness_ratio = float(getattr(bl, "growth_ratio", 1.2) or 1.2)
            max_first = float(getattr(bl, "first_layer_thickness", 0.0) or 0.0)
        # BETA2847 — GUI cfMesh BL widget override.
        if "cfmesh_bl_n_layers" in params:
            n_layers = int(params["cfmesh_bl_n_layers"])
        if "cfmesh_bl_thickness_ratio" in params:
            thickness_ratio = float(params["cfmesh_bl_thickness_ratio"])
        if "cfmesh_bl_max_first_layer" in params:
            max_first = float(params["cfmesh_bl_max_first_layer"])

        # Backend selector (default: ``tet_dual`` per user QA 2026-05-13).
        # - ``tet_dual`` (default, 2026-05-13): fTetWild tet primal →
        #   polyDualMesh.  Produces TRUE polyhedral cells: pentagon/hexagon
        #   dominant face mix (4-vert 31 %, 5-vert 40 %, 6-vert 21 %,
        #   up to 15-vert).  Matches user expectation of "다면체".
        # - ``cartesian_dual``: cartesianMesh octree primal → polyDualMesh.
        #   Mostly quad faces (95 %) due to uniform octree connectivity.
        #   Faster than tet_dual but visually hex-like.  Stable on bench.
        # - ``cfmesh_pmesh`` (legacy): vendored pMesh exe direct.
        #   Segfaults on broken multi-shell STLs (13/21 NO_QR on bench).
        _backend = os.environ.get(
            "AUTO_TESSELL_POLY_BACKEND", "tet_dual",
        ).lower()

        t_step = time.monotonic()
        if _backend == "tet_dual":
            # QA-fix (2026-05-13) — user reported "Poly 다면체를 기대했는데
            # hex-dom 같다".  cartesianMesh octree primal → polyDualMesh
            # gives mostly quad faces (95 %).  tet primal → polyDualMesh
            # yields true polyhedra: quad/pentagon/hexagon mix (test_cube:
            # 3577/2410/3399 + heptagon/octagon).
            # Trade-off: dual_cells ≈ primal_points, so target_cells must
            # be multiplied by ~6 when generating the tet primal.
            from core.generator.tier_wildmesh import TierWildMeshGenerator
            from core.utils.openfoam_utils import run_openfoam
            # Boost primal target_cells so dual ends up near user target.
            # Empirically: 1 dual cell ≈ 1 primal internal vertex, and
            # n_primal_internal_verts ≈ n_primal_cells / 6 for clean tet
            # mesh from fTetWild.  But fTetWild often overshoots target by
            # 2-3× on simple geometries; tune scale to ~1.5× by default.
            # Empirical (test_cube, target=10000):
            #   scale=1.5 → 3049 dual cells (-70 %)
            #   scale=3.0 → 5693 dual cells (-43 %, primal_s ≈ 4 s)
            #   scale=6.0 → 93658 dual cells (+836 %, primal_s ≈ 90 s)
            # Default 3.0 balances target accuracy and runtime.
            _scale = float(os.environ.get(
                "AUTO_TESSELL_POLY_TETDUAL_PRIMAL_SCALE", "3.0",
            ))
            _scaled_target = max(int(_target_cells * _scale), 1000) if _target_cells > 0 else 0
            primal_strategy = strategy
            if _scaled_target > 0:
                # mutate a copy of tier_specific_params for the tet generator
                if primal_strategy.tier_specific_params is None:
                    primal_strategy.tier_specific_params = {}
                primal_strategy.tier_specific_params = dict(primal_strategy.tier_specific_params)
                primal_strategy.tier_specific_params["target_cells"] = _scaled_target
                primal_strategy.tier_specific_params["max_cells"] = _scaled_target
                # disable fastpaths so we get pure tet primal
                primal_strategy.tier_specific_params["bl_layers"] = 0
                primal_strategy.tier_specific_params["post_layers_engine"] = "disabled"
            # Step 1: tet primal via WildMesh (fTetWild real path).
            _t_primal = time.monotonic()
            tet_gen = TierWildMeshGenerator()
            tet_attempt = tet_gen.run(primal_strategy, stl_path, case_dir)
            if tet_attempt.status != "success":
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=time.monotonic() - t_start,
                    error_message=(
                        f"tet_dual stage 1 (WildMesh tet primal) 실패: "
                        f"{tet_attempt.error_message or ''}"
                    ),
                )
            # Step 2: polyDualMesh — convert tet primal → polyhedral dual.
            try:
                self._writer.write_control_dict(case_dir, application="polyDualMesh")
                self._writer.write_fv_schemes(case_dir)
                self._writer.write_fv_solution(case_dir)
                _feat = float(params.get("bl_feature_angle", 30.0))
                _t_dual = time.monotonic()
                run_openfoam("polyDualMesh", case_dir, [str(_feat)])
                # polyDualMesh writes into 1/polyMesh (or 0/polyMesh
                # depending on the case's startTime).  Promote whichever
                # exists to constant/polyMesh.
                _to = case_dir / "constant" / "polyMesh"
                for _t in ("1", "0"):
                    _from = case_dir / _t / "polyMesh"
                    if _from.exists():
                        if _to.exists():
                            shutil.rmtree(str(_to))
                        shutil.copytree(str(_from), str(_to))
                        break
                logger.info(
                    "cfmesh_poly_tet_dual_used",
                    polymesh=str(_to),
                    feature_angle=_feat,
                    primal_target_cells=_scaled_target,
                    primal_s=round(_t_dual - _t_primal, 3),
                    dual_s=round(time.monotonic() - _t_dual, 3),
                )
            except Exception as exc:
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=time.monotonic() - t_start,
                    error_message=(
                        f"tet_dual stage 2 (polyDualMesh) 실패: "
                        f"{str(exc)[:300]}"
                    ),
                )
        elif _backend == "cartesian_dual":
            # Step 1: cartesianMesh (hex+BL volume mesh, segfault-free
            # path already proven by tier15_cfmesh H-series 21/21).
            r = cfm.cartesian_mesh(
                str(stl_path), str(case_dir),
                max_cell_size=max_cell,
                min_cell_size=min_cell,
                boundary_cell_size=boundary_cell,
                bl_n_layers=n_layers,
                bl_thickness_ratio=thickness_ratio,
                bl_max_first_layer=max_first,
                feature_angle_deg=float(params.get("bl_feature_angle", 30.0)),
                keep_cells_intersecting_boundary=True,
            )
            if not r.get("success"):
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=time.monotonic() - t_start,
                    steps=[GeneratorStep(
                        name="cfmesh_cartesianMesh",
                        status="failed",
                        time=time.monotonic() - t_step,
                    )],
                    error_message=(
                        "cartesian_dual stage 1 (cartesianMesh) 실패: "
                        + (r.get("log", "")[-300:])
                    ),
                )
            # Step 2: polyDualMesh (OpenFOAM utility) — hex→poly dual.
            try:
                from core.utils.openfoam_utils import run_openfoam
                # polyDualMesh requires system/fvSchemes + fvSolution;
                # cfmesh_native cartesian_mesh doesn't write them.
                self._writer.write_control_dict(case_dir, application="polyDualMesh")
                self._writer.write_fv_schemes(case_dir)
                self._writer.write_fv_solution(case_dir)
                _feat = float(params.get("bl_feature_angle", 30.0))
                _step2_t = time.monotonic()
                run_openfoam(
                    "polyDualMesh", case_dir, [str(_feat)],
                )
                # polyDualMesh writes the new polyMesh into a time
                # directory (1/polyMesh).  Promote it back to
                # constant/polyMesh so the evaluator finds it.
                _from = case_dir / "1" / "polyMesh"
                _to = case_dir / "constant" / "polyMesh"
                if _from.exists():
                    if _to.exists():
                        shutil.rmtree(str(_to))
                    shutil.copytree(str(_from), str(_to))
                logger.info(
                    "cfmesh_poly_cartesian_dual_used",
                    polymesh=str(_to),
                    feature_angle=_feat,
                    step1_s=round(time.monotonic() - t_step - (time.monotonic() - _step2_t), 3),
                    step2_s=round(time.monotonic() - _step2_t, 3),
                )
            except Exception as exc:
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=time.monotonic() - t_start,
                    steps=[GeneratorStep(
                        name="polyDualMesh",
                        status="failed",
                        time=time.monotonic() - t_step,
                    )],
                    error_message=(
                        f"cartesian_dual stage 2 (polyDualMesh) 실패: "
                        f"{str(exc)[:300]}"
                    ),
                )
        else:
            # legacy pMesh path (segfault prone on broken STLs).
            r = cfm.poly_mesh(
                str(stl_path), str(case_dir),
                max_cell_size=max_cell,
                min_cell_size=min_cell,
                boundary_cell_size=boundary_cell,
                bl_n_layers=n_layers,
                bl_thickness_ratio=thickness_ratio,
                bl_max_first_layer=max_first,
                feature_angle_deg=float(params.get("bl_feature_angle", 30.0)),
                keep_cells_intersecting_boundary=True,
            )

        step_time = time.monotonic() - t_step
        elapsed = time.monotonic() - t_start

        # Legacy pMesh failure check — tet_dual and cartesian_dual return
        # early on failure, so this branch only matters for cfmesh_pmesh.
        if _backend not in ("cartesian_dual", "tet_dual") and not r.get("success"):
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                steps=[GeneratorStep(name="cfmesh_pMesh", status="failed", time=step_time)],
                error_message=f"cfmesh pMesh 실패: {r.get('log', '')[-300:]}",
            )

        logger.info(
            "cfmesh_poly_vendored_used",
            backend=_backend,
            polymesh=str(case_dir / "constant" / "polyMesh"),
        )
        return TierAttempt(
            tier=TIER_NAME,
            status="success",
            time_seconds=elapsed,
            steps=[GeneratorStep(name="cfmesh_pMesh", status="success", time=step_time)],
        )
