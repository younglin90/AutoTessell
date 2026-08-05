"""Deterministic source inventory for shipped first-party C++ native modules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CORE = _ROOT / "auto_tessell_core"
_CONTRACT = _CORE / "native_build_contract.json"
_CMAKE = _CORE / "CMakeLists.txt"


@dataclass(frozen=True)
class _StaticAudit:
    binding_source: str
    lines: int
    forcecast_lines: int
    vector_lines: int
    request_lines: int
    mutable_data_lines: int


_EXPECTED: dict[str, _StaticAudit] = {
    "native_metrics": _StaticAudit("native_metrics_bind.cpp", 4866, 69, 89, 0, 5),
    "native_bl": _StaticAudit("native_bl_bind.cpp", 909, 13, 18, 0, 3),
    "native_polymesh": _StaticAudit("native_polymesh_bind.cpp", 2127, 14, 51, 0, 4),
    "native_poly_quality_relocation": _StaticAudit("native_poly_quality_relocation_bind.cpp", 509, 14, 27, 0, 0),
    "native_poly_bl_local_front_qopt": _StaticAudit("native_poly_bl_local_front_qopt_bind.cpp", 485, 16, 36, 0, 0),
    "native_snap": _StaticAudit("native_snap_bind.cpp", 512, 9, 3, 0, 0),
    "native_surface_padding": _StaticAudit(
        "native_surface_padding_bind.cpp", 271, 1, 14, 1, 0
    ),
    "native_hex_quality": _StaticAudit("native_hex_quality_bind.cpp", 1134, 12, 19, 1, 1),
    "native_tet_predicates": _StaticAudit(
        "native_tet_predicates_bind.cpp", 2886, 20, 71, 8, 0
    ),
    "native_tet_qopt": _StaticAudit("native_tet_qopt_bind.cpp", 810, 22, 38, 0, 0),
    "native_tri_quality_repair": _StaticAudit(
        "native_tri_quality_repair_bind.cpp", 487, 13, 55, 0, 0
    ),
    "native_hex_boundary_receipt": _StaticAudit(
        "native_hex_boundary_receipt_bind.cpp", 472, 4, 5, 0, 0
    ),
    "native_atomic_publish": _StaticAudit(
        "native_atomic_publish_bind.cpp", 154, 0, 1, 0, 0
    ),
    "native_bl_identity": _StaticAudit(
        "native_bl_identity_bind.cpp", 510, 0, 13, 0, 0
    ),
    "native_artifact_fingerprint": _StaticAudit(
        "native_artifact_fingerprint_bind.cpp", 139, 0, 6, 0, 0
    ),
}


def _line_count(source: str, token: str) -> int:
    return sum(token in line for line in source.splitlines())


def _audit(module: str, source_name: str) -> _StaticAudit:
    source = (_CORE / source_name).read_text(encoding="utf-8")
    return _StaticAudit(
        source_name,
        len(source.splitlines()),
        _line_count(source, "forcecast"),
        _line_count(source, "std::vector"),
        _line_count(source, "request()"),
        _line_count(source, "mutable_data"),
    )


def test_shipped_native_modules_have_frozen_python_boundary_static_inventory() -> None:
    contract = json.loads(_CONTRACT.read_text(encoding="utf-8"))

    assert set(contract["modules"]) == set(_EXPECTED)
    for module, expected in _EXPECTED.items():
        sources = contract["modules"][module]["sources"]
        assert f"auto_tessell_core/{expected.binding_source}" in sources
        assert _audit(module, expected.binding_source) == expected


def test_first_party_targets_explicitly_raise_cmake_global_cpp17_to_cpp23() -> None:
    cmake = _CMAKE.read_text(encoding="utf-8")

    assert "set(CMAKE_CXX_STANDARD 17)" in cmake
    assert "target_compile_features(${target_name} PRIVATE cxx_std_23)" in cmake
    assert "set_target_properties(${target_name} PROPERTIES CXX_EXTENSIONS OFF)" in cmake
    for module in _EXPECTED:
        assert f"pybind11_add_module({module}" in cmake
        assert f"autotessell_configure_first_party_native({module})" in cmake


def test_static_audit_priority_remains_measurement_not_refactor_authority() -> None:
    audits = {
        module: _audit(module, expected.binding_source)
        for module, expected in _EXPECTED.items()
    }

    assert max(audits, key=lambda module: audits[module].forcecast_lines) == "native_metrics"
    assert audits["native_tet_predicates"].request_lines == 8
    assert audits["native_surface_padding"].forcecast_lines == 1
