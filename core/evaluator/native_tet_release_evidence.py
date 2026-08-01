"""Measured Native Tet source/feature/patch authority adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from core.evaluator.volume_source_output_certificate import (
    VolumeSourceOutputCertificate,
    certify_volume_source_output,
)
from core.utils.polymesh_reader import parse_foam_boundary


def certify_native_tet_release_output(
    case_dir: Path,
    source_path: Path,
    source_vertices: object,
    source_faces: object,
    output_points: object,
    output_tets: object,
    *,
    source_feature_ids: Sequence[object],
    source_patch_ids: Sequence[object],
    source_physical_groups: Sequence[str],
    debug_info: object,
) -> VolumeSourceOutputCertificate:
    """Bind a strict Tet artifact to measured source-topology evidence.

    The strict source audit is the authority for component/face preservation;
    this adapter only turns its measured counters and the written boundary
    patch table into the common Gate4 certificate.  It never infers missing
    declarations.
    """
    debug = debug_info if isinstance(debug_info, dict) else {}
    component = debug.get("strict_source_component_bijection")
    topology = debug.get("strict_source_topology")
    if not isinstance(component, dict) or not isinstance(topology, dict):
        return certify_volume_source_output(
            source_path, source_vertices, source_faces, output_points, output_tets,
            source_feature_ids=source_feature_ids,
            source_patch_ids=source_patch_ids,
            source_physical_groups=source_physical_groups,
            provenance={"status": "missing_strict_source_evidence"},
            source_vertices_preserved=False,
            source_faces_preserved=False,
            feature_preserved=False,
            patch_preserved=False,
            physical_groups_preserved=False,
            component_bijection=False,
            provenance_complete=False,
        )

    try:
        patches = parse_foam_boundary(case_dir / "constant" / "polyMesh" / "boundary")
    except Exception:
        patches = []
    declared_patches = tuple(str(value) for value in source_patch_ids)
    declared_groups = tuple(str(value) for value in source_physical_groups)
    one_wall_declaration = (
        len(declared_patches) == len(declared_groups) > 0
        and len(set(declared_patches)) == 1
        and len(set(declared_groups)) == 1
    )
    output_patch_names = tuple(
        str(patch.get("name"))
        for patch in patches
        if isinstance(patch, dict) and isinstance(patch.get("name"), str)
    )
    patch_bound = bool(output_patch_names) and all(name == "defaultWall" or name.startswith("wall_") for name in output_patch_names)
    source_vertices_preserved = (
        component.get("n_missing_source_vertices") == 0
        and component.get("n_source_vertices_on_boundary")
        == component.get("n_source_surface_vertices")
    )
    source_faces_preserved = topology.get("source_faces_preserved") is True
    component_bijection = (
        component.get("bijective") is True
        and topology.get("component_bijective") is True
    )
    feature_preserved = component.get("n_feature_boundary_mismatches") == 0
    patch_preserved = one_wall_declaration and patch_bound
    physical_groups_preserved = one_wall_declaration and patch_bound
    provenance_complete = bool(
        topology.get("valid") is True
        and source_faces_preserved
        and component_bijection
    )
    return certify_volume_source_output(
        source_path, source_vertices, source_faces, output_points, output_tets,
        source_feature_ids=source_feature_ids,
        source_patch_ids=source_patch_ids,
        source_physical_groups=source_physical_groups,
        provenance={
            "strict_source_component_bijection": component,
            "strict_source_topology": topology,
            "output_patch_names": output_patch_names,
        },
        source_vertices_preserved=source_vertices_preserved,
        source_faces_preserved=source_faces_preserved,
        feature_preserved=feature_preserved,
        patch_preserved=patch_preserved,
        physical_groups_preserved=physical_groups_preserved,
        component_bijection=component_bijection,
        provenance_complete=provenance_complete,
    )


__all__ = ["certify_native_tet_release_output"]
