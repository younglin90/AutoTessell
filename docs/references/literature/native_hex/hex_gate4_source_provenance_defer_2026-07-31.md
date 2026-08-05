# Hex Gate 4 source-provenance research — Cycle 61

State: `DEFER`; no production behavior changed.

## Finding

Current CAD/B-Rep ingestion provides authoritative face ordinals, orientation,
and seam connectivity.  It deliberately returns
`partial_authority_physical_groups_unavailable`, sets every
`physical_group_names` entry to `None`, and sets
`physical_groups_authoritative=false`.  XDE layer/color/name/assembly metadata
is not converted into CFD physical groups.

Therefore there is no explicit authoritative source-face-to-physical-group
mapping to hash or verify for Hex Gate 4.  A source-product certificate remains
missing.  No synthetic mapping, display-metadata fallback, acceptance,
threshold, or routing change is permitted.

## Evidence

The focused test reads the actual STEP reader contract and verifies the four
explicit unavailable-authority declarations plus the retained B-Rep authority
triplet.  It repeats the source bytes exactly and creates no mesh/artifact.

Unblock condition: CAD ingestion must expose an explicit immutable mapping
from every canonical source face to one declared physical group, together with
an authority declaration and a dedicated mapping digest.  Only then may a
separate report-only digest-verification card run.  `vendor/dependencies/` unchanged.
