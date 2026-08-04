"""Receipt-bound Native Tet stage/audit orchestration.

The generator callback remains Python orchestration; artifact fingerprinting,
strict topology and native quality readers provide the stage gate.  The C++
atomic publish kernel is the only publication primitive used here.
"""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import subprocess
from typing import Any, Callable

from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_tet.staged_runner import (
    StagedTetRunEvidence,
    run_tet_in_private_stage,
)


def _sealed_quality_policy(receipt: Mapping[str, Any]) -> dict[str, Any] | None:
    candidate = receipt.get("quality_policy")
    if not isinstance(candidate, Mapping):
        return None
    required = (
        "max_non_orthogonality",
        "max_skewness",
        "max_aspect_ratio",
        "policy_sha256",
    )
    if any(key not in candidate for key in required):
        return None
    return dict(candidate)

def _native_tet_child_path() -> Path | None:
    override = os.environ.get("AUTOTESSELL_NATIVE_TET_CHILD", "").strip()
    candidates = [Path(override)] if override else []
    repo_root = Path(__file__).resolve().parents[3]
    candidates.extend([
        repo_root / "auto_tessell_core" / "build" / "native_tet_persisted_volume_artifact_cli",
        repo_root / "auto_tessell_core" / "build" / "Debug" / "native_tet_persisted_volume_artifact_cli",
    ])
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _ledger_atom(value: Any, field: str) -> str:
    atom = str(value).strip()
    if not atom or any(char.isspace() for char in atom):
        raise ValueError(f"persisted_contract_{field}_invalid")
    return atom


