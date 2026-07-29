# MFRC Notes - 2026-07-22

Goal: reduce native-tet plateau cases where 2-3, 3-2, 4-4 flips and local
smoothing cannot improve worst sliver neighborhoods.

## Paper Direction

- Misztal, Baerentzen, Anton, Erleben, `Tetrahedral Mesh Improvement Using
  Multi-face Retriangulation`.
  Source checked: https://backend.orbit.dtu.dk/ws/files/4566784/mfrt_paper.pdf
- Ma and Wang, `An efficient method to improve the quality of tetrahedron mesh
  with MFRC`.
  Open text checked: https://pmc.ncbi.nlm.nih.gov/articles/PMC8611015/
- Klingner and Shewchuk, `Aggressive Tetrahedral Mesh Improvement`.
  Source checked earlier: https://people.eecs.berkeley.edu/~jrs/papers/aggress.pdf

Common point: single flips affect tiny cavities. When flip search reaches a
local minimum, a larger bounded cavity can cross the quality valley while
preserving the same boundary.

## Implemented Card: MFRC1

File: `core/generator/native_tet/mfrc.py`

Implemented standalone helpers:

- `extract_edge_cavity`: find closed internal edge-ring cavity.
- `enumerate_edge_mfrc_candidates`: remove the edge, triangulate the ring
  polygon, build two tet fans, validate boundary/volume/quality.
- `propose_edge_mfrc`: choose best accepted candidate by local quality-vector
  rank.
- `apply_edge_mfrc`: replace only owner tets in a copy.

This includes 3-face and 4-face cases. The 3-face case covers 3-2 behavior.
The 4-face case covers 4-4-like edge removal alternatives. Larger rings are
bounded by `max_ring_vertices` and `max_triangulations`.

## Guards

- same local boundary faces before/after;
- non-degenerate new volumes;
- absolute local volume sum preserved;
- local sorted quality vector improves;
- no mesher hook yet.

## Why Not Hook Yet

Native tet current worst cases need topology changes, but direct mesher
integration needs ownership guards:

- protected boundary/feature edges;
- envelope rollback;
- conflict-free scheduling with existing flip pass;
- full matrix comparison against QOPT4/QOPT5 baseline.

MFRC1 is therefore infrastructure and parity tests only.

## Next Integration Point

Add a worst-first pass after `flip_edges_44` and before smoothing:

1. collect internal edges adjacent to worst quality percentile;
2. skip protected boundary/feature edges;
3. call `propose_edge_mfrc`;
4. apply one non-overlapping accepted cavity per pass;
5. run existing signed-volume and fidelity guards;
6. compare focused cases first: `pipe.step`, `03_hard_bracket.stl`,
   `04_extreme_gear.stl`.
