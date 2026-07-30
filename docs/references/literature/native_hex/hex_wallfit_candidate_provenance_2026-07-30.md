# HEX-WALLFIT-CANDIDATE-PROVENANCE-1

Date: 2026-07-30

## Scope

`CORRECTNESS_KEEP`, report-only, default OFF.  This card adds source-provenance
status to the existing opt-in wall-fit candidate quality audit only.  It does
not change wall-fit projection, ordering, acceptance, rollback, routing,
quality thresholds, output points, cells, or any boundary-layer/cell-budget
path.

## Authority contract

`source_feature_sidecar_l1.py` remains the only authority source.  A sidecar
must bind both source-file bytes and the reader-visible ordered triangle
coordinate stream.  The wall-fit report can record one source entity only when
that sidecar validates and every source triangle containing the projection
target has exactly one entity identity.

| condition | recorded status | source entity |
|---|---|---|
| no sidecar or source path | `UNAVAILABLE` | `None` |
| file hash or ordered-triangle hash mismatch | `UNAVAILABLE` | `None` |
| projection target not on validated source | `UNAVAILABLE` | `None` |
| valid sidecar, one entity across source contact triangles | `AUTHORITATIVE` | exact supplied entity |
| valid sidecar, source-entity boundary tie | `AMBIGUOUS` | `None` |

The source-contact scan is exhaustive only inside the opt-in diagnostic.  It
does not replace the existing nearest-centroid shortlist used by wall-fit, so
it cannot alter a mesh decision.  The record identifies the proposed
projection target, not a permission to move, repair, or relabel output faces.

## Evidence

L0:

- Valid cube sidecar records an exact `("cube", "axis_2_high")` source entity
  for interior top-face projection targets.
- Wrong source-file hash and reordered source triangles both record
  `UNAVAILABLE`; no default patch is fabricated.
- An authoritative cube entity-boundary edge records `AMBIGUOUS` and no entity.
- Repeated classification is value-identical.

L1:

- Canonical stock cube input without a sidecar reports only `UNAVAILABLE`.
- Enabling the candidate diagnostic preserves wall-fit output points byte for
  byte and preserves the existing snap-count result.
- Real 500-cell stock cylinder diagnostic recorded `128` candidates:
  `0 AUTHORITATIVE`, `128 UNAVAILABLE`, `0 AMBIGUOUS`; the final checker stayed
  truthful `FAIL` (`max_boundary_skew=2.730272645`, negative volumes `0`).
  This is the known wall-fit quality limitation, not an acceptance change.

Focused command:

```bash
python3 -m pytest -q \
  tests/test_native_hex_wallfit_candidate_provenance.py \
  tests/test_native_hex_wallfit_quality.py \
  tests/test_native_hex_wall_fit_degenerate.py
```

Diagnostic command:

```bash
python3 scripts/diag_hex_transition_quality1.py --compact --max-cells 500 --shapes cylinder
```

The stock runner intentionally has no authoritative feature sidecar and prints
`candidate_provenance=UNAVAILABLE`.  A future ingress card may pass an importer
validated `source_path` plus `AuthoritativeSourceFeatureManifest` to the
private diagnostic hook; no production route does so in this card.

## Decision

Retain at `L1_PASS / CORRECTNESS_KEEP`.  The prior cylinder quality finding
remains unchanged: distance improvement does not authorize quality regression,
source repair, candidate selection, or promotion.  This provenance result only
prevents a future repair card from mistaking missing or tied labels for a
unique source entity.
