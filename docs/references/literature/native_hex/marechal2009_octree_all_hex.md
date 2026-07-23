# Maréchal 2009 - Advances in Octree-Based All-Hexahedral Mesh Generation

## Bibliographic record

- Loïc Maréchal, *Advances in Octree-Based All-Hexahedral Mesh Generation: Handling Sharp Features*, 18th International Meshing Roundtable, pp. 65-84, 2009.
- DOI: `10.1007/978-3-642-04319-2_5`
- Legal open manuscript: <https://team.inria.fr/gamma/files/2021/03/imr18.pdf>
- Status: `FULL_READ` (19/19 pages, 2026-07-23).
- Visual verification: pages 4, 9, and 14 rendered and inspected. The size/balance diagram, dual transition patterns, equations, and conclusion are legible and agree with extracted text.

## Problem and claimed scope

Hexotic targets automated, conforming, valid, all-hexahedral meshes with variable size, multiple/non-manifold subdomains, sharp features, and adaptation. The paper does not claim the ideal target is fully reached. Reported remaining failures are thin geometry and angles sharper than 30 degrees.

## Algorithm read from the paper

1. Build a modified octree from the object bounding box.
2. Refine from geometry thickness and a user/solver size map. Local size is the minimum of all active criteria.
3. Enforce two topological rules:
   - balance: neighboring octants sharing a vertex differ by at most one level;
   - pairing: if one child is split, its siblings are also split.
4. Convert hanging-node octants into a conforming **polyhedral primal mesh** using directional cuts in the three coordinate planes.
5. Construct the dual. Primal degree-four edges yield quad dual faces; primal degree-six vertices yield six-faced dual cells, hence hexahedra.
6. Recover subdomains and filter one-element-thick regions and pinches.
7. Map boundary quads to target input triangles; map detected ridges and corners to target geometric features.
8. Insert volume and surface buffer layers. Every boundary hex is arranged to have one boundary face; every ridge-adjacent buffer hex has at most one ridge edge.
9. Run 30 constrained element-based smoothing/projection steps. Element quality takes priority over exact geometry projection.

The quality objective is

```text
q = 24 sqrt(3) V_min / (sum_{i=1}^{12} l_i^2)^(3/2)
```

where `V_min` is the minimum over two five-tetrahedron decompositions of a hex. `q=1` for a cube, `q=0` for flat cells, and `q<0` for invalid cells. Hexotic accepts down to `q=0.01`.

## Assumptions, guarantees, limits

- The input is a triangulated surface that can be analyzed, intersected, and assigned to subdomains.
- At least two elements across local thickness are sought. This gives free interior vertices during boundary recovery; one-element-thick regions lock all vertices.
- Pairing plus directional cuts establishes the primal connectivity needed by the dual construction. A generic 2:1 level rule alone does not imply an all-hex dual.
- The paper reports conforming, all-hex, positive-Jacobian output for its examples, not a formal proof for arbitrary input.
- Geometry accuracy is deliberately relaxed when projection would violate the quality threshold.
- Angles below 30 degrees and thin regions remain weak cases. Thin features can trigger very high octree levels and cell counts.
- Reported 2009 performance: about two million elements/minute on a 2.4 GHz Core 2 Duo. Example minima include `q=0.004`, below the stated 0.01 default in one table; this makes the global validity claim empirical, not a uniform quality lower bound.

## AutoTessell code comparison

Relevant code:

- `core/generator/native_hex/octree.py:316`: level-grid 2:1 balance.
- `core/generator/native_hex/octree.py:395`: N-level cells.
- `core/generator/native_hex/octree.py:485`: coarse faces split into multiple sub-quads at a fine neighbor.
- `core/generator/native_hex/octree.py:1109`: second 26-neighbor balance helper.
- `core/generator/native_hex/mesher.py:1557`: adaptive cells written through the generic polyhedral writer.
- `core/generator/native_hex/mesher.py:379`: written-mesh quality summary.

### Present matches

- Surface-distance and feature-driven refinement exist.
- Level difference is limited and an extra buffer band can be added.
- Boundary projection has distance and inversion guards.
- Written mesh is checked for negative volume, non-orthogonality, skewness, and aspect ratio.

### Material gaps

- Current adaptive transition is **not Maréchal's all-hex construction**. It splits a coarse cube face into sub-quads and writes that cube as a generic polyhedron with more than six faces. No pairing rule, three directional primal cuts, degree invariant, or dual construction exists.
- Centroid-inside selection can miss a boundary-cut cell or a thin component before refinement. Maréchal explicitly refines from local thickness and surface intersections.
- No persistent boundary-quad to source-triangle, ridge, and corner map exists. Current snapping searches nearest triangles/features afresh.
- No volume/surface buffer topology equivalent to sections 7-8 is constructed before projection.
- The adaptive path is graded as a generic polyMesh. It does not report true hexahedron count/ratio or the paper's two-decomposition `q`.
- Comments label several mechanisms as Hexotic/snappy equivalents, but shared names are not evidence of the paper's topology or guarantees.

## Falsifiable implementation cards

### HEX-OCT-1 - truthful cell-type census

- Add cell histogram: six quad faces = hex; otherwise polyhedron classified by face count.
- Pass: every run reports `hex_count`, `poly_count`, and `hex_volume_fraction`; counts sum to written cells.
- Expected current adaptive result: some transition cells classify as non-hex. This test prevents an all-hex claim.

### HEX-OCT-2 - choose transition contract

- Option A: implement pairing, directional primal cuts, and dual extraction.
- Pass: adaptive cube, L-shape, and two-level corner cases have exactly six quad faces per cell; every internal face has two owners; no hanging topology; all signed Jacobian samples positive.
- Option B: retain split-face polyhedra, rename/advertise output as hex-dominant, and make hex ratio a quality gate.
- Stop rule: do not describe Option B as Maréchal all-hex.

### HEX-OCT-3 - thickness/intersection refinement

- Mark any cell intersected by a source triangle and enforce at least two cells across measured local thickness where budget allows.
- Pass: thin plate, narrow gap, and acute wedge remain connected; no source component vanishes; refinement cap failure returns explicit diagnostic rather than a silent coarse mesh.

### HEX-OCT-4 - constrained projection transaction

- Give each boundary entity stable face/ridge/corner provenance. Trial move uses line search and commits only if local cell validity and quality floor hold.
- Pass: 30-degree ridge, cube corner, and curved wall improve bidirectional surface error without increasing inverted cells; rejected vertices and residual error are reported.

## Decision

Use this paper for octree sizing, transition topology, feature provenance, and projection architecture. Do not cite it as validation of the current adaptive implementation until either the dual all-hex path exists or the engine explicitly reports hybrid polyhedral transition cells.