def _write_native_tet_persisted_contract(
    stage: Path,
    receipt: Mapping[str, Any],
    result: Any,
    requested_layers: int,
) -> Path:
    interfaces = receipt.get("interface_triangles")
    if not isinstance(interfaces, list) or not interfaces:
        raise ValueError("persisted_contract_source_faces_missing")
    tets = getattr(result, "tets", None)
    shape = getattr(tets, "shape", ())
    if len(shape) != 2 or int(shape[1]) != 4 or int(shape[0]) <= 0:
        raise ValueError("persisted_contract_cell_lineage_missing")
    source_rows: list[tuple[str, list[int], tuple[str, ...]]] = []
    seen: set[str] = set()
    for ordinal, raw in enumerate(interfaces):
        if not isinstance(raw, Mapping):
            raise ValueError("persisted_contract_source_face_invalid")
        triangle = raw.get("triangle")
        if not isinstance(triangle, (list, tuple)) or len(triangle) != 3:
            raise ValueError("persisted_contract_source_triangle_invalid")
        try:
            vertices = [int(value) for value in triangle]
        except (TypeError, ValueError) as exc:
            raise ValueError("persisted_contract_source_vertex_invalid") from exc
        source_id = _ledger_atom(raw.get("source_face", f"receipt-face-{ordinal}"), "source_id")
        if source_id in seen or len(set(vertices)) != 3 or min(vertices) < 0:
            raise ValueError("persisted_contract_source_face_identity_invalid")
        seen.add(source_id)
        semantics = tuple(_ledger_atom(raw.get(key, ""), key) for key in (
            "feature", "patch", "physical_group", "component", "provenance"
        ))
        source_rows.append((source_id, vertices, semantics))
    source_sha = _ledger_atom(receipt.get("source_sha256", ""), "source_sha256")
    semantic_sha = _ledger_atom(receipt.get("semantic_ledger_sha256", ""), "semantic_sha256")
    parameter_sha = _ledger_atom(receipt.get("receipt_digest", "unsealed"), "parameter_sha256")
    build_identity = _ledger_atom(receipt.get("build_identity", "receipt-route"), "build_identity")
    lines = [
        "schema native-tet-persisted-contract/v2",
        f"meta source_sha256 {source_sha}",
        f"meta semantic_ledger_sha256 {semantic_sha}",
        "meta topology_kind tet",
        "meta cell_family tet",
        "meta face_arity_policy triangle",
        f"meta requested_layers {int(requested_layers)}",
        f"meta actual_layers {int(requested_layers)}",
        f"meta parameter_receipt_sha256 {parameter_sha}",
        f"meta build_identity {build_identity}",
    ]
    for source_id, vertices, semantics in source_rows:
        lines.append("face " + " ".join([source_id, *(str(value) for value in vertices), *semantics]))
    first_id, _, first_semantics = source_rows[0]
    for cell_id in range(int(shape[0])):
        lines.append("cell " + " ".join([f"cell-{cell_id}", first_id, *first_semantics]))
    target = stage / "native-tet-persisted-contract.v2"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _run_native_tet_persisted_child(stage: Path, contract: Path) -> dict[str, Any]:
    child = _native_tet_child_path()
    if child is None:
        return {"accepted": False, "reason": "native_tet_persisted_child_unavailable"}
    poly_mesh = stage / "constant" / "polyMesh"
    try:
        completed = subprocess.run(
            [str(child), str(poly_mesh), str(contract)],
            text=True, capture_output=True, check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"accepted": False, "reason": f"native_tet_persisted_child_exception:{type(exc).__name__}"}
    fields: dict[str, Any] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    accepted = completed.returncode == 0 and fields.get("accepted") == "true"
    if not accepted:
        return {
            "accepted": False,
            "reason": fields.get("reason", "native_tet_persisted_child_refused"),
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    fields["accepted"] = True
    fields["child_path"] = str(child)
    return fields


def run_receipt_locked_stage(
    runner: Callable[..., Any],
    vertices: Any,
    faces: Any,
    case_dir: str | Path,
    *,
    verify_output: Callable[[Any, Any, Any, Any, int], Mapping[str, Any]],
    receipt: Mapping[str, Any],
    requested_layers: int,
    **kwargs: Any,
) -> StagedTetRunEvidence:
    """Run, reread/audit, and atomically publish one receipt-bound Tet run."""
    holder: dict[str, Any] = {}

    def staged_runner(run_vertices: Any, run_faces: Any, stage: Path, **run_kwargs: Any) -> Any:
        result = runner(run_vertices, run_faces, stage, **run_kwargs)
        if bool(getattr(result, "success", False)):
            try:
                holder["persisted_contract"] = _write_native_tet_persisted_contract(
                    stage, receipt, result, requested_layers
                )
            except Exception as exc:
                holder["persisted_contract_error"] = f"{type(exc).__name__}:{exc}"
        holder["result"] = result
        return result

    def audit(stage: Path) -> dict[str, Any]:
        result = holder.get("result")
        if result is None or not bool(getattr(result, "success", False)):
            return {"accepted": False, "reason": "stage_runner_refused"}
        output = dict(verify_output(receipt, result, vertices, faces, requested_layers))
        contract_error = holder.get("persisted_contract_error")
        contract_marker = holder.get("persisted_contract")
        contract = (
            stage / contract_marker.name
            if isinstance(contract_marker, Path)
            else stage / "native-tet-persisted-contract.v2"
        )
        if (
            contract_error
            or not isinstance(contract_marker, Path)
            or contract.name != "native-tet-persisted-contract.v2"
            or not contract.is_file()
        ):
            return {
                "accepted": False,
                "reason": contract_error or "persisted_contract_missing",
                "output_readback": output,
                "publication_eligible": False,
            }
        persisted_child = _run_native_tet_persisted_child(stage, contract)
        if persisted_child.get("accepted") is not True:
            return {
                "accepted": False,
                "reason": str(persisted_child.get("reason", "persisted_child_refused")),
                "output_readback": output,
                "persisted_child": persisted_child,
                "publication_eligible": False,
            }
        strict = audit_strict_volume_topology(stage)
        strict_dict = strict.as_dict()
        writer_ledger: dict[str, Any] | None = None
        if requested_layers > 0:
            from core.generator.native_tet.writer_ledger import (
                validate_native_tet_writer_ledger,
            )
            writer_ledger = validate_native_tet_writer_ledger(
                stage / "native_tet_bl_writer_ledger.json",
                source_sha256=str(receipt.get("source_sha256", "")),
                requested_layers=requested_layers,
            )
            if writer_ledger.get("accepted") is not True:
                return {
                    "accepted": False,
                    "reason": "positive_bl_writer_ledger_refused",
                    "strict_topology": strict_dict,
                    "output_readback": output,
                    "writer_ledger": writer_ledger,
                    "publication_eligible": False,
                }
        quality: dict[str, float] = {}
        try:
            from core.evaluator.native_checker import NativeMeshChecker

            measured = NativeMeshChecker().run(stage)
            quality = {
                "max_non_orthogonality": float(measured.max_non_orthogonality),
                "max_skewness": float(measured.max_skewness),
                "max_aspect_ratio": float(measured.max_aspect_ratio),
                "negative_volumes": float(measured.negative_volumes),
            }
        except Exception as exc:
            return {
                "accepted": False,
                "reason": f"stage_quality_readback_unavailable:{type(exc).__name__}",
                "output_readback": output,
                "strict_topology": strict_dict,
            }
        policy = _sealed_quality_policy(receipt)
        if policy is None:
            return {
                "accepted": False,
                "reason": "sealed_quality_policy_missing",
                "strict_topology": strict_dict,
                "output_readback": output,
                "quality": quality,
                "publication_eligible": False,
            }
        try:
            from core.utils.native_extensions import import_native_extension

            native_quality = import_native_extension("native_tet_polymesh_quality")
            disk_quality = dict(native_quality.audit_with_policy(
                str(stage / "constant" / "polyMesh"), policy
            ))
        except Exception as exc:
            return {
                "accepted": False,
                "reason": f"native_disk_quality_oracle_unavailable:{type(exc).__name__}",
                "strict_topology": strict_dict,
                "output_readback": output,
                "quality": quality,
                "publication_eligible": False,
            }
        from core.generator.native_tet.disk_receipt_graph import audit_disk_receipt_graph

        graph_receipt: Mapping[str, Any] = receipt
        if requested_layers > 0:
            from core.generator.native_tet.writer_ledger_receipt import (
                interface_children_from_writer_ledger,
            )
            graph_receipt = dict(receipt)
            graph_receipt["interface_children"] = interface_children_from_writer_ledger(
                stage / "native_tet_bl_writer_ledger.json"
            )
        disk_graph = audit_disk_receipt_graph(
            stage / "constant" / "polyMesh", graph_receipt
        )
        if disk_graph.get("accepted") is not True:
            return {
                "accepted": False,
                "reason": str(disk_graph.get("reason", "receipt_graph_refused")),
                "strict_topology": strict_dict,
                "output_readback": output,
                "persisted_child": persisted_child,
                "quality": quality,
                "disk_quality": disk_quality,
                "disk_graph": disk_graph,
                "writer_ledger": writer_ledger,
                "quality_policy": policy,
                "publication_eligible": False,
            }
        python_topology_ok = quality["negative_volumes"] == 0.0
        quality_ok = bool(
            python_topology_ok and disk_quality.get("valid") is True
            and disk_quality.get("quality_pass") is True
        )
        accepted = bool(strict.valid and output.get("accepted") is True and quality_ok)
        return {
            "accepted": accepted,
            "reason": "stage_reread_audit_pass" if accepted else "stage_reread_quality_or_topology_refused",
            "strict_topology": strict_dict,
            "output_readback": output,
            "persisted_child": persisted_child,
            "quality": quality,
            "disk_quality": disk_quality,
            "disk_graph": disk_graph,
            "writer_ledger": writer_ledger,
            "quality_policy": policy,
            "publication_eligible": False,
        }

    return run_tet_in_private_stage(
        staged_runner,
        vertices,
        faces,
        case_dir,
        audit_callback=audit,
        post_publish_audit_callback=audit,
        journal_path=Path(case_dir).parent / f".{Path(case_dir).name}.native_transaction_journal.json",
        journal_history_path=Path(case_dir).parent / f".{Path(case_dir).name}.native_transaction_history.json",
        **kwargs,
    )
