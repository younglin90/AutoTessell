# Native poly boundary-edge separator evidence (2026-07-31)

## Card

`POLY-DUAL-WARPED-SEPARATOR-SI-ROOTCAUSE-1`

Primary metric: self-intersection pairs caused by boundary-edge separators.
Acceptance requires zero pairs without moving points, changing source caps,
relaxing star admission, or weakening validity thresholds.

## Root cause

Path 3b' emitted an open tetrahedron fan around each primal boundary edge as
one polygon:

`[source-face centroid A, tet centroids..., source-face centroid B, edge midpoint]`.

The loop is generally non-planar.  OpenFOAM's implicit polygon triangulation
can therefore cut through an adjacent exact source cap.  On the cylinder
diagnostic the first pair was:

- separator triangle `[320, 193, 321]` from face
  `[320, 192, 193, 321, 353]`
- cap triangle `[353, 464, 532]` from exact source cap
  `[353, 321, 464, 532]`

The worst separator had six vertices and planarity deviation/diameter
`0.372693`.

## Repair

The primal topology defines a unique barycentric fan.  For each boundary edge,
the implementation now anchors consecutive open-chain segments at the exact
primal edge midpoint:

`[edge midpoint, chain[i], chain[i+1]]`.

Every triangle keeps the original owner/neighbour pair.  Interior closed rings
are unchanged.  No coordinates, source caps, labels, tolerances, star
admission, or target-cell logic change.

## Evidence

Exact counterfactual rewrite of the 73-cell cylinder diagnostic:

| metric | warped polygon | barycentric fan |
|---|---:|---:|
| internal faces | 348 | 800 |
| total faces | 732 | 1184 |
| cells with closed-edge failure | 0 | 0 |
| self-intersecting cells | 39 | 0 |
| self-intersection pairs | 60 | 0 |
| repeated/degenerate faces | 0 | 0 |
| negative/inverted cells | 0 | 0 |
| max face planarity deviation/diameter | 0.372693 | 0.143262 |
| max non-orthogonality | 81.074 | 82.611 |
| input-surface on ratio | 0.999999999989 | 0.999999999989 |
| input-surface off area | 0 | 0 |
| enclosed/source volume ratio | 1.044711 | 1.034645 |

The remaining `0.143262` planarity is confined to unchanged interior closed
rings.  Source caps stayed planar (`8.88e-10` maximum diagnostic deviation).

The synthetic pyramid test now requires every internal face incident to a
source boundary-edge midpoint to be triangular.  It also checks exact 24-cap
provenance, per-cell edge incidence two, and zero exact shell intersections.

Focused native/Python dual validity and provenance regression:

```text
22 passed in 2.54s
```

The classified byte/provenance oracle passed three fresh processes in
`2.21s`, `2.03s`, and `2.11s`; all five polyMesh digests matched.

Cube solid-volume regression, run with the release native extension:

```text
4 passed in 35.62s
```

## Deterministic diagnostic hashes

The runtime-only 73-cell cylinder candidate used for the exact rewrite had:

- `points`: `69cefd3575523b71f7c5b3755a0569574e2ec8d6b43e4d9e0b3db417c02d7cbb`
- `faces`: `9d29a5cd9b68427813c7b371df356e25f2bcfe3ccca31d64159e5dbec88c93d1`
- `owner`: `04335ec339798238ab80da006881cdf833ec9715640507adde6dcd2c2a66f1ff`
- `neighbour`: `b8848c7b1e4e1d0cc520a8165d12d68d96f972290c4eaea16bc20f53c615c249`
- `boundary`: `ffe9164f28003c1986701960684bebaaf8d0bc9324b78153e22dafb5f8705758`

## Remaining gate

Production cylinder generation still rejects both point-placement candidates
at the unchanged star-validity gate (`54/73` cells, `539` invalid sub-tetrahedra)
and then reaches the slow fallback.  Runtime-only admission also has maximum
skewness `38.1916`.  Star-kernel construction, skewness, and the cylinder
module timeout therefore remain separate fail-closed blockers.  This commit is
not an integration-success claim and remains unmerged pending module acceptance.
