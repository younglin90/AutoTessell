"""Default-OFF atomic artifact writer for fixed-pair tri+quad products.

The writer persists the already-admitted separate triangle and quad arrays. It
does not route a product, convert quads to triangles, or invoke another
surface producer.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import numpy as np

from .tri_quad_fixed_pair_product_l0 import (
    TriQuadFixedPairProduct,
    TriQuadFixedPairProductResult,
)

_ENV = "AUTO_TESSELL_TRI_QUAD_FIXED_PAIR_WRITER_L0"
_SCHEMA = 1
_PRODUCER = "native_tri_quad_fixed_pair_writer_l0"
_MANIFEST = "manifest.json"
_ARRAYS = {
    "vertices": "vertices.npy",
    "triangles": "triangles.npy",
    "quads": "quads.npy",
    "triangle_source_indices": "triangle_source_indices.npy",
    "quad_source_pairs": "quad_source_pairs.npy",
}


@dataclass(frozen=True, slots=True)
class TriQuadFixedPairWriterResult:
    """Explicit artifact outcome; successful writing does not promote a route."""

    written: bool
    status: str
    rejection_reason: str | None
    artifact_path: Path | None
    content_sha256: str | None
    manifest_sha256: str | None
    readback_verified: bool
    product_claimed: bool = False
    contract: str = "tri_quad_fixed_pair_writer_l0"


def tri_quad_fixed_pair_writer_l0_enabled() -> bool:
    """Return whether the disconnected artifact writer was explicitly enabled."""
    return os.environ.get(_ENV) == "1"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_sha256(files: dict[str, dict[str, object]]) -> str:
    digest = sha256()
    for name in sorted(files):
        digest.update(name.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(files[name]["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _owned_stage(path: Path, parent: Path, prefix: str) -> bool:
    return path.parent == parent and path.name.startswith(prefix) and not path.is_symlink()


def _cleanup_owned_stage(path: Path | None, parent: Path, prefix: str) -> None:
    if path is not None and path.exists() and _owned_stage(path, parent, prefix):
        shutil.rmtree(path)


def _target_path(value: object) -> tuple[Path, Path] | None:
    if not isinstance(value, (str, Path)):
        return None
    requested = Path(value)
    if requested.name in {"", ".", ".."} or requested.parent.is_symlink():
        return None
    parent = requested.parent.resolve(strict=False)
    if not parent.is_dir() or parent.is_symlink():
        return None
    target = parent / requested.name
    if target.exists() or target.is_symlink():
        return None
    return parent, target


def _write_array(path: Path, values: np.ndarray) -> dict[str, object]:
    np.save(path, values, allow_pickle=False)
    _fsync_file(path)
    return {
        "file": path.name,
        "dtype": values.dtype.str,
        "shape": list(values.shape),
        "sha256": _file_sha256(path),
    }


def _manifest(product: TriQuadFixedPairProduct, files: dict[str, dict[str, object]]) -> dict[str, object]:
    return {
        "schema": _SCHEMA,
        "producer": _PRODUCER,
        "product_contract": product.contract,
        "source": {
            "vertices_sha256": product.source_vertices_hash,
            "triangles_sha256": product.source_triangles_hash,
            "patch_sha256": product.source_patch_hash,
            "physical_group_sha256": product.source_physical_group_hash,
            "feature_sha256": product.feature_hash,
        },
        "provenance": {
            "triangle_source_indices_file": _ARRAYS["triangle_source_indices"],
            "quad_source_pairs_file": _ARRAYS["quad_source_pairs"],
        },
        "payloads": {
            "triangle_patch_ids": list(product.triangle_patch_ids),
            "quad_patch_ids": list(product.quad_patch_ids),
            "triangle_physical_groups": list(product.triangle_physical_groups),
            "quad_physical_groups": list(product.quad_physical_groups),
        },
        "arrays": files,
        "content_sha256": _content_sha256(files),
    }


def _expected_arrays(product: TriQuadFixedPairProduct) -> dict[str, np.ndarray]:
    return {
        "vertices": product.vertices,
        "triangles": product.triangles,
        "quads": product.quads,
        "triangle_source_indices": product.triangle_source_indices,
        "quad_source_pairs": product.quad_source_pairs,
    }


def _readback(stage: Path, product: TriQuadFixedPairProduct) -> tuple[str, str] | None:
    manifest_path = stage / _MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema", "producer", "product_contract", "source", "provenance", "payloads", "arrays", "content_sha256",
    }:
        return None
    if (
        manifest["schema"] != _SCHEMA
        or manifest["producer"] != _PRODUCER
        or manifest["product_contract"] != product.contract
        or not isinstance(manifest["arrays"], dict)
        or not isinstance(manifest["content_sha256"], str)
    ):
        return None
    arrays = manifest["arrays"]
    expected = _expected_arrays(product)
    if set(arrays) != set(expected) or manifest["content_sha256"] != _content_sha256(arrays):
        return None
    expected_paths = {_MANIFEST}
    for name, values in expected.items():
        metadata = arrays.get(name)
        if not isinstance(metadata, dict) or set(metadata) != {"file", "dtype", "shape", "sha256"}:
            return None
        if metadata["file"] != _ARRAYS[name] or metadata["dtype"] != values.dtype.str or metadata["shape"] != list(values.shape):
            return None
        path = stage / _ARRAYS[name]
        expected_paths.add(path.name)
        if path.is_symlink() or not path.is_file() or _file_sha256(path) != metadata["sha256"]:
            return None
        try:
            loaded = np.load(path, allow_pickle=False)
        except (OSError, ValueError):
            return None
        if not isinstance(loaded, np.ndarray) or loaded.dtype != values.dtype or loaded.shape != values.shape:
            return None
        if loaded.tobytes() != values.tobytes():
            return None
    if {path.name for path in stage.iterdir()} != expected_paths:
        return None
    if manifest["source"] != {
        "vertices_sha256": product.source_vertices_hash,
        "triangles_sha256": product.source_triangles_hash,
        "patch_sha256": product.source_patch_hash,
        "physical_group_sha256": product.source_physical_group_hash,
        "feature_sha256": product.feature_hash,
    }:
        return None
    if manifest["provenance"] != {
        "triangle_source_indices_file": _ARRAYS["triangle_source_indices"],
        "quad_source_pairs_file": _ARRAYS["quad_source_pairs"],
    }:
        return None
    if manifest["payloads"] != {
        "triangle_patch_ids": list(product.triangle_patch_ids),
        "quad_patch_ids": list(product.quad_patch_ids),
        "triangle_physical_groups": list(product.triangle_physical_groups),
        "quad_physical_groups": list(product.quad_physical_groups),
    }:
        return None
    return str(manifest["content_sha256"]), _file_sha256(manifest_path)


def write_tri_quad_fixed_pair_product_l0(
    product_result: object,
    target_directory: object,
) -> TriQuadFixedPairWriterResult:
    """Atomically publish one admitted mixed product to a fresh directory."""
    if not tri_quad_fixed_pair_writer_l0_enabled():
        return TriQuadFixedPairWriterResult(False, "reject_tri_quad_fixed_pair_writer_disabled", "tri_quad_fixed_pair_writer_l0_disabled", None, None, None, False)
    if (
        not isinstance(product_result, TriQuadFixedPairProductResult)
        or not product_result.accepted
        or not product_result.transaction_applied
        or product_result.product is None
    ):
        return TriQuadFixedPairWriterResult(False, "reject_tri_quad_fixed_pair_writer_product", "accepted_tri_quad_fixed_pair_product_required", None, None, None, False)
    resolved = _target_path(target_directory)
    if resolved is None:
        return TriQuadFixedPairWriterResult(False, "reject_tri_quad_fixed_pair_writer_target", "fresh_real_target_directory_required", None, None, None, False)
    parent, target = resolved
    prefix = f".{target.name}.stage."
    stage: Path | None = None
    try:
        stage = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
        os.chmod(stage, 0o700)
        product = product_result.product
        files = {
            name: _write_array(stage / filename, values)
            for name, filename in _ARRAYS.items()
            for values in (_expected_arrays(product)[name],)
        }
        manifest = _manifest(product, files)
        manifest_path = stage / _MANIFEST
        manifest_path.write_bytes(_canonical_json(manifest))
        _fsync_file(manifest_path)
        _fsync_directory(stage)
        readback = _readback(stage, product)
        if readback is None:
            return TriQuadFixedPairWriterResult(False, "reject_tri_quad_fixed_pair_writer_readback", "artifact_readback_verification_failed", None, None, None, False)
        content_hash, manifest_hash = readback
        if target.exists() or target.is_symlink():
            return TriQuadFixedPairWriterResult(False, "reject_tri_quad_fixed_pair_writer_target", "fresh_real_target_directory_required", None, None, None, False)
        os.replace(stage, target)
        stage = None
        _fsync_directory(parent)
        return TriQuadFixedPairWriterResult(True, "pass_tri_quad_fixed_pair_writer_unrouted", None, target, content_hash, manifest_hash, True)
    except (OSError, ValueError, TypeError):
        return TriQuadFixedPairWriterResult(False, "reject_tri_quad_fixed_pair_writer_io", "artifact_write_failed", None, None, None, False)
    finally:
        _cleanup_owned_stage(stage, parent, prefix)


__all__ = [
    "TriQuadFixedPairWriterResult",
    "tri_quad_fixed_pair_writer_l0_enabled",
    "write_tri_quad_fixed_pair_product_l0",
]
