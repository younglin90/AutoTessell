# CAD physical-group authority evidence — Cycle 59

State: `L0_PASS / CORRECTNESS_KEEP`; report-only and default disconnected.

## Hypothesis

Complete CAD B-Rep authority and physical-group authority are independent.
Face ordinal, orientation, and seam evidence can establish a trustworthy CAD
identity while still being insufficient to label a wall, inlet, outlet, or
region.  The diagnostic must return the exact missing physical-group evidence
instead of inferring semantics from names, layers, colors, geometry, or XDE
assembly paths.

## Contract

`diagnose_cad_physical_group_evidence()` first checks the existing B-Rep
authority triplet: positive face/edge counts plus authoritative face ordinal,
orientation, and seam connectivity.  A complete B-Rep with
`physical_groups_authoritative=false` returns:

```text
reject_cad_physical_groups_unknown
missing_evidence = (physical_group,)
```

When a caller declares physical-group authority, every face must carry one
nonempty group name.  A canonical JSON SHA-256 is recorded only as a
deterministic diagnostic fingerprint.  The result remains
`report_cad_physical_groups_authoritative_unverified`; it never accepts a
product, shell, local front, or route.

## L0 evidence

A minimal immutable CAD provenance fixture repeats the complete-B-Rep/unknown
case three times and reports the exact physical-group gap.  A separately
declared `wall` group is distinguished and fingerprinted but remains
unverified.  Missing group names under an authoritative declaration and an
incomplete B-Rep both fail closed.  Source arrays are never modified.

## Scope and rollback

No CAD reader, C++, shell, candidate, routing, writer, target-cell,
boundary-layer, default, or output code changes.  Roll back if the diagnostic
maps display metadata to a physical group, promotes a declared group to a
product acceptance, mutates provenance, or creates an artifact.

Existing XDE evidence remains authoritative for layers/display/assembly only;
it is not a CFD BC contract.  `third_party/` remains unchanged.
