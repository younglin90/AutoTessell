"""Actual STEP/BRep regular-tetra pure-Tet BL evidence bridge.

Geometry, topology, template selection, and quality stay in the C++ producer.
Python only adapts OCCT evidence, serializes the producer-owned artifact, and
invokes the existing independent persisted audit.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.evaluator.native_l2_evidence_audit import audit_native_tet_polymesh_persisted_evidence
from core.layers.native_tet_brep_front_evidence_v2 import build_brep_front_evidence_v2
from core.utils.native_extensions import import_native_extension


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _tree_digest(path: Path) -> str:
    raw = bytearray()
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        raw.extend(name.encode())
        raw.append(0)
        raw.extend((path / name).read_bytes())
        raw.append(0)
    return _sha(bytes(raw))


def _foam_header(count: int) -> str:
    return "FoamFile\n{\n    format ascii;\n}\n" + str(count) + "\n(\n"


def _write_polymesh(poly: Path, producer: Mapping[str, Any], boundary_name: str = "wall") -> None:
    poly.mkdir(parents=True, exist_ok=True)
    points = producer["points"]
    faces = producer["faces"]
    owner = producer["owner"]
    neighbour = producer["neighbour"]
    ranges = producer["boundary_ranges"]
    point_text = _foam_header(len(points)) + "".join(
        f"({float(p[0]):.17g} {float(p[1]):.17g} {float(p[2]):.17g})\n" for p in points
    ) + ")\n"
    face_text = _foam_header(len(faces)) + "".join(
        f"3({int(f[0])} {int(f[1])} {int(f[2])})\n" for f in faces
    ) + ")\n"
    owner_text = _foam_header(len(owner)) + "".join(f"{int(value)}\n" for value in owner) + ")\n"
    neighbour_text = _foam_header(len(neighbour)) + "".join(
        f"{int(value)}\n" for value in neighbour
    ) + ")\n"
    boundary_text = (
        "FoamFile\n{\n    format ascii;\n}\n"
        + str(len(ranges))
        + "\n(\n"
        + "".join(
            f"source-face-{int(index)}\n{{\n    type {boundary_name};\n"
            f"    nFaces {int(pair[1])};\n    startFace {int(pair[0])};\n}}\n"
            for index, pair in enumerate(ranges)
        )
        + ")\n"
    )
    for name, text in {
        "points": point_text,
        "faces": face_text,
        "owner": owner_text,
        "neighbour": neighbour_text,
        "boundary": boundary_text,
    }.items():
        (poly / name).write_text(text)


def _copy_poly(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst)


def _mapping_digest(mapping: Sequence[Mapping[str, Any]]) -> str:
    return _sha(json.dumps([dict(row) for row in mapping], sort_keys=True, separators=(",", ":")).encode())


def _write_source_ledger(root: Path, evidence: Mapping[str, Any], mapping: Sequence[Mapping[str, Any]]) -> None:
    rows: list[str] = []
    for triangle in sorted(evidence["triangles"], key=lambda row: int(row["brep_face_id"])):
        face_id = int(triangle["brep_face_id"])
        semantic = next(
            (dict(row) for row in mapping if int(row["source_face"]) == face_id),
            dict(mapping[0]),
        )
        edge_id = int(semantic["source_edge"])
        vertices = ",".join(str(int(value)) for value in triangle["canonical_vertices"])
        rows.append(
            "\t".join(
                [
                    f"face-{face_id}",
                    f"edge-{edge_id}",
                    str(semantic["feature"]),
                    str(semantic["patch"]),
                    str(semantic["physical_group"]),
                    str(semantic["component"]),
                    "forward",
                    vertices,
                    str(face_id),
                ]
            )
        )
    (root / "ledger.tsv").write_text("\n".join(rows) + "\n")


def _write_bindings(root: Path, producer: Mapping[str, Any]) -> None:
    rows: list[str] = []
    for row in producer["boundary_binding"]:
        final_cells = ",".join(str(int(value)) for value in row["final_cell_ids"])
        front_faces = ",".join(str(int(value)) for value in row["final_front_face_ids"])
        wall_faces = ",".join(str(int(value)) for value in row["final_wall_face_ids"])
        fields = [
            str(row["source_face"]),
            str(row.get("source_face_a", "")),
            str(row.get("source_face_b", "")),
            str(row["source_edge"]),
            str(row["wall_edge"]),
            str(row["bl_strip"]),
            str(row["output_boundary_face"]),
            str(row["volume_boundary_face"]),
            str(row["feature"]),
            str(row["patch"]),
            str(row["physical_group"]),
            str(row["component"]),
            str(row["provenance"]),
            str(int(row["wall0"])),
            str(int(row["wall1"])),
            str(int(row["front0"])),
            str(int(row["front1"])),
            str(row["tangent_face"]),
            str(int(row["first_strip_face"])),
            str(row.get("orientation", "forward")),
            final_cells,
            front_faces,
            wall_faces,
        ]
        rows.append("\t".join(fields))
    (root / "binding.tsv").write_text("\n".join(rows) + "\n")


def _write_layers(root: Path, producer: Mapping[str, Any], requested_layers: int, first_height: float, growth: float) -> float:
    cumulative = 0.0
    rows: list[str] = []
    for layer, row in enumerate(producer["layer_records"]):
        thickness = first_height * (growth ** layer)
        cumulative += thickness
        rows.append(
            "\t".join(
                [
                    str(layer),
                    f"{first_height:.17g}",
                    f"{thickness:.17g}",
                    f"{cumulative:.17g}",
                    f"{growth:.17g}",
                    "tet-shell",
                    str(len(row["cell_ids"])),
                    str(row["source_face"]),
                ]
            )
        )
    (root / "layers.tsv").write_text("\n".join(rows) + ("\n" if rows else ""))
    return cumulative


def _write_manifest(
    root: Path,
    source_rel: str,
    source_digest: str,
    output_digest: str,
    baseline_digest: str,
    candidate_digest: str,
    mapping_digest: str,
    evidence: Mapping[str, Any],
    requested_layers: int,
    actual_layers: int,
    first_height: float,
    growth: float,
    total_thickness: float,
) -> None:
    build_digest = _sha(b"native_tet_actual_brep_conformal_shell/v1")
    config_digest = _sha(
        json.dumps(
            {
                "requested_layers": requested_layers,
                "first_height": first_height,
                "growth_ratio": growth,
            },
            sort_keys=True,
        ).encode()
    )
    lines = [
        "schema=native-l2-persisted-evidence/v1",
        "engine=native_tet",
        "artifact_format=openfoam-polymesh-ascii/v1",
        f"source_path={source_rel}",
        "polymesh_root=output/case/constant/polyMesh",
        "baseline_polymesh_root=baseline/case/constant/polyMesh",
        "run_polymesh_root_1=runs/run-1/case/constant/polyMesh",
        "run_polymesh_root_2=runs/run-2/case/constant/polyMesh",
        "run_polymesh_root_3=runs/run-3/case/constant/polyMesh",
        "ledger_path=ledger.tsv",
        "binding_path=binding.tsv",
        f"source_sha256={source_digest}",
        f"artifact_tree_sha256={output_digest}",
        f"build_sha256={build_digest}",
        f"config_sha256={config_digest}",
        f"baseline_digest={baseline_digest}",
        f"candidate_digest={candidate_digest}",
        f"requested_layers={requested_layers}",
        f"actual_layers={actual_layers}",
        f"bl0_exact_identity={'true' if requested_layers == 0 else 'false'}",
        "authority_level=L0_actual_brep_fixture",
        f"authority_canonical_positions_digest={evidence['canonical_positions_digest']}",
        f"authority_face_ordinal_digest={evidence['face_ordinal_digest']}",
        f"authority_orientation_digest={evidence['orientation_digest']}",
        f"authority_seam_digest={evidence['seam_digest']}",
        f"authority_mapping_digest={mapping_digest}",
    ]
    if requested_layers:
        lines.extend(
            [
                "positive_contract=true",
                "source_authority_kind=actual-brep-regular-tetra-fixture",
                "source_authority_status=SOURCE_VERIFIED",
                "wall_edge_eligible=true",
                "writer_owned_id_capsule=true",
                "pure_tet=true",
                f"layer_record_count={actual_layers}",
                "wall_edge_binding_count=1",
                f"first_thickness={first_height:.17g}",
                f"growth_ratio={growth:.17g}",
                f"total_thickness={total_thickness:.17g}",
                "quality_aspect_cap=5.0",
                "layer_path=layers.tsv",
            ]
        )
    (root / "evidence.atne").write_text("\n".join(lines) + "\n")


def write_actual_brep_conformal_tet_shell_evidence(
    target_root: str | Path,
    source_path: str | Path,
    *,
    explicit_mapping: Sequence[Mapping[str, Any]],
    owner_face_by_edge: Mapping[int, int],
    requested_layers: int,
    first_height: float | None = None,
    growth_ratio: float = 0.5,
) -> dict[str, Any]:
    target = Path(target_root)
    source = Path(source_path)
    if target.exists():
        return {
            "accepted": False,
            "reason": "target_exists",
            "candidate_discarded": True,
            "atomic_rollback": True,
            "publication_eligible": False,
        }
    if requested_layers < 0:
        return {"accepted": False, "reason": "negative_layer_count", "candidate_discarded": True}
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = parent / f".{target.name}.actual-tet-tmp"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir()
    try:
        raw = source.read_bytes()
        source_digest = _sha(raw)
        cad = load_cad_native_with_provenance(source, source.suffix.lower())
        evidence = build_brep_front_evidence_v2(
            cad,
            source_digest=source_digest,
            owner_face_by_edge=owner_face_by_edge,
        )
        positions = np.ascontiguousarray(np.asarray(evidence["canonical_positions"], dtype=np.float64))
        mapping = [dict(row) for row in explicit_mapping]
        selected = [row for row in mapping if bool(row.get("selected_for_bl", False))]
        if len(selected) != 1:
            raise ValueError("exactly_one_selected_wall_edge_required")
        selected_face = int(selected[0]["source_face"])
        wall_triangle = next(
            row for row in evidence["triangles"] if int(row["brep_face_id"]) == selected_face
        )
        wall_vertices = np.asarray(wall_triangle["canonical_vertices"], dtype=np.int64)
        p = positions[wall_vertices]
        normal = np.cross(p[1] - p[0], p[2] - p[0])
        height = abs(float(np.dot(positions[[i for i in range(4) if i not in wall_vertices][0]] - p.mean(axis=0), normal) / np.linalg.norm(normal)))
        step = 0.50 * height if first_height is None else float(first_height)
        if not np.isfinite(step) or step <= 0:
            raise ValueError("invalid_first_height")
        if not np.isfinite(growth_ratio) or growth_ratio <= 0:
            raise ValueError("invalid_growth_ratio")
        kernel = import_native_extension("native_tet_actual_brep_conformal_shell")
        producers: list[dict[str, Any]] = []
        for _ in range(3):
            result = dict(
                kernel.produce_actual_brep_conformal_tet_shell(
                    positions,
                    evidence,
                    mapping,
                    int(requested_layers),
                    step,
                    float(growth_ratio),
                )
            )
            if not result.get("accepted"):
                return result
            producers.append(result)
        baseline = temp / "baseline/case/constant/polyMesh"
        _write_polymesh(baseline, producers[0] if requested_layers == 0 else dict(
            kernel.produce_actual_brep_conformal_tet_shell(
                positions, evidence, mapping, 0, step, growth_ratio
            )
        ))
        output = temp / "output/case/constant/polyMesh"
        _write_polymesh(output, producers[0])
        for index in range(1, 4):
            _write_polymesh(temp / f"runs/run-{index}/case/constant/polyMesh", producers[index - 1])
        (temp / "source").mkdir()
        source_rel = "source/" + source.name
        (temp / source_rel).write_bytes(raw)
        _write_source_ledger(temp, evidence, mapping)
        _write_bindings(temp, producers[0])
        total = _write_layers(temp, producers[0], requested_layers, step, float(growth_ratio))
        baseline_digest = _tree_digest(baseline)
        output_digest = _tree_digest(output)
        _write_manifest(
            temp,
            source_rel,
            source_digest,
            output_digest,
            baseline_digest,
            baseline_digest if requested_layers == 0 else output_digest,
            _mapping_digest(mapping),
            evidence,
            int(requested_layers),
            int(producers[0]["actual_layers"]),
            step,
            float(growth_ratio),
            total,
        )
        audit = dict(audit_native_tet_polymesh_persisted_evidence(str(temp)))
        if not audit.get("accepted"):
            shutil.rmtree(temp)
            return {
                "accepted": False,
                "reason": f"persisted_audit_refused:{audit.get('reason', 'unknown')}",
                "audit": audit,
                "producer": producers[0],
                "producers": producers,
                "candidate_discarded": True,
                "atomic_rollback": True,
                "publication_eligible": False,
            }
        temp.replace(target)
        return {
            "accepted": True,
            "status": "native_tet_actual_brep_conformal_shell_evidence_written",
            "reason": "cxx_producer_and_persisted_audit_passed",
            "evidence_root": str(target),
            "producer": producers[0],
            "producers": producers,
            "audit": audit,
            "authority_level": "L0_actual_brep_fixture",
            "publication_eligible": False,
            "atomic_rollback": False,
        }
    except Exception as exc:
        if temp.exists():
            shutil.rmtree(temp)
        return {
            "accepted": False,
            "reason": f"actual_tet_shell_exception:{type(exc).__name__}:{exc}",
            "candidate_discarded": True,
            "atomic_rollback": True,
            "publication_eligible": False,
        }
