# Native Tet Source-Component Bijection — 2026-07-31

## Card

`TET-SOURCE-COMPONENT-BIJECTION-1`

Primary metric: every edge-connected source surface component maps to exactly
one final tetrahedral boundary component, and vice versa.

Rollback conditions: missing/interiorized source surface vertex, merged source
components, split source component, unanchored output component, ambiguous
coordinate provenance, malformed native result, or any existing writer
topology defect.

Target-cell behavior is unchanged. Shape and topology evidence takes priority.

## Defect and decision

The local `TetBoundaryAudit.valid` contract remains conservative and requires
one boundary component. It must not be relaxed by itself because it has no
source mesh with which to distinguish a valid disconnected input from an
invented output shell.

The production P4C acceptance and final-result paths now add a separate
source-aware contract. Source identity is recovered from exact finite
coordinates, not a candidate vertex-prefix assumption. This is required because
external fallback output may reorder vertices. Duplicate source coordinates or
multiple candidate vertices at one source coordinate are ambiguous and fail
closed. A scan through all 52 repository STL fixtures after `read_stl` found no
duplicate source coordinate.

The native C++23 implementation uses flat contiguous records, sorted canonical
faces and edges, and contiguous disjoint-set forests. New candidate vertices
receive collision-free synthetic provenance ids. The Python implementation is
an independent oracle/fallback. The strict native ABI accepts only C-contiguous
`float64` point matrices and `int64` index matrices; the GIL is released only
after dtype, shape, and layout validation.

## Acceptance evidence

Focused fixtures:

- 1, 2, and 5 exact disconnected tetrahedral bodies: bijection accepted.
- lost, merged, split, unanchored, and interiorized components: rejected.
- candidate point reorder plus face/tet reorder: identical deterministic result.
- malformed native count or verdict: rejected without Python fallback.
- single-body cylinder generation: result and topology hashes unchanged from
  the pre-card baseline (`1495` cells, `353` points).

Synthetic benchmark, 1,000 disconnected bodies (`4,000` vertices, `4,000`
faces, `1,000` tetrahedra), warm process:

- native C++23 audit: `1.781 ms` mean over 10 runs;
- independent Python oracle: `52.000 ms` mean over 3 runs;
- observed speedup: `29.19x`.

The dominant bound is `O((F + T) log(F + T) + V log V)` time from sorting and
`O(F + T + V)` auxiliary storage. Flat vectors avoid per-face hash-node
allocation and improve locality. No `third_party/` file or dependency changed.

## Research and provenance

- CGAL 6.2 Polygon Mesh Processing documents connected-component operations
  for arbitrary component counts:
  https://doc.cgal.org/latest/Polygon_mesh_processing/index.html
- CGAL 6.2 Tetrahedral Remeshing separates sizing criteria from topology and
  feature preservation:
  https://doc.cgal.org/latest/Tetrahedral_remeshing/index.html
- Boost Graph `connected_components` documents linear graph traversal:
  https://www.boost.org/doc/libs/latest/libs/graph/doc/connected_components.html
- Hang Si, *TetGen, a Delaunay-Based Quality Tetrahedral Mesh Generator*, 2015,
  DOI `10.1145/2629697`.

CGAL licensing is GPL/LGPL/commercial; TetGen source is AGPL; Boost Graph is
BSL-1.0. These sources were used only for concepts and test strategy. The code
in this card is an independent implementation and adds no dependency or copied
source.
