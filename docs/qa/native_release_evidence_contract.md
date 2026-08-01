# Native release evidence contract

The native engines do not acquire a release claim from a focused unit test or
from a cube-only run.  Release evidence is a separate, read-only observation
of written artifacts.

## Independent artifact audit

Run the strict topology audit after generation, in a fresh process if the
generator used native extensions:

```bash
python3 scripts/strict_native_release_audit.py \
  artifacts/tet-cube artifacts/tet-sphere artifacts/tet-naca \
  --output evidence/strict-topology.json
```

The audit is fail-closed.  A valid row has zero duplicate faces, zero
non-manifold faces, zero open/non-manifold local cell edges, zero inverted
cells, a valid boundary surface, and a strictly positive minimum cell volume.
The result is bound to the exact five-file `polyMesh` digest.

## Corpus contract

`core.evaluator.native_release_matrix` requires these rows before any native
release claim can be evaluated:

- Tet: cube, sphere, NACA, and one complex geometry.
- Hex: cube, sphere, NACA, and gear.
- Poly: cube, sphere, NACA, and gear.
- Tri: cube, sphere, NACA, and a CAD-backed case.
- Strict Quad: cube and a complex case, as its own product.
- TRI+QUAD: cube and a complex case, with mixed topology evidence.

Every row must bind an authoritative source digest to the measured surface,
feature and physical-group/provenance evidence, and output digest.  Positive
boundary-layer rows require a positive first-layer height and positive layer
cell count.  Each row requires at least three byte-identical runs and an
explicitly independent release route.  A sidecar-only diagnostic, relabelled
quad-dominant output, or no-op Tri clone is not sufficient evidence.

Verify a manifest with:

```bash
python3 scripts/verify_native_release_matrix.py \
  evidence/native-release-matrix.json \
  --evidence evidence/native-release-matrix-report.json
```

The verifier is evidence-only and never changes routing or defaults.  Missing
authority, topology, provenance, positive-BL, or repeatability evidence stays
`unverified`.


## Evidence collection

scripts/collect_native_release_evidence.py consumes an engine-produced JSON
spec and writes the common matrix plus an authority-gate report. When case
directories are supplied, it recomputes the independent strict written-artifact
audit and the three-run artifact digests. Source authority, feature, patch,
physical-group, boundary-layer, and source/output preservation fields are
never defaulted; absent measurements leave the matrix unverified.

Example: python3 scripts/collect_native_release_evidence.py spec.json --output native_release_matrix.json --authority-evidence native_release_authority.json


### Volume versus surface topology

A matrix row declares strict_topology.kind as olume (the default) or
surface. Volume rows require the independent polyMesh zero counters. Surface
rows require measured surface_topology_valid, duplicate-face,
non-manifold-edge, degenerate-face, and inverted-face zero counters. Surface
source/output authority additionally requires explicit shape_preserved and
source_face_provenance (or exact source-face preservation); vertex identity is
not silently substituted for remeshed surface shape preservation.

The independent surface auditor is core/evaluator/strict_surface_topology.py;
it emits a canonical vertex/face artifact digest and measured zero counters for
duplicate faces, non-manifold/open edges, degenerate faces, and orientation
conflicts.
