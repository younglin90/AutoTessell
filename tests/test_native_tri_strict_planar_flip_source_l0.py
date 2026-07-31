from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_tri.strict_planar_flip_source_l0 import (
    AuthoritativeNativeTriFeatureEdges,
    AuthoritativeNativeTriPatchIds,
    StrictPlanarFlipSourceRequest,
    ingest_strict_planar_flip_source_l0,
)


def _array_hash(values: np.ndarray) -> str:
    digest = sha256()
    digest.update(str(values.dtype).encode("ascii"))
    digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
    digest.update(values.tobytes())
    return digest.hexdigest()


def _request(tmp_path: Path) -> StrictPlanarFlipSourceRequest:
    path = tmp_path / "source.stl"
    path.write_text(
        """solid source
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 2 1 0
 endloop
endfacet
facet normal 0 0 1
 outer loop
  vertex 1 0 0
  vertex 0 1 0
  vertex 2 1 0
 endloop
endfacet
endsolid source
""",
        encoding="utf-8",
    )
    mesh = read_stl(path)
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    return StrictPlanarFlipSourceRequest(
        source_path=path,
        source_sha256=sha256(path.read_bytes()).hexdigest(),
        vertices_sha256=_array_hash(vertices),
        faces_sha256=_array_hash(faces),
        patch_ids=AuthoritativeNativeTriPatchIds(("wall", "wall"), True),
        feature_edges=AuthoritativeNativeTriFeatureEdges((), True),
        physical_groups=AuthoritativePhysicalGroupMapping(("wall", "wall"), True),
    )


def test_source_locked_test_authority_admits_immutable_reader_arrays(tmp_path: Path) -> None:
    result = ingest_strict_planar_flip_source_l0(_request(tmp_path))

    assert result.accepted and result.source is not None
    assert result.status == "pass_strict_planar_flip_source_test_authority"
    assert result.source.contract == "strict_planar_flip_source_l0_test_authority"
    assert not result.source.vertices.flags.writeable
    assert not result.source.faces.flags.writeable
    assert result.source.patch_ids == ("wall", "wall")
    assert result.source.physical_groups == ("wall", "wall")


def test_hash_array_and_authority_mismatches_fail_closed(tmp_path: Path) -> None:
    request = _request(tmp_path)
    mismatches = (
        replace(request, source_sha256="0" * 64),
        replace(request, vertices_sha256="0" * 64),
        replace(request, faces_sha256="0" * 64),
        replace(request, patch_ids=AuthoritativeNativeTriPatchIds(("wall",), True)),
        replace(request, feature_edges=AuthoritativeNativeTriFeatureEdges(((1, 0),), True)),
        replace(
            request, physical_groups=AuthoritativePhysicalGroupMapping(("wall", "wall"), False)
        ),
    )
    for invalid in mismatches:
        result = ingest_strict_planar_flip_source_l0(invalid)
        assert result.accepted is False and result.source is None
        assert result.status == "reject_strict_planar_flip_source"


def test_mutated_source_bytes_after_declaration_fail_closed(tmp_path: Path) -> None:
    request = _request(tmp_path)
    source_path = Path(request.source_path)
    source_path.write_bytes(source_path.read_bytes() + b"\n")

    result = ingest_strict_planar_flip_source_l0(request)

    assert result.status == "reject_strict_planar_flip_source"
    assert result.rejection_reason == "strict_planar_flip_source_binding_mismatch"
    assert result.source is None
