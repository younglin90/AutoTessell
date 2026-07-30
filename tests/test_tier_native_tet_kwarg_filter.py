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
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from core.generator.tier_native_tet import _runner

_TYPED_RUNNER = cast(Callable[..., Any], _runner)


def test_runner_strips_pipeline_only_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, dict[str, object]] = {}

    def fake_harness(
        vertices: object,
        faces: object,
        case_dir: object,
        **kwargs: object,
    ) -> object:
        seen["harness"] = dict(kwargs)

        class _R:
            success = True
            n_cells = 1

        return _R()

    def fake_generate(
        vertices: object,
        faces: object,
        case_dir: object,
        **kwargs: object,
    ) -> object:
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

    _TYPED_RUNNER(
        vertices=None,
        faces=None,
        case_dir=None,
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
        assert key in src, f"_runner filter list missing pipeline-only key {key!r}"


def test_runner_consumes_max_cells_in_harness_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed harness retries with mesher-supported target/shape inputs."""
    seen_kwargs: dict[str, dict[str, object]] = {}
    seen_inputs: dict[str, object] = {}
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    fallback_result = SimpleNamespace(success=True, n_cells=1_950)

    def fake_harness(
        actual_vertices: object,
        actual_faces: object,
        case_dir: Path,
        **kwargs: object,
    ) -> SimpleNamespace:
        seen_inputs["harness_vertices"] = actual_vertices
        seen_inputs["harness_faces"] = actual_faces
        seen_kwargs["harness"] = dict(kwargs)
        return SimpleNamespace(success=False, n_cells=0)

    def fake_generate(
        actual_vertices: object,
        actual_faces: object,
        case_dir: Path,
        **kwargs: object,
    ) -> SimpleNamespace:
        seen_inputs["fallback_vertices"] = actual_vertices
        seen_inputs["fallback_faces"] = actual_faces
        seen_kwargs["fallback"] = dict(kwargs)
        return fallback_result

    monkeypatch.setattr(
        "core.generator.tier_native_tet.run_native_tet_harness",
        fake_harness,
    )
    monkeypatch.setattr(
        "core.generator.tier_native_tet.generate_native_tet",
        fake_generate,
    )

    result = _TYPED_RUNNER(
        vertices,
        faces,
        Path("/tmp/case"),
        target_edge_length=0.2,
        seed_density=9,
        max_iter=2,
        target_cells=2_000,
        max_cells=2_000,
        enable_phase_b=True,
    )

    assert result is fallback_result
    assert seen_inputs["harness_vertices"] is vertices
    assert seen_inputs["harness_faces"] is faces
    assert seen_inputs["fallback_vertices"] is vertices
    assert seen_inputs["fallback_faces"] is faces
    assert seen_kwargs["harness"]["max_cells"] == 2_000
    assert seen_kwargs["harness"]["target_cells"] == 2_000
    assert "max_cells" not in seen_kwargs["fallback"]
    assert seen_kwargs["fallback"]["target_cells"] == 2_000
    assert seen_kwargs["fallback"]["enable_phase_b"] is True
    assert seen_kwargs["fallback"]["target_edge_length"] == 0.2
    assert seen_kwargs["fallback"]["seed_density"] == 9


def test_runner_keeps_strict_topology_fallback_failure_truthful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback must return a strict writer rejection, never a fake success."""
    fallback_kwargs: dict[str, object] = {}
    strict_message = (
        "native_tet writer rejected output topology: "
        "strict polyMesh contract rejected non-manifold face references: count=4"
    )
    strict_failure = SimpleNamespace(
        success=False,
        n_cells=1_287,
        message=strict_message,
    )

    def fake_harness(
        vertices: object,
        faces: object,
        case_dir: Path,
        **kwargs: object,
    ) -> SimpleNamespace:
        return SimpleNamespace(success=False, n_cells=0, message="harness failed")

    def fake_generate(
        vertices: object,
        faces: object,
        case_dir: Path,
        **kwargs: object,
    ) -> SimpleNamespace:
        fallback_kwargs.update(kwargs)
        return strict_failure

    monkeypatch.setattr(
        "core.generator.tier_native_tet.run_native_tet_harness",
        fake_harness,
    )
    monkeypatch.setattr(
        "core.generator.tier_native_tet.generate_native_tet",
        fake_generate,
    )

    result = _TYPED_RUNNER(
        None,
        None,
        Path("/tmp/case"),
        target_cells=2_000,
        max_cells=2_000,
    )

    assert result is strict_failure
    assert not result.success
    assert result.n_cells == 1_287
    assert result.message == strict_message
    assert "max_cells" not in fallback_kwargs
    assert fallback_kwargs["target_cells"] == 2_000
