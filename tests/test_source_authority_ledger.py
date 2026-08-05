from __future__ import annotations

from core.source_authority_ledger import (
    build_source_authority_ledger,
    resolve_input_selectors,
    resolve_selector,
)


def _write_ascii_stl(path):
    path.write_text(
        """solid one
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 0 1 0
 endloop
endfacet
endsolid one
""",
        encoding="ascii",
    )


def test_stl_ledger_is_digest_bound_and_exposes_only_facet_identity(tmp_path):
    source = tmp_path / "plate.stl"
    _write_ascii_stl(source)

    ledger = build_source_authority_ledger(source)

    assert ledger["status"] == "authoritative_partial"
    assert ledger["source"]["filename"] == "plate.stl"
    assert ledger["source"]["sha256"] == ledger["source_digest"]
    assert ledger["selector_namespaces"]["stl_facet"]["id_ranges"] == [[0, 0]]
    assert ledger["selector_namespaces"]["stl_facet"]["available"] is True
    assert ledger["selector_namespaces"]["physical_group"]["available"] is False
    assert "path" not in ledger

    selector = {
        "ledger_digest": ledger["ledger_digest"],
        "kind": "stl_facet",
        "ids": [0],
    }
    resolved = resolve_selector(ledger, selector, pointer="/boundary_layers/0/selector")
    assert resolved["status"] == "resolved"
    assert resolved["matched_ids"] == [0]


def test_selector_rejects_free_text_and_stale_digest(tmp_path):
    source = tmp_path / "plate.stl"
    _write_ascii_stl(source)
    ledger = build_source_authority_ledger(source)

    free_text = resolve_selector(
        ledger, "wall", pointer="/boundary_layers/0/selector", strict=True
    )
    assert free_text["status"] == "rejected"

    stale = resolve_selector(
        ledger,
        {"ledger_digest": "stale", "kind": "stl_facet", "ids": [0]},
        pointer="/boundary_layers/0/selector",
        strict=True,
    )
    assert stale["status"] == "rejected"
    assert "digest" in stale["reason"]


def test_bl_zero_is_identity_but_positive_bl_requires_authority(tmp_path):
    source = tmp_path / "plate.stl"
    _write_ascii_stl(source)
    ledger = build_source_authority_ledger(source)

    zero = resolve_input_selectors(
        {"boundary_layers": [{"layers": 0}]}, ledger, strict=True
    )
    assert zero["can_run"] is True
    assert zero["resolutions"][0]["status"] == "ignored_identity"

    positive = resolve_input_selectors(
        {"boundary_layers": [{"layers": 1, "first_height": 0.1, "growth_rate": 1.2}]},
        ledger,
        strict=True,
    )
    assert positive["can_run"] is False
    assert positive["resolutions"][0]["status"] == "rejected"

    compat = resolve_input_selectors(
        {"boundary_layers": [{"layers": 1}]}, ledger, strict=False
    )
    assert compat["can_run"] is False
    assert compat["status"] == "unavailable"
    assert compat["resolutions"][0]["status"] == "unavailable_missing_authority"
