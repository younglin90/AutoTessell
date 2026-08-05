# Native Hex CAD Entity Ingress Contract — 2026-07-31

## Card

- Lane: common CAD ingress; report/contract only.
- Primary metric: authoritative triangle-to-B-Rep-face coverage on
  `tests/benchmarks/t_junction.step`.
- Baseline: 0/3,392 triangles (0%).
- Acceptance: 3,392/3,392 triangles (100%), deterministic three-run hashes,
  oriented closed seam topology, exact source-quad entity propagation, unchanged
  legacy `(vertices, faces)` bytes and order.
- Rollback: any inferred label, incomplete edge polygon, traversal mismatch,
  geometry movement, silent fallback, physical-group fabrication, production
  routing, writer change, or `vendor/dependencies/` change.

## Evidence and provenance

The reader uses installed OCP 7.8.1.1 APIs only: `TopExp` B-Rep face/edge
traversal, `TopoDS_Face::Orientation`, and
`BRep_Tool::PolygonOnTriangulation`. The implementation is independent
AutoTessell metadata plumbing. No OpenCASCADE, external mesher, or GitHub source
was copied.

Ledoux and Shepherd, *Topological and geometrical properties of hexahedral
meshes*, DOI `10.1016/j.cagd.2010.05.003`, motivates explicit CAD surface,
curve, and vertex classification. It does not provide implementation source.
The current card closes only the first surface-identity break and does not
claim curve/corner, physical-group, inner-interface, or core-fill completion.

## Baseline diagnosis

`t_junction.step` contains 12 B-Rep faces and 18 topological edges. The legacy
reader emits 3,404 face-local vertex records and 3,392 triangles, but its return
type has no entity, patch, feature, orientation, or physical-group payload.

- authoritative entity coverage: 0/3,392
- raw index boundary edges: 3,404
- reversed B-Rep faces: 6/12
- same-directed shared edges after coordinate-only seam collapse: 843
- source audit: `reject_source_not_closed_two_manifold`
- exact quadization: `source_not_oriented_closed_manifold`

All six checked STEP fixtures contain blank `ADVANCED_FACE` names. Therefore
physical-group semantics are not verifiable from the current corpus.

## Contract result

The optional API preserves the original arrays and returns a typed side payload.
Seam equivalence requires both the same B-Rep edge identity and the same exact
IEEE-754 coordinate. It does not merge unrelated coincident geometry.

- legacy vertex SHA-256:
  `12d7fe77d022a49bb2b877302fd30472b0dbfef65b1c268439c9e76d70930a9c`
- legacy face SHA-256:
  `80462a27612ef87554a947f946529569cea22b22d2b124bd5443d015c2fb0a3c`
- authoritative entity coverage: 3,392/3,392 (100%)
- canonical vertices: 1,696
- closed oriented edges: 5,088/5,088; direction conflicts 0
- source entity-boundary audit: PASS, 1,696 edges, 12 components
- exact quad provenance: expected 3,392, observed 3,392, spurious 0
- support distance: 0
- relative area error: 0
- coordinate/entity/orientation/seam hashes: identical across three runs
- input geometry changed: no
- production mesh/routing changed: no
- physical groups: unknown; authority false; gate remains UNVERIFIED
- all-hex inner interface and core fill: not produced; gate remains UNVERIFIED

## Reproduction

```bash
pytest -q tests/test_native_hex_cad_front_contract.py -o addopts='' \
  --disable-warnings --maxfail=1
pytest -q tests/test_cad_reader_native.py \
  tests/test_native_hex_source_quad_feature_provenance_l1.py -o addopts='' \
  --disable-warnings --maxfail=1
git diff --check
```
