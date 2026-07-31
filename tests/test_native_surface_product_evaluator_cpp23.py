"""L0 contract tests for the default-OFF native surface product evaluator."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "auto_tessell_core" / "native_surface_product_build_contract.json"
CMAKE = ROOT / "auto_tessell_core" / "CMakeLists.txt"


def _module_or_skip():
    build_dir = os.environ.get("AUTOTESSELL_SURFACE_PRODUCT_BUILD_DIR")
    if build_dir and build_dir not in sys.path:
        sys.path.insert(0, build_dir)
    try:
        return importlib.import_module("native_surface_product")
    except ModuleNotFoundError:
        pytest.skip("native_surface_product is a default-OFF explicit CMake target")


def _indices(rows: list[list[int]], columns: int) -> np.ndarray:
    values = np.asarray(rows, dtype=np.int64).reshape((-1, columns))
    values.setflags(write=False)
    return values


def test_contract_is_explicit_default_off_and_not_shipped_inventory() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    cmake = CMAKE.read_text(encoding="utf-8")

    assert contract == {
        "schema": 1,
        "module": "native_surface_product",
        "shipping": False,
        "runtime": "report_only_default_off",
        "public_symbols": ["evaluate_surface_product"],
        "sources": ["auto_tessell_core/native_surface_product_bind.cpp"],
    }
    assert 'option(BUILD_NATIVE_SURFACE_PRODUCT\n  "Build report-only native surface product evaluator" OFF)' in cmake
    assert "if(BUILD_NATIVE_SURFACE_PRODUCT)" in cmake
    assert "pybind11_add_module(native_surface_product native_surface_product_bind.cpp)" in cmake
    first_party_targets = cmake.split("set(_AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS", 1)[1].split(")", 1)[0]
    assert "native_surface_product" not in first_party_targets


@pytest.mark.parametrize(
    ("triangles", "quads", "vertex_count", "classification"),
    [
        (_indices([[0, 1, 2]], 3), _indices([], 4), 3, "tri"),
        (_indices([], 3), _indices([[0, 1, 2, 3]], 4), 4, "quad"),
        (
            _indices([[0, 1, 2]], 3),
            _indices([[0, 1, 2, 3]], 4),
            4,
            "tri_quad",
        ),
    ],
)
def test_product_classes_are_distinct_and_deterministic(
    triangles: np.ndarray,
    quads: np.ndarray,
    vertex_count: int,
    classification: str,
) -> None:
    subject = _module_or_skip()
    before = (triangles.tobytes(), quads.tobytes())
    reports = [subject.evaluate_surface_product(triangles, quads, vertex_count) for _ in range(3)]

    assert reports[0] == reports[1] == reports[2]
    report = reports[0]
    assert report["classification"] == classification
    assert report["local_topology_valid"] is True
    assert report["product_accepted"] is False
    assert report["product_rejection"] == "source_product_certificate_required"
    assert report["triangle_count"] == triangles.shape[0]
    assert report["quad_count"] == quads.shape[0]
    assert report["triangles_immutable"] is True
    assert report["quads_immutable"] is True
    assert (triangles.tobytes(), quads.tobytes()) == before


@pytest.mark.parametrize(
    ("triangles", "quads", "vertex_count"),
    [
        (_indices([], 3), _indices([], 4), 0),
        (_indices([[0, 0, 2]], 3), _indices([], 4), 3),
        (_indices([], 3), _indices([[0, 1, 2, 4]], 4), 4),
    ],
)
def test_invalid_topology_is_reported_not_repaired(
    triangles: np.ndarray, quads: np.ndarray, vertex_count: int
) -> None:
    subject = _module_or_skip()
    report = subject.evaluate_surface_product(triangles, quads, vertex_count)

    assert report["classification"] == "invalid"
    assert report["local_topology_valid"] is False
    assert report["product_accepted"] is False
    assert report["product_rejection"] == "source_product_certificate_required"


def test_nonconforming_arrays_are_rejected_without_conversion() -> None:
    subject = _module_or_skip()
    readonly_quad = _indices([[0, 1, 2, 3]], 4)
    wrong_dtype = np.asarray([[0, 1, 2]], dtype=np.int32)
    wrong_dtype.setflags(write=False)
    writable_tri = np.asarray([[0, 1, 2]], dtype=np.int64)
    noncontiguous_tri = np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int64)[:, ::-1]
    noncontiguous_tri.setflags(write=False)

    with pytest.raises(TypeError, match="dtype int64"):
        subject.evaluate_surface_product(wrong_dtype, readonly_quad, 4)
    with pytest.raises(ValueError, match="read-only"):
        subject.evaluate_surface_product(writable_tri, readonly_quad, 4)
    with pytest.raises(ValueError, match="C-contiguous"):
        subject.evaluate_surface_product(noncontiguous_tri, readonly_quad, 6)
    with pytest.raises(ValueError, match="non-negative"):
        subject.evaluate_surface_product(_indices([], 3), readonly_quad, -1)
