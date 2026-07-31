# TRI-ROUTE-CORPUS-FAILCLOSED-1 evidence

Date: 2026-07-31

Promotion state: `L1_PASS / CORRECTNESS_KEEP`.

## Scope

The native-tri runtime route deliberately has no source-envelope and per-face
provenance certificate for topology-changing edits.  This card adds no mesh
operation and changes no route, writer, default, target-count policy, or
boundary-layer behavior.  It freezes the truthful rejection contract on four
small representative sources:

- closed sharp cube;
- closed capped cylinder with sharp rim features;
- open wing with a spike and feature/boundary edges; and
- closed thin disk.

Each source is run three times at `boundary_layers=0` and `boundary_layers=1`.
The test independently hashes C-contiguous `float64` vertices and `int64`
faces including dtype and shape, audits a fixed 30-degree feature-edge set,
and compares the exact source arrays before and after every rejection.

## Acceptance

- all 24 calls return `accepted=false`;
- all BL0 calls report `source_contract_unavailable`, actual layers `0`, and
  reserved layer budget `0`;
- all BL1 calls report `boundary_layers_unsupported_by_surface_route`, actual
  layers `0`, and reserved layer budget `0`;
- source/output/provenance hashes, array bytes, dtype, shape, topology, and
  feature-edge audit sets remain exact;
- each fixture/configuration's three repeat signatures are identical.

## Result and remaining blocker

Focused route regression passes the 24 corpus calls plus pre-existing route
tests.  This is evidence that the product does not silently mutate a source,
invent a layer, or claim provenance while the topology-changing contract is
missing.  It is not an accepted native-tri mesh result and does not close the
source-envelope/per-face provenance blocker.  Target-face requests are
reported but remain unmet by explicit rejection.
