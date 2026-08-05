from __future__ import annotations

import hashlib

from core.generator.native_poly.protected_corpus_receipt import (
    validate_native_poly_protected_corpus,
)


_REF = "codex/native-poly-cycle41-solid-volume-timeout-1"
_COMMIT = "70ce4b9b"


def _package(source: bytes = b"poly-source") -> dict:
    raw_sha = hashlib.sha256(source).hexdigest()
    return {
        "schema": "NativePolyProtectedCorpusPackage/v1",
        "protected_ref": _REF,
        "protected_commit": _COMMIT,
        "protected_tree": "tree-sha",
        "raw_source_sha256": raw_sha,
        "issuer": "fixture-author",
        "tool": "poly-authority-tool/v1",
        "reader_options": "reader-options",
        "provenance": "source-authored",
        "trust": {"root": "fixture-root", "signature": "sig"},
        "source_reader": {"reader": "native-poly-reader", "version": "1"},
        "source_output_map": {
            "source_face_to_output_faces": [{"source_face": 0, "output_faces": [0, 1]}],
            "wall_edges": [{"edge": "wall-0", "source_face": 0}],
        },
        "faces": [{"face_id": 0, "feature": "planar", "patch": "wall"}],
        "physical_groups": [{"id": "fluid_wall", "faces": [0]}],
        "components": [{"id": "main", "faces": [0]}],
        "bl0": {
            "exact_identity": True,
            "source_digest": raw_sha,
            "output_digest": raw_sha,
        },
        "positive_bl": {
            "requested_layers": 1,
            "actual_layers": 1,
            "direct_layer_final_ids": [{"layer": 1, "final_ids": [1, 2]}],
            "topology": {"accepted": True, "invalid": 0, "non_manifold": 0},
            "quality": {"accepted": True, "skew_p95": 0.1},
            "fresh_process_digests": ["digest", "digest", "digest"],
        },
    }


def test_protected_poly_bl0_and_bl1_receipts_are_private_and_deterministic():
    source = b"poly-source"
    first = validate_native_poly_protected_corpus(source, "tree-sha", _package(source), 0)
    second = validate_native_poly_protected_corpus(source, "tree-sha", _package(source), 0)
    assert first == second
    assert first["accepted"] is True
    assert first["actual_layers"] == 0
    assert first["publication_eligible"] is False
    assert first["runtime_route"] == "private_default_off"
    assert first["route_calls"] == 0

    positive = validate_native_poly_protected_corpus(source, "tree-sha", _package(source), 1)
    assert positive["accepted"] is True
    assert positive["actual_layers"] == 1


def test_missing_package_or_partial_or_repeat_mismatch_refuses():
    source = b"poly-source"
    missing = _package(source)
    missing.pop("trust")
    refused = validate_native_poly_protected_corpus(source, "tree-sha", missing, 0)
    assert refused["accepted"] is False
    assert refused["reason"] == "source_authority_package_evidence_missing"

    partial = _package(source)
    partial["positive_bl"]["actual_layers"] = 0
    refused = validate_native_poly_protected_corpus(source, "tree-sha", partial, 1)
    assert refused["accepted"] is False
    assert refused["reason"] == "partial_positive_layer"

    repeat = _package(source)
    repeat["positive_bl"]["fresh_process_digests"][-1] = "other"
    refused = validate_native_poly_protected_corpus(source, "tree-sha", repeat, 1)
    assert refused["accepted"] is False
    assert refused["reason"] == "repeatability_digest_mismatch"


def test_protected_ref_and_source_digest_drift_refuse_without_branch_access():
    source = b"poly-source"
    package = _package(source)
    refused = validate_native_poly_protected_corpus(
        source,
        "tree-sha",
        package,
        0,
        protected_ref="not-the-protected-ref",
    )
    assert refused["accepted"] is False
    assert refused["reason"] == "protected_ref_or_commit_mismatch"

    package = _package(source)
    package["raw_source_sha256"] = hashlib.sha256(b"other").hexdigest()
    refused = validate_native_poly_protected_corpus(source, "tree-sha", package, 0)
    assert refused["accepted"] is False
    assert refused["reason"] == "source_authority_package_header_incomplete"
