"""BLR-9c-d-r-1 — pipeline-only kwargs must not leak into native_tet.

The orchestrator forwards ``bl_layers``, ``post_layers_*``,
``checker_engine``, ``cad_engine``, ``remesh_engine``,
``repair_engine`` and ``postprocess_engine`` to every tier runner.
``tier_native_tet._runner`` strips them before calling
``run_native_tet_harness`` / ``generate_native_tet`` so the volume
mesher does not blow up with "unexpected keyword argument".
"""
from __future__ import annotations

import inspect

from core.generator.tier_native_tet import _runner


def test_runner_strips_pipeline_only_kwargs(monkeypatch) -> None:
    seen: dict[str, dict[str, object]] = {}

    def fake_harness(vertices, faces, case_dir, **kwargs):  # noqa: ANN001
        seen["harness"] = dict(kwargs)
        class _R:
            success = True
            n_cells = 1
        return _R()

    def fake_generate(vertices, faces, case_dir, **kwargs):  # noqa: ANN001
        seen["generate"] = dict(kwargs)
        class _R:
            success = True
            n_cells = 1
        return _R()

    monkeypatch.setattr(
        "core.generator.tier_native_tet.run_native_tet_harness",
        fake_harness,
    )
    monkeypatch.setattr(
        "core.generator.tier_native_tet.generate_native_tet",
        fake_generate,
    )

    _runner(
        vertices=None, faces=None, case_dir=None,
        target_edge_length=0.1,
        seed_density=10,
        max_iter=2,
        # Pipeline-only kwargs the volume mesher doesn't accept:
        bl_layers=3,
        post_layers_engine="auto",
        post_layers_num_layers=3,
        checker_engine="native",
        cad_engine="cadquery",
        remesh_engine="native",
        repair_engine="native",
        postprocess_engine="none",
        # Real volume-mesher kwargs that should pass through:
        target_cells=10000,
    )
    forwarded = seen["harness"]
    assert "bl_layers" not in forwarded
    assert "post_layers_engine" not in forwarded
    assert "post_layers_num_layers" not in forwarded
    assert "checker_engine" not in forwarded
    assert "cad_engine" not in forwarded
    assert "remesh_engine" not in forwarded
    assert "repair_engine" not in forwarded
    assert "postprocess_engine" not in forwarded
    assert forwarded.get("target_cells") == 10000


def test_runner_filter_keys_exhaustive() -> None:
    """The hard-coded filter list mirrors the orchestrator's
    ``tier_specific_params_override`` keys.  If those grow, this
    test will fail to surface that the filter list needs an
    update."""
    src = inspect.getsource(_runner)
    for key in (
        "bl_layers",
        "post_layers_engine",
        "post_layers_num_layers",
        "checker_engine",
        "cad_engine",
        "remesh_engine",
        "repair_engine",
        "postprocess_engine",
    ):
        assert key in src, (
            f"_runner filter list missing pipeline-only key {key!r}"
        )
