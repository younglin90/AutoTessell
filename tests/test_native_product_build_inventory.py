"""Fail-closed clean-install inventory for tri/quad native C++23 diagnostics."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CMAKE = ROOT / "auto_tessell_core" / "CMakeLists.txt"
SHIPPED_CONTRACT = ROOT / "auto_tessell_core" / "native_build_contract.json"
DIAGNOSTIC_CONTRACT = ROOT / "auto_tessell_core" / "native_surface_product_build_contract.json"


def _first_party_targets(cmake: str) -> list[str]:
    match = re.search(
        r"set\(_AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS(?P<body>.*?)\)",
        cmake,
        flags=re.DOTALL,
    )
    assert match is not None, "first-party native target inventory is missing"
    targets = re.findall(r"^\s*(native_[a-z0-9_]+)\s*$", match.group("body"), re.MULTILINE)
    targets.extend(re.findall(
        r"list\(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS (native_[a-z0-9_]+)\)",
        cmake,
    ))
    return targets


def test_clean_install_inventory_equals_shipped_abi_contract() -> None:
    cmake = CMAKE.read_text(encoding="utf-8")
    shipped = json.loads(SHIPPED_CONTRACT.read_text(encoding="utf-8"))["modules"]
    targets = _first_party_targets(cmake)

    assert set(targets) == set(shipped)
    assert len(targets) == 15
    assert len(targets) == len(set(targets))
    assert "native_metrics" in targets
    assert "triangle_surface_topology_audit" in shipped["native_metrics"]["public_symbols"]
    assert "strict_quad_pair_preflight" in shipped["native_metrics"]["public_symbols"]
    assert "install(TARGETS ${_AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS}" in cmake
    assert "DEPENDS\n      ${_AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS}" in cmake


def test_surface_product_diagnostic_is_default_off_and_not_installable() -> None:
    cmake = CMAKE.read_text(encoding="utf-8")
    diagnostic = json.loads(DIAGNOSTIC_CONTRACT.read_text(encoding="utf-8"))
    build_definitions = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "scikit-build"
    ]["cmake"]["define"]

    assert diagnostic["module"] == "native_surface_product"
    assert diagnostic["shipping"] is False
    assert diagnostic["runtime"] == "report_only_default_off"
    assert 'option(BUILD_NATIVE_SURFACE_PRODUCT\n  "Build report-only native surface product evaluator" OFF)' in cmake
    assert "native_surface_product" not in _first_party_targets(cmake)
    assert "BUILD_NATIVE_SURFACE_PRODUCT" not in build_definitions
