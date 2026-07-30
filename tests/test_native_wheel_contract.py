"""Static release contract for the isolated first-party native wheel."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from scripts.smoke_native_wheel import EXPECTED_MODULES, FORBIDDEN_MODULES

ROOT = Path(__file__).resolve().parents[1]


def test_scikit_build_profile_enables_exact_first_party_set() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["build-system"]["build-backend"] == "scikit_build_core.build"
    assert any(
        requirement.startswith("scikit-build-core>=1.0,<2")
        for requirement in config["build-system"]["requires"]
    )
    settings = config["tool"]["scikit-build"]
    assert settings["cmake"]["source-dir"] == "auto_tessell_core"
    assert settings["wheel"]["packages"] == ["cli", "core", "desktop"]
    assert config["project"]["license"] == "GPL-3.0-or-later"
    assert config["project"]["license-files"] == ["LICENSE", "NOTICE"]
    assert "license-files" not in settings["wheel"]
    definitions = settings["cmake"]["define"]
    assert definitions["AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE"] == "ON"
    for module in EXPECTED_MODULES:
        option = "BUILD_" + module.removeprefix("native_").upper()
        if module == "native_surface_padding":
            option = "BUILD_NATIVE_SURFACE_PADDING"
        elif module == "native_tet_predicates":
            option = "BUILD_NATIVE_TET_PREDICATES"
        elif module == "native_tet_qopt":
            option = "BUILD_NATIVE_TET_QOPT"
        elif module == "native_hex_quality":
            option = "BUILD_NATIVE_HEX_QUALITY"
        elif module == "native_polymesh":
            option = "BUILD_NATIVE_POLYMESH"
        elif module == "native_metrics":
            option = "BUILD_NATIVE_METRICS"
        elif module == "native_snap":
            option = "BUILD_NATIVE_SNAP"
        elif module == "native_bl":
            option = "BUILD_NATIVE_BL"
        assert definitions[option] == "ON"
    for option in ("BUILD_CINOLIB_HEX", "BUILD_ROBUSTHEX", "BUILD_FTETWILD", "BUILD_CFMESH"):
        assert definitions[option] == "OFF"


def test_cmake_install_contract_and_adapter_exclusion() -> None:
    cmake = (ROOT / "auto_tessell_core/CMakeLists.txt").read_text(encoding="utf-8")
    assert "function(autotessell_configure_first_party_native target_name)" in cmake
    assert "CXX_EXTENSIONS OFF" in cmake
    assert "cxx_std_23" in cmake
    assert "find_package(Boost REQUIRED)" in cmake
    assert "target_link_libraries(native_tet_predicates PRIVATE Boost::headers)" in cmake
    assert "AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE" in cmake
    for option in ("BUILD_CINOLIB_HEX", "BUILD_ROBUSTHEX", "BUILD_FTETWILD", "BUILD_CFMESH"):
        assert f"set({option} OFF CACHE BOOL \"\" FORCE)" in cmake
    for module in EXPECTED_MODULES:
        assert module in cmake
    for module in FORBIDDEN_MODULES:
        assert module not in cmake.split("install(TARGETS", 1)[1]
    install_block = cmake.split("install(TARGETS", 1)[1]
    assert "LIBRARY DESTINATION ." in install_block
    assert "RUNTIME DESTINATION ." in install_block


def test_distribution_inventory_records_wheel_boundary() -> None:
    inventory = json.loads(
        (ROOT / "docs/licensing/distribution-dependency-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    profile = next(
        item for item in inventory["profiles"] if item["id"] == "first-party-native-wheel"
    )
    assert set(profile["native_modules"]) == EXPECTED_MODULES
    assert set(profile["forbidden_native_modules"]) == FORBIDDEN_MODULES
    assert profile["project_license"] == "GPL-3.0-or-later"
    assert "sdist" in profile["corresponding_source"]
    boost = next(item for item in profile["dependencies"] if item["id"] == "cmake:Boost.headers")
    assert boost["license_assertion"]["spdx_expression"] == "BSL-1.0"
    assert "NOT_YET_RELEASE_AUDITED" in boost["license_assertion"]["status"]

    provenance = json.loads(
        (ROOT / "docs/licensing/native-core-provenance-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    shipped = {
        item["module"]
        for item in provenance["bindings"]
        if item["classification"] == "native_core"
    }
    assert shipped == EXPECTED_MODULES
