"""Gate-12 evidence: surface product labels are not yet user-selectable routes."""

from __future__ import annotations

import ast
from pathlib import Path

from click.testing import CliRunner

from cli.main import run
from core.preprocessor.native_remesh.surface_mode_contract import (
    SurfaceProductClassification,
    SurfaceProductMode,
    certify_surface_product_mode,
)

_ROOT = Path(__file__).resolve().parents[1]
_PIPELINE = _ROOT / "core" / "preprocessor" / "pipeline.py"
_GUI = _ROOT / "desktop" / "qt_app" / "main_window.py"


def _engine_equal_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        comparison.comparators[0].value
        for comparison in ast.walk(tree)
        if isinstance(comparison, ast.Compare)
        and isinstance(comparison.left, ast.Name)
        and comparison.left.id == "engine"
        and len(comparison.ops) == len(comparison.comparators) == 1
        and isinstance(comparison.ops[0], ast.Eq)
        and isinstance(comparison.comparators[0], ast.Constant)
        and isinstance(comparison.comparators[0].value, str)
    }


def test_surface_product_registry_and_pipeline_route_identities_are_distinct() -> None:
    assert tuple(SurfaceProductMode) == (
        SurfaceProductMode.TRI,
        SurfaceProductMode.QUAD,
        SurfaceProductMode.TRI_QUAD,
    )

    routes = _engine_equal_literals(_PIPELINE)
    assert {"native_tri", "native_strict_quad", "native_tri_quad"} <= routes
    assert "native_quad_dominant" in routes
    assert "native_quad_strict" not in routes
    assert "native_tri_quad_mixed" not in routes


def test_gui_has_no_three_way_native_surface_product_selector() -> None:
    source = _GUI.read_text(encoding="utf-8")

    assert '"native_isotropic"' in source
    assert '"native_cvt"' in source
    assert '"native_quad_strict"' not in source
    assert '"native_tri_quad_mixed"' not in source


def test_cli_exposes_three_explicit_surface_product_route_identities() -> None:
    result = CliRunner().invoke(run, ["--help"])

    assert result.exit_code == 0
    for identity in ("native_tri", "native_strict_quad", "native_tri_quad"):
        assert identity in result.output


def test_quad_dominant_candidate_never_certifies_as_strict_quad() -> None:
    strict = certify_surface_product_mode(
        SurfaceProductMode.QUAD,
        triangle_count=0,
        quad_count=1,
        separate_tri_quad_representation=True,
        triangular_handoff=False,
        producer="native_quad_dominant",
    )

    assert strict.classification is SurfaceProductClassification.CANDIDATE_MIXED
    assert strict.accepted is False
    assert strict.rejection_reason == "representation_not_strict_quad"


def test_existing_representation_aliases_are_unchanged() -> None:
    aliases = {
        "native_tri_only": SurfaceProductMode.TRI,
        "native_quad_strict": SurfaceProductMode.QUAD,
        "native_tri_quad_mixed": SurfaceProductMode.TRI_QUAD,
    }

    for alias, expected_mode in aliases.items():
        certificate = certify_surface_product_mode(
            alias,
            triangle_count=0 if expected_mode is not SurfaceProductMode.TRI else 1,
            quad_count=0 if expected_mode is SurfaceProductMode.TRI else 1,
            separate_tri_quad_representation=expected_mode is SurfaceProductMode.TRI_QUAD,
            triangular_handoff=False,
        )
        assert certificate.requested_mode is expected_mode
