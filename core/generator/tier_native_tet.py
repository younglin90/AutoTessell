"""Tier wrapper: native_tet MVP 엔진 + harness (Gen↔Eval)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.generator._tier_native_common import run_native_tier
from core.generator.native_tet import (
    NativeTetResult,
    TetHarnessResult,
    generate_native_tet,
    run_native_tet_harness,
)
from core.generator.native_tet.receipt_route import verify_surface_receipt_output
from core.generator.native_tet.receipt_stage import run_receipt_locked_stage
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_tet"


def _surface_receipt_from_config(config: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return an explicit authoritative surface receipt, if supplied.

    The receipt is intentionally opt-in.  Legacy/native calls without one
    retain their existing route; a supplied receipt enters the strict route
    and may not silently fall back to an unbound generator.
    """
    if not isinstance(config, Mapping):
        return None
    candidates: list[Any] = [
        config.get("surface_receipt"),
        config.get("input", {}).get("surface_receipt")
        if isinstance(config.get("input"), Mapping) else None,
        config.get("source_output_authority", {}).get("surface_receipt")
        if isinstance(config.get("source_output_authority"), Mapping) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return None


def _requested_boundary_layers(config: Mapping[str, Any] | None) -> int:
    if not isinstance(config, Mapping):
        return 0
    raw_layers = config.get("boundary_layers", [])
    if not isinstance(raw_layers, list):
        return 0
    count = 0
    for entry in raw_layers:
        if isinstance(entry, Mapping):
            try:
                count = max(count, int(entry.get("layers", 0)))
            except (TypeError, ValueError):
                continue
    return max(0, count)


def _lock_surface_receipt_ingress(
    vertices: Any,
    faces: Any,
    input_config: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, NativeTetResult | None]:
    receipt = _surface_receipt_from_config(input_config)
    if receipt is None:
        return None, None, None
    requested_layers = _requested_boundary_layers(input_config)
    try:
        import native_tet_surface_boundary_receipt_consumer as consumer
    except Exception as exc:
        # Production runs normally install the extension on PYTHONPATH; the
        # repository build tree is also a supported local developer route.
        try:
            import importlib
            import sys
            build_dir = Path(__file__).resolve().parents[2] / "auto_tessell_core" / "build"
            if build_dir.is_dir() and str(build_dir) not in sys.path:
                sys.path.insert(0, str(build_dir))
            consumer = importlib.import_module("native_tet_surface_boundary_receipt_consumer")
        except Exception:
            consumer = None
    if consumer is None:
        return receipt, None, NativeTetResult(
            success=False,
            elapsed=0.0,
            message=f"native_tet receipt ingress unavailable: {type(exc).__name__}",
            debug_info={"receipt_ingress": {"accepted": False, "reason": "receipt_consumer_unavailable"}},
        )
    try:
        result = dict(consumer.validate_surface_boundary_receipt_ingress(
            receipt, vertices, faces, requested_layers
        ))
    except Exception as exc:
        result = {"accepted": False, "reason": f"receipt_ingress_exception:{type(exc).__name__}"}
    if result.get("accepted") is not True:
        return receipt, result, NativeTetResult(
            success=False,
            elapsed=0.0,
            message=f"native_tet receipt ingress refused: {result.get('reason', 'unknown')}",
            debug_info={"receipt_ingress": result, "requested_layers": requested_layers},
        )
    return receipt, result, None


def _runner(
    vertices: Any,
    faces: Any,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 12,
    max_iter: int = 2,
    input_config: Mapping[str, Any] | None = None,
    input_parameter_report: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> NativeTetResult | TetHarnessResult:
    """harness 우선, 완전 실패 시 기본 generate_native_tet 로 fallback.

    quality-specific 파라미터 (seed_density / max_iter) 는 run_native_tier 가
    HARNESS_PARAMS 테이블에서 주입. 직접 호출 시의 기본값은 standard 와 동일.

    beta2295: TetWild-lite Phase B/C / AMIPS / chunked / CDT / target_cells
    knobs 를 **kwargs 로 forward (이전엔 **_unused 가 silently drop).
    harness 는 이미 (beta310 부터) **kwargs 를 mesher 에 전달하도록 wired.

    The orchestrator forwards pipeline-level kwargs that aren't part
    of the volume-mesher API (``bl_layers``, ``post_layers_*``,
    ``checker_engine``, ``cad_engine``, etc).  Strip them here so
    they don't leak into ``generate_native_tet`` and trigger
    "unexpected keyword argument" failures (BLR-9c-d-r-1 fix).
    """
    _PIPELINE_ONLY_KEYS = {
        "bl_layers",
        "post_layers_engine",
        "post_layers_num_layers",
        "checker_engine",
        "cad_engine",
        "remesh_engine",
        "repair_engine",
        "postprocess_engine",
    }
    forward_kwargs = {k: v for k, v in kwargs.items() if k not in _PIPELINE_ONLY_KEYS}
    receipt, receipt_result, receipt_failure = _lock_surface_receipt_ingress(
        vertices, faces, input_config
    )
    if receipt_failure is not None:
        return receipt_failure
    stage_evidence = None
    if receipt is not None:
        def _run_receipt_harness(run_vertices: Any, run_faces: Any, stage: Path, **run_kwargs: Any) -> Any:
            return run_native_tet_harness(
                run_vertices, run_faces, stage,
                target_edge_length=target_edge_length,
                seed_density=int(seed_density),
                max_iter=int(max_iter),
                **run_kwargs,
            )
        stage_evidence = run_receipt_locked_stage(
            _run_receipt_harness,
            vertices,
            faces,
            case_dir,
            verify_output=verify_surface_receipt_output,
            receipt=receipt,
            requested_layers=_requested_boundary_layers(input_config),
            **forward_kwargs,
        )
        hres = stage_evidence.result
    else:
        hres = run_native_tet_harness(
            vertices, faces, case_dir,
            target_edge_length=target_edge_length,
            seed_density=int(seed_density),
            max_iter=int(max_iter),
            **forward_kwargs,
        )
    if receipt is not None:
        # A receipt-bound run is a strict route: preserve the evidence on the
        # actual tier result and never downgrade to the legacy fallback after
        # a harness failure. Read-back is evidence only; publication remains
        # locked until atomic staging and release corpus gates exist.
        if hres.success:
            readback = verify_surface_receipt_output(
                receipt, hres, vertices, faces, _requested_boundary_layers(input_config)
            )
        else:
            readback = {"accepted": False, "reason": "harness_failed_before_readback"}
        hres.route = "native_tet_production_receipt"
        hres.contract = "receipt_locked_ingress"
        hres.contract_details = {
            "receipt_ingress": dict(receipt_result or {}),
            "receipt_digest": receipt.get("receipt_digest"),
            "requested_layers": _requested_boundary_layers(input_config),
            "publication_eligible": False,
            "output_readback": dict(readback),
        }
        if stage_evidence is not None:
            hres.contract_details["stage"] = {
                "published": bool(stage_evidence.published),
                "audit": stage_evidence.audit,
                "publish": stage_evidence.publish,
                "refused_reason": stage_evidence.refused_reason,
                "destination_audit": stage_evidence.destination_audit,
            }
            if not stage_evidence.published:
                hres.success = False
                hres.message = f"native_tet receipt stage refused: {stage_evidence.refused_reason or 'unknown'}"
        if readback.get("accepted") is not True:
            hres.success = False
            hres.message = f"native_tet receipt output refused: {readback.get('reason', 'unknown')}"
        return hres
    if hres.success or hres.n_cells > 0:
        return hres
    # 완전 실패 → 기본 경로로 한 번 더
    # ``max_cells`` is a harness-only safety cap.  The direct mesher owns
    # ``target_cells`` but has no ``max_cells`` parameter, so reuse every
    # supported mesher knob while dropping only the consumed harness budget.
    fallback_kwargs = {key: value for key, value in forward_kwargs.items() if key != "max_cells"}
    return generate_native_tet(
        vertices,
        faces,
        case_dir,
        target_edge_length=target_edge_length,
        seed_density=int(seed_density),
        **fallback_kwargs,
    )


class TierNativeTetGenerator:
    """AutoTessell 자체 tet 엔진 (scipy Delaunay + envelope check)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        return run_native_tier(
            _runner,
            self.TIER_NAME,
            strategy,
            preprocessed_path,
            case_dir,
        )
