"""Default-OFF atomic writer for admitted fixed-pair strict-quad products.

The artifact is strict quad only: it contains no triangle array and never
routes, converts, or delegates the product to another surface representation.
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

from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductClassification,
)

from .strict_pair_product_l0 import (
    StrictQuadFixedPairProduct,
    StrictQuadFixedPairProductResult,
)

_ENV = "AUTO_TESSELL_STRICT_QUAD_FIXED_PAIR_WRITER_L0"
_SCHEMA = 1
_PRODUCER = "native_strict_quad_fixed_pair_writer_l0"
_MANIFEST = "manifest.json"
_ARRAYS = {
    "vertices": "vertices.npy",
    "quads": "quads.npy",
    "quad_source_pairs": "quad_source_pairs.npy",
}


@dataclass(frozen=True, slots=True)
class StrictQuadFixedPairWriterResult:
    """Artifact outcome; publication never selects a route or UI product."""

    written: bool
    status: str
    rejection_reason: str | None
    artifact_path: Path | None
    content_sha256: str | None
    manifest_sha256: str | None
    readback_verified: bool
    product_claimed: bool = False
    contract: str = "strict_quad_fixed_pair_writer_l0"


def strict_quad_fixed_pair_writer_l0_enabled() -> bool:
    """Return whether the strict-only artifact writer was explicitly enabled."""
    return os.environ.get(_ENV) == "1"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    digest = sha256()
    digest.update(str(values.dtype).encode("ascii"))
    digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
    digest.update(values.tobytes())
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


def _owned_stage(path: Path, parent: Path, prefix: str) -> bool:
    return path.parent == parent and path.name.startswith(prefix) and not path.is_symlink()


def _cleanup_owned_stage(path: Path | None, parent: Path, prefix: str) -> None:
    if path is not None and path.exists() and _owned_stage(path, parent, prefix):
        shutil.rmtree(path)


def _expected_arrays(product: StrictQuadFixedPairProduct) -> dict[str, np.ndarray]:
    return {
        "vertices": product.vertices,
        "quads": product.quads,
        "quad_source_pairs": product.quad_source_pairs,
    }


def _accepted_strict_product(value: object) -> StrictQuadFixedPairProduct | None:
    if (
        not isinstance(value, StrictQuadFixedPairProductResult)
        or not value.accepted
        or value.product is None
        or value.product_certificate is None
        or not value.product_certificate.accepted
        or value.product_certificate.classification is not SurfaceProductClassification.STRICT_QUAD
    ):
        return None
    product = value.product
    arrays = _expected_arrays(product)
    if (
        product.contract != "strict_quad_fixed_pair_product_l0"
        or product.triangles.dtype != np.dtype(np.int64)
        or product.triangles.shape != (0, 3)
        or not product.triangles.flags.c_contiguous
        or any(
            values.dtype != dtype
            or values.ndim != 2
            or values.shape[1] != columns
            or not values.flags.c_contiguous
            for values, dtype, columns in (
                (arrays["vertices"], np.dtype(np.float64), 3),
                (arrays["quads"], np.dtype(np.int64), 4),
                (arrays["quad_source_pairs"], np.dtype(np.int64), 2),
            )
        )
        or len(product.quads) == 0
        or len(product.quads) != len(product.quad_source_pairs)
        or len(product.quads) != len(product.quad_patch_ids)
        or len(product.quads) != len(product.quad_physical_groups)
        or any(
            not isinstance(group, str) or not group.strip()
            for group in product.quad_physical_groups
        )
        or product.quads_hash != _array_sha256(product.quads)
        or product.pair_provenance_hash != _array_sha256(product.quad_source_pairs)
        or not all(
            isinstance(digest, str) and len(digest) == 64
            for digest in (
                product.source_vertices_hash,
                product.source_triangles_hash,
                product.quads_hash,
                product.pair_provenance_hash,
                product.feature_hash,
                product.source_patch_hash,
                product.source_physical_group_hash,
            )
        )
    ):
        return None
    return product


def _write_array(path: Path, values: np.ndarray) -> dict[str, object]:
    np.save(path, values, allow_pickle=False)
    _fsync_file(path)
    return {
        "file": path.name,
        "dtype": values.dtype.str,
        "shape": list(values.shape),
        "sha256": _file_sha256(path),
    }


def _manifest(
    product: StrictQuadFixedPairProduct,
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema": _SCHEMA,
        "producer": _PRODUCER,
        "product_contract": product.contract,
        "strict_quad": {"triangle_count": 0, "quad_count": len(product.quads)},
        "source": {
            "vertices_sha256": product.source_vertices_hash,
            "triangles_sha256": product.source_triangles_hash,
            "patch_sha256": product.source_patch_hash,
            "physical_group_sha256": product.source_physical_group_hash,
            "feature_sha256": product.feature_hash,
        },
        "provenance": {
            "quad_source_pairs_file": _ARRAYS["quad_source_pairs"],
            "quad_source_pairs_sha256": product.pair_provenance_hash,
            "quads_sha256": product.quads_hash,
        },
        "payloads": {
            "quad_patch_ids": list(product.quad_patch_ids),
            "quad_physical_groups": list(product.quad_physical_groups),
        },
        "arrays": files,
        "content_sha256": _content_sha256(files),
    }


def _readback(stage: Path, product: StrictQuadFixedPairProduct) -> tuple[str, str] | None:
    manifest_path = stage / _MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    expected = _expected_arrays(product)
    if (
        not isinstance(manifest, dict)
        or set(manifest)
        != {
            "schema",
            "producer",
            "product_contract",
            "strict_quad",
            "source",
            "provenance",
            "payloads",
            "arrays",
            "content_sha256",
        }
        or manifest["schema"] != _SCHEMA
        or manifest["producer"] != _PRODUCER
        or manifest["product_contract"] != product.contract
        or manifest["strict_quad"] != {"triangle_count": 0, "quad_count": len(product.quads)}
        or not isinstance(manifest["arrays"], dict)
        or manifest["content_sha256"] != _content_sha256(manifest["arrays"])
    ):
        return None
    expected_paths = {_MANIFEST}
    for name, values in expected.items():
        metadata = manifest["arrays"].get(name)
        if not isinstance(metadata, dict) or set(metadata) != {"file", "dtype", "shape", "sha256"}:
            return None
        if (
            metadata["file"] != _ARRAYS[name]
            or metadata["dtype"] != values.dtype.str
            or metadata["shape"] != list(values.shape)
        ):
            return None
        path = stage / _ARRAYS[name]
        expected_paths.add(path.name)
        if path.is_symlink() or not path.is_file() or _file_sha256(path) != metadata["sha256"]:
            return None
        try:
            loaded = np.load(path, allow_pickle=False)
        except (OSError, ValueError):
            return None
        if (
            not isinstance(loaded, np.ndarray)
            or loaded.dtype != values.dtype
            or loaded.shape != values.shape
            or loaded.tobytes() != values.tobytes()
        ):
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
        "quad_source_pairs_file": _ARRAYS["quad_source_pairs"],
        "quad_source_pairs_sha256": product.pair_provenance_hash,
        "quads_sha256": product.quads_hash,
    }:
        return None
    if manifest["payloads"] != {
        "quad_patch_ids": list(product.quad_patch_ids),
        "quad_physical_groups": list(product.quad_physical_groups),
    }:
        return None
    return str(manifest["content_sha256"]), _file_sha256(manifest_path)


def write_strict_quad_fixed_pair_product_l0(
    product_result: object,
    target_directory: object,
) -> StrictQuadFixedPairWriterResult:
    """Atomically publish one admitted strict-quad product to a fresh directory."""
    if not strict_quad_fixed_pair_writer_l0_enabled():
        return StrictQuadFixedPairWriterResult(
            False,
            "reject_strict_quad_fixed_pair_writer_disabled",
            "strict_quad_fixed_pair_writer_l0_disabled",
            None,
            None,
            None,
            False,
        )
    product = _accepted_strict_product(product_result)
    if product is None:
        return StrictQuadFixedPairWriterResult(
            False,
            "reject_strict_quad_fixed_pair_writer_product",
            "accepted_strict_quad_fixed_pair_product_required",
            None,
            None,
            None,
            False,
        )
    resolved = _target_path(target_directory)
    if resolved is None:
        return StrictQuadFixedPairWriterResult(
            False,
            "reject_strict_quad_fixed_pair_writer_target",
            "fresh_real_target_directory_required",
            None,
            None,
            None,
            False,
        )
    parent, target = resolved
    prefix = f".{target.name}.stage."
    stage: Path | None = None
    try:
        stage = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
        os.chmod(stage, 0o700)
        files = {
            name: _write_array(stage / filename, values)
            for name, filename in _ARRAYS.items()
            for values in (_expected_arrays(product)[name],)
        }
        manifest_path = stage / _MANIFEST
        manifest_path.write_bytes(_canonical_json(_manifest(product, files)))
        _fsync_file(manifest_path)
        _fsync_directory(stage)
        readback = _readback(stage, product)
        if readback is None:
            return StrictQuadFixedPairWriterResult(
                False,
                "reject_strict_quad_fixed_pair_writer_readback",
                "artifact_readback_verification_failed",
                None,
                None,
                None,
                False,
            )
        content_hash, manifest_hash = readback
        if target.exists() or target.is_symlink():
            return StrictQuadFixedPairWriterResult(
                False,
                "reject_strict_quad_fixed_pair_writer_target",
                "fresh_real_target_directory_required",
                None,
                None,
                None,
                False,
            )
        os.replace(stage, target)
        stage = None
        _fsync_directory(parent)
        return StrictQuadFixedPairWriterResult(
            True,
            "pass_strict_quad_fixed_pair_writer_unrouted",
            None,
            target,
            content_hash,
            manifest_hash,
            True,
        )
    except (OSError, TypeError, ValueError):
        return StrictQuadFixedPairWriterResult(
            False,
            "reject_strict_quad_fixed_pair_writer_io",
            "artifact_write_failed",
            None,
            None,
            None,
            False,
        )
    finally:
        _cleanup_owned_stage(stage, parent, prefix)


__all__ = [
    "StrictQuadFixedPairWriterResult",
    "strict_quad_fixed_pair_writer_l0_enabled",
    "write_strict_quad_fixed_pair_product_l0",
]


def readback_strict_quad_fixed_pair_artifact(stage: Path, product: StrictQuadFixedPairProduct) -> tuple[str, str] | None:
    """Public read-only wrapper around the writer's fail-closed read-back."""
    return _readback(Path(stage), product)
