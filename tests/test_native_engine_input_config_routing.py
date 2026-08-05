"""Card A: the full user envelope is consumed by tier adapters, not kernels."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.generator.tier_native_hex import _runner as hex_runner
from core.generator.tier_native_tet import _runner as tet_runner


def test_native_tet_consumes_input_envelope_before_mesher(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_harness(vertices, faces, case_dir, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(success=True, n_cells=1, n_points=4, n_faces=4)

    monkeypatch.setattr("core.generator.tier_native_tet.run_native_tet_harness", fake_harness)
    tet_runner(
        None,
        None,
        Path("case"),
        input_config={"quality": {"max_skewness": 0.5}},
        input_parameter_report={"applied": ["quality.max_skewness"]},
    )
    assert "input_config" not in seen
    assert "input_parameter_report" not in seen


def test_native_hex_consumes_input_envelope_before_mesher(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_generate(vertices, faces, case_dir, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(success=True, n_cells=1, n_points=8, n_faces=6)

    monkeypatch.setattr("core.generator.tier_native_hex.generate_native_hex", fake_generate)
    hex_runner(
        None,
        None,
        Path("case"),
        input_config={"boundary_layers": [{"layers": 0}]},
        input_parameter_report={"applied": ["boundary_layers.layers"]},
    )
    assert "input_config" not in seen
    assert "input_parameter_report" not in seen
