# STELLAR1 Notes

Scope: native tet only.  Main mesher path is unchanged.

Paper basis:
- Klingner and Shewchuk, Stellar: tetrahedral mesh improvement by local
  transformations.  The useful idea here is not one blind flip.  It is bounded
  local-cavity search with rollback when the sorted quality vector does not
  improve.
- Freitag/Ollivier-Gooch and TetWild/fTetWild use the same practical rule:
  local operation candidates must be guarded by inversion checks and monotone
  local quality acceptance.

Implemented helper:
- `insert_edge_midpoint_qopt_cleanup` in `core/generator/native_tet/stellar.py`.
- It selects a bounded edge cavity, inserts one midpoint, splits incident tets,
  rejects near-zero volumes, then accepts only if the QOPT sorted quality vector
  improves.
- It is deliberately helper-only.  No `mesher.py` or global flip path changed.

Why this matters:
- Current native tet plateau is not from Python speed only.  The remaining gap
  is missing robust topology-changing local search.
- This helper gives a safe primitive for later Stellar-style edge removal and
  vertex insertion scheduling without risking surface preservation yet.

Next blocker:
- Full edge removal needs alternate cavity retriangulation, not just midpoint
  split.  That requires a bounded cavity enumerator or small CDT/Delaunay
  retetrahedralizer before it should be enabled in the main pipeline.
