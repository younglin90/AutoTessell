"""Regression contract for the native Hex local-front admission ABI."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "auto_tessell_core" / "native_build_contract.json"
SOURCE = ROOT / "auto_tessell_core" / "native_hex_quality_bind.cpp"


def test_local_front_numeric_admission_is_contracted_and_strict_no_convert() -> None:
    symbols = json.loads(CONTRACT.read_text(encoding="utf-8"))["modules"][
        "native_hex_quality"
    ]["public_symbols"]
    source = SOURCE.read_text(encoding="utf-8")
    function = source[source.index("py::dict local_front_numeric_admission(") :]
    binding = source[source.index('"local_front_numeric_admission",') :]

    assert "local_front_numeric_admission" in symbols
    assert "py::array_t<std::int64_t, py::array::c_style> source_face_ids" in function
    assert 'py::arg("source_face_ids").noconvert()' in binding
