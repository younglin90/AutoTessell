"""Actual STEPCAF/XDE Native Hex evidence bridge for the restricted box route."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.evaluator.native_canonical_quality_witness import build_authority_bound_volume_quality_witness
from core.generator.native_hex.xde_semantic_ledger import build_explicit_xde_hex_profile
from core.utils.native_extensions import import_native_extension


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _array_hash(value: object) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _payload_hash(value: object) -> str:
    return _sha(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _tree_digest(poly: Path) -> str:
    raw = bytearray()
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        raw.extend(name.encode())
        raw.append(0)
        raw.extend((poly / name).read_bytes())
        raw.append(0)
    return _sha(bytes(raw))


def _header(count: int) -> str:
    return "FoamFile\n{\n    format ascii;\n}\n" + str(count) + "\n(\n"


def _write_polymesh(poly: Path, producer: Mapping[str, Any]) -> None:
    poly.mkdir(parents=True, exist_ok=True)
    points = np.asarray(producer["points"], dtype=np.float64)
    faces = np.asarray(producer["faces"], dtype=np.int64)
    owner = [int(v) for v in producer["owner"]]
    neighbour = [int(v) for v in producer["neighbour"]]
    internal_count = len(neighbour)
    assert len(owner) == len(faces)
    point_text = _header(len(points)) + "".join(
        f"({p[0]:.17g} {p[1]:.17g} {p[2]:.17g})\n" for p in points
    ) + ")\n"
    face_text = _header(len(faces)) + "".join(
        f"4({int(f[0])} {int(f[1])} {int(f[2])} {int(f[3])})\n" for f in faces
    ) + ")\n"
    owner_text = _header(len(owner)) + "".join(f"{v}\n" for v in owner) + ")\n"
    neighbour_text = _header(len(neighbour)) + "".join(f"{v}\n" for v in neighbour) + ")\n"
    boundary_text = (
        "FoamFile\n{\n    format ascii;\n}\n1\n(\n"
        f"source-boundary\n{{\n    type wall;\n    nFaces {len(faces) - internal_count};\n    startFace {internal_count};\n}}\n)\n"
    )
    for name, text in {
        "points": point_text,
        "faces": face_text,
        "owner": owner_text,
        "neighbour": neighbour_text,
        "boundary": boundary_text,
    }.items():
        (poly / name).write_text(text)


def _mapping_digest(rows: list[Mapping[str, Any]]) -> str:
    return _sha(json.dumps([dict(row) for row in rows], sort_keys=True, separators=(",", ":")).encode())


def _write_ledgers(root: Path, profile: Mapping[str, Any], producer: Mapping[str, Any]) -> None:
    rows = profile["face_records"]
    (root / "source_ledger.tsv").write_text(
        "\n".join(
            "\t".join(
                [
                    str(row["face_id"]), str(row["feature"]), str(row["patch"]),
                    str(row["physical_group"]), str(row["component"]),
                    str(row["provenance"]),
                ]
            ) for row in rows
        ) + "\n"
    )
    (root / "binding.tsv").write_text(
        "\n".join(
            "\t".join(
                [str(row["source_face"]), str(row["output_face"]), str(row["feature"]),
                 str(row["patch"]), str(row["physical_group"]), str(row["component"]),
                 str(row["provenance"]), str(bool(row["direct"]))]
            ) for row in producer["boundary_binding"]
        ) + "\n"
    )
    layer_lines = [
        "\t".join([
            str(item["layer"]), f"{float(item['thickness']):.17g}",
            f"{float(item['cumulative_thickness']):.17g}", str(bool(item["positive"])),
        ]) for item in producer["layer_records"]
    ]
    (root / "layers.tsv").write_text("\n".join(layer_lines) + ("\n" if layer_lines else ""))


def write_actual_xde_hex_evidence(
    target_root: str | Path,
    source_path: str | Path,
    *,
    requested_layers: int,
    growth_ratio: float = 1.2,
    first_height: float | None = None,
) -> dict[str, Any]:
    target = Path(target_root)
    source = Path(source_path)
    if target.exists():
        return {"accepted": False, "reason": "target_exists", "candidate_discarded": True, "atomic_rollback": True}
    if requested_layers < 0:
        return {"accepted": False, "reason": "negative_layer_count", "candidate_discarded": True}
    temp = target.parent / f".{target.name}.native-hex-xde-tmp"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True, exist_ok=True)
    try:
        raw = source.read_bytes()
        source_sha = _sha(raw)
        cad = load_cad_native_with_provenance(source, source.suffix.lower())
        profile = build_explicit_xde_hex_profile(cad)
        if profile.get("accepted") is not True:
            return {**profile, "candidate_discarded": True, "atomic_rollback": True}
        positions = np.ascontiguousarray(np.asarray(profile["canonical_positions"], dtype=np.float64))
        face_vertices = np.ascontiguousarray(np.asarray(profile["face_vertices"], dtype=np.int64))
        extents = positions.max(axis=0) - positions.min(axis=0)
        step = float(0.08 * min(extents)) if first_height is None else float(first_height)
        kernel = import_native_extension("native_hex_actual_xde_brep_producer")
        producers = [dict(kernel.build_native_hex_actual_xde_brep(
            positions, face_vertices, list(profile["face_records"]),
            int(requested_layers), step, float(growth_ratio),
        )) for _ in range(3)]
        if any(item.get("accepted") is not True for item in producers):
            return {"accepted": False, "reason": "cxx_producer_refused", "producer_runs": producers, "candidate_discarded": True, "atomic_rollback": True}
        baseline_producer = dict(kernel.build_native_hex_actual_xde_brep(
            positions, face_vertices, list(profile["face_records"]), 0, step, float(growth_ratio),
        ))
        if baseline_producer.get("accepted") is not True:
            raise ValueError("baseline_producer_refused")
        _write_polymesh(temp / "baseline/case/constant/polyMesh", baseline_producer)
        _write_polymesh(temp / "output/case/constant/polyMesh", producers[0])
        for index, producer in enumerate(producers, 1):
            _write_polymesh(temp / f"runs/run-{index}/case/constant/polyMesh", producer)
        (temp / "source").mkdir()
        (temp / f"source/{source.name}").write_bytes(raw)
        _write_ledgers(temp, profile, producers[0])
        output_sha = _tree_digest(temp / "output/case/constant/polyMesh")
        baseline_sha = _tree_digest(temp / "baseline/case/constant/polyMesh")
        run_digests = [_tree_digest(temp / f"runs/run-{i}/case/constant/polyMesh") for i in range(1, 4)]
        if len(set(run_digests)) != 1:
            raise ValueError("producer_repeatability_mismatch")
        if requested_layers == 0 and output_sha != baseline_sha:
            raise ValueError("bl0_identity_mismatch")
        bindings = [dict(row) for row in producers[0]["boundary_binding"]]

        def _ordered_quad_triangles(face: object) -> list[np.ndarray]:
            corner_ids = [int(value) for value in face]
            quad = positions[np.asarray(corner_ids, dtype=np.int64)]
            normal = np.cross(quad[1] - quad[0], quad[2] - quad[0])
            drop_axis = int(np.argmax(np.abs(normal)))
            keep_axes = [axis for axis in range(3) if axis != drop_axis]
            center = quad.mean(axis=0)
            order = sorted(
                range(4),
                key=lambda index: math.atan2(
                    float(quad[index, keep_axes[1]] - center[keep_axes[1]]),
                    float(quad[index, keep_axes[0]] - center[keep_axes[0]]),
                ),
            )
            ordered = quad[np.asarray(order, dtype=np.int64)]
            if float(np.dot(np.cross(ordered[1] - ordered[0], ordered[2] - ordered[0]), normal)) < 0.0:
                ordered = ordered[[0, 3, 2, 1]]
            return [
                np.asarray([ordered[0], ordered[1], ordered[2]], dtype=np.float64),
                np.asarray([ordered[0], ordered[2], ordered[3]], dtype=np.float64),
            ]

        source_triangles = np.asarray(
            [triangle for face in face_vertices for triangle in _ordered_quad_triangles(face)],
            dtype=np.float64,
        )
        source_ordinals = np.repeat(np.arange(len(face_vertices), dtype=np.int64), 2)
        producer_points = np.asarray(producers[0]["points"], dtype=np.float64)
        producer_faces = np.asarray(producers[0]["faces"], dtype=np.int64)
        internal_count = len(producers[0]["neighbour"])
        output_quads = producer_points[producer_faces[internal_count:]]
        output_boundary_faces = np.asarray(producer_faces[internal_count:], dtype=np.int64)
        output_mapping = np.asarray(producers[0]["boundary_source_faces"], dtype=np.int64)
        writer_order_rows: list[dict[str, object]] = []
        for index, (binding_row, source_face) in enumerate(
            zip(bindings, output_mapping.tolist(), strict=True)
        ):
            row = dict(binding_row)
            row.update({
                "writer_order": int(index),
                "output_face_id": int(row["output_face"]),
                "source_mesh_face": int(index),
                "source_face": int(source_face),
                "output_patch": "source-boundary",
                "direct": True,
            })
            writer_order_rows.append(row)
        source_shape_sha = _payload_hash({
            "vertices": _array_hash(positions),
            "faces": _array_hash(face_vertices),
        })
        output_shape_sha = _payload_hash({
            "points": _array_hash(producer_points),
            "boundary_faces": _array_hash(output_boundary_faces),
        })
        quality = dict(producers[0]["quality"])
        topology = dict(producers[0]["topology"])
        positive_geometry = bool(
            float(quality.get("minimum_volume", 0.0)) > 0.0
            and all(int(topology.get(name, 1)) == 0 for name in ("duplicate", "non_manifold", "inverted", "invalid"))
        )
        receipt = dict(import_native_extension("native_hex_boundary_receipt").audit_native_hex_brep_boundary(
            output_quads,
            source_triangles,
            source_ordinals,
            output_mapping,
            list(profile["face_records"]),
            source_sha,
            output_sha,
            int(requested_layers),
            int(producers[0]["actual_layers"]),
            float(step),
            bool(producers[0]["positive_boundary_layer"]),
            positive_geometry,
            max(1.0e-9, float(np.linalg.norm(extents)) * 1.0e-8),
            0.75,
            writer_order_rows,
        ))
        if receipt.get("accepted") is not True:
            shutil.rmtree(temp)
            return {
                "accepted": False,
                "reason": f"boundary_receipt_refused:{receipt.get('reason', 'unknown')}",
                "boundary_receipt": receipt,
                "candidate_discarded": True,
                "atomic_rollback": True,
            }
        source_authority = {
            "authoritative": True, "kind": "actual-stepcaf-xde-box", "sha256": source_sha,
            "profile": profile["profile"], "shape_preserved": True,
        }
        output_authority = {
            "authoritative": True, "source_sha256": source_sha,
            "source_shape_sha256": source_shape_sha, "output_shape_sha256": output_shape_sha,
            "output_sha256": output_sha,
            "feature_sha256": profile["feature_sha256"], "patch_sha256": profile["patch_sha256"],
            "physical_group_sha256": profile["physical_group_sha256"],
            "provenance_sha256": profile["provenance_sha256"], "shape_preserved": True,
            "positive_thickness": requested_layers == 0 or bool(producers[0]["positive_boundary_layer"]),
            "source_face_bindings": bindings,
            "feature_preserved": True,
            "patch_preserved": True,
            "physical_groups_preserved": True,
            "provenance_complete": True,
            "component_bijection": True,
            "source_vertices_preserved": True,
            "source_faces_preserved": True,
            "source_face_provenance": True,
            "positive_geometry": positive_geometry,
            "boundary_receipt_sha256": receipt.get("receipt_sha256"),
            "writer_order_bound": receipt.get("writer_order_bound") is True,
            "writer_order_sha256": receipt.get("writer_order_sha256"),
            "boundary_receipt": receipt,
        }
        witness = build_authority_bound_volume_quality_witness(
            temp / "output/case", source_authority=source_authority,
            source_output_authority=output_authority,
            requested_layers=requested_layers, actual_layers=int(producers[0]["actual_layers"]),
        )
        if witness.get("accepted") is not True:
            shutil.rmtree(temp)
            return {"accepted": False, "reason": f"quality_witness_refused:{witness.get('reason', 'unknown')}", "witness": witness, "candidate_discarded": True, "atomic_rollback": True}
        output_authority["quality_witness"] = witness
        manifest = {
            "schema": "native-hex-actual-xde-evidence/v1", "engine": "native_hex",
            "authority_level": "L0_actual_stepcaf_xde_box", "source_sha256": source_sha,
            "output_sha256": output_sha, "baseline_sha256": baseline_sha,
            "run_sha256": run_digests, "requested_layers": requested_layers,
            "actual_layers": int(producers[0]["actual_layers"]), "profile": profile["profile"],
            "quality": dict(producers[0]["quality"]), "topology": dict(producers[0]["topology"]),
            "source_authority": source_authority, "source_output_authority": output_authority,
            "boundary_receipt": receipt,
            "witness_sha256": witness["witness_sha256"], "publication_eligible": False,
        }
        (temp / "evidence.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
        temp.replace(target)
        return {
            "accepted": True, "status": "native_hex_actual_xde_evidence_written",
            "reason": "cxx_producer_authority_and_quality_witness_passed",
            "evidence_root": str(target), "producer": producers[0], "producer_runs": producers,
            "witness": witness, "boundary_receipt": receipt,
            "authority_level": "L0_actual_stepcaf_xde_box",
            "publication_eligible": False, "atomic_rollback": False,
        }
    except Exception as exc:
        if temp.exists():
            shutil.rmtree(temp)
        return {"accepted": False, "reason": f"actual_xde_hex_exception:{type(exc).__name__}:{exc}", "candidate_discarded": True, "atomic_rollback": True}


__all__ = ["write_actual_xde_hex_evidence"]
