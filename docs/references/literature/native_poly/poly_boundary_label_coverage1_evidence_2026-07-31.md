# POLY-BOUNDARY-LABEL-COVERAGE-1 Evidence

Date: 2026-07-31

Base: `68c3bfd184852d26fe9308617511ca4a9bd2a852`

Scope: explicit primal-boundary mapping coverage only.  No point, face,
owner, neighbour, patch, topology, geometry, tolerance, target-cell,
boundary-layer, routing, native ABI, or `vendor/dependencies/` change.

## Hypothesis and fixed acceptance

`tet_to_poly_dual` exposes `boundary_face_labels` and
`boundary_face_entities` as aliases for the same explicit primal-boundary
classification.  The existing complete-coverage guard inspected only the
second name.  A partial mapping through the first name could therefore erase
source provenance by replacing omitted patches with `defaultWall`.

Primary metric on the deterministic two-tetrahedron, two-patch bipyramid:

- baseline: `3/3` false successes through partial `boundary_face_labels`
- target: `0/3` false successes and zero written artifacts
- rollback: any complete-mapping output hash, patch order/type, input byte,
  sequence/classifier/unclassified behavior, or mapping-order change

Target-cell behavior is deliberately deferred and not measured by this card.

## Baseline false certification

The partial map classified only the three upper-cap primal triangles.  All
three runs returned success, wrote five polyMesh files, and emitted:

- `source_high:wall`, `9` faces, `startFace=9`
- `defaultWall:wall`, `9` faces, `startFace=18`

The geometry, owner, and neighbour hashes happened to equal the valid
classified output, but the boundary hash changed to
`b70bfe9806220b401f9a8d7c976114580c3d1519da66043adf85420ff3525413`.
Deterministic bytes do not make the silent physical-group reassignment valid.

The identical mapping supplied through `boundary_face_entities` already
returned an exact missing-triangle refusal.  This alias-dependent verdict is
the defect.

## Independent mechanism

The existing set-difference guard now examines `supplied_entity_labels`, the
single value selected after enforcing mutual exclusivity of both aliases.  It
runs only when that value is a `Mapping`.  The error names the public argument
that received the mapping and lists missing canonical triangles in sorted
order.  No mesh object or output directory exists at this point.

This is Python orchestration/schema validation by project design; no numerical
kernel moved out of C++23.  Sequence labels, a callback classifier, and no
classification bypass the mapping-only guard exactly as before.

## Result

Partial `boundary_face_labels` now returns the following exact failure three
times and creates no case directory:

```text
boundary entity classification failed: boundary_face_labels must cover every extracted boundary triangle; missing canonical triangles: ((0, 1, 4), (0, 2, 4), (1, 2, 4))
```

Point and tetrahedron arrays remain byte-identical.  Complete mappings through
both aliases succeed three times with exact patch contract:

- `source_high:wall`, `9` faces, `startFace=9`
- `source_low:patch`, `9` faces, `startFace=18`

The frozen five hashes remain:

- `points`: `fdab8bddd008ad6fc003427a6a153c4ae4898ddb540dee684cc2be2134a25957`
- `faces`: `e34a8b7e92d198a658ef33227d71ecbba55dba2c9c8ebd66c9db16fa297c854c`
- `owner`: `2f3f3f3e97e28db3e2c4ad74ec0b55690bb399ab97098b15d97172ae488873ca`
- `neighbour`: `8d80df3c7b13898717eb271b3913d3e577179c3f85e9441418159002f9374873`
- `boundary`: `d29e59ca7dede8b5d1b3ecd5e7858923ab3e5ca459dafcf1d8b2ebd0281d88c0`

Reversing mapping insertion order preserves all five hashes.  Sequence,
classifier, and unclassified paths remain successful with their existing
single-patch names.

## Research and license boundary

- Garimella, Kim, and Berndt, *Polyhedral Mesh Generation and Optimization
  for Non-manifold Domains* (2013), DOI
  `10.1007/978-3-319-02335-9_18`, local status `FULL_READ`: exact geometric-model
  classification is required to reconstruct exterior boundaries, interfaces,
  creases, corners, and non-manifold junctions.
- [Gmsh 4.15.2 official manual](https://gmsh.info/doc/texinfo/): mesh elements
  remain classified on model entities; physical groups carry mathematical,
  functional, and material meaning.  Gmsh is GPL and reference-only.
- [CGAL 6.2 `Labeled_mesh_domain_3`](https://doc.cgal.org/latest/Mesh_3/classCGAL_1_1Labeled__mesh__domain__3.html):
  every boundary facet receives a surface-patch index from its incident
  subdomains.  CGAL is GPL/commercial and reference-only.
- [OpenFOAM-dev](https://github.com/OpenFOAM/OpenFOAM-dev) was reviewed as the
  active C++ polyMesh reference.  It is GPL-3.0-or-later; no source or artifact
  was copied.

The 2025 SIAM IMR paper *Validity-first automatic polycube labeling for CAD
models*, Sébastien Mestrallet, Christophe Bourcier, and Franck Ledoux, DOI
`10.1137/1.9781611978575.8`, was inaccessible beyond publisher metadata and
abstract because full text requires access.  Its DOI/title were absent from
the project manifests and local PDF repository.  It is recorded, not used as
an implementation source.

The guard and tests are independently authored.  No external code, generated
artifact, dependency, or `vendor/dependencies/` file was copied or modified.

## Verification

Focused mapping/provenance set:

```text
10 passed in 3.18s
```

Bounded boundary semantics, primal conformity, star fail-closed, raw-input,
and writer regression set:

```text
46 passed, 3 skipped in 16.85s
```

The three skips are optional native-extension cases under the existing build
selection.  Black, Ruff, focused strict mypy, and `git diff --check` pass.
No C++ source changed, so no new native build artifact is part of this card.

Verification state: `L1_PASS / CORRECTNESS_KEEP`.  This is a runtime
fail-closed provenance guard for malformed explicit classification, but full
adverse Poly L2/L3 corpus validation remains open.
