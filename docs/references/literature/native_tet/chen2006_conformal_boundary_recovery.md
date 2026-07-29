# Chen--Zheng 2006 — conformal boundary recovery

- Citation: Jian-jun Chen and Yao Zheng, *Redesign of a conformal boundary
  recovery algorithm for 3D Delaunay triangulation*, J. Zhejiang Univ. SCIENCE
  A 7(12), 2031-2042 (2006).
- DOI: `10.1631/jzus.2006.A2031`.
- Status: FULL_READ from the publisher's public full text on 2026-07-28.
- Archived source: `docs/references/tetrahedral_meshing/chen2006_conformal_boundary_recovery.pdf`
  (SHA-256 `76db209b65715a17a5f00cc3aa93d87a303cbc878c67148ec15b098641b10265`).
- Official source: https://jzus.zju.edu.cn/opentxt.php?doi=10.1631%2Fjzus.2006.A2031

## Implementation-relevant evidence

The paper separates missing-edge recovery from missing-facet recovery. A facet
clusterel is classified by zero through four strict cutting edges. `ONE_EDG`
and `TWO_EDG` reuse pipel cases; only `THR_EDG` and `FOU_EDG` use S/Z facet
decompositions.

Table 11 (p. 2038) gives four `THR_EDG` rows: S2/Z1, S1/Z2, S3/Z0, and S0/Z3.
The all-S and all-Z rows require an additional Steiner point `H`; the table
does not specify a numerical placement rule for `H`, so AutoTessell must not
invent one. The S2/Z1 and S1/Z2 rows have no `H`; both literal four-child
connectivities are now held in `chen_thr_edg_table11_l0.py`, under exact
boundary/volume/orientation checks.

## Scope restriction

The source's neighbour-table notation (`NG`, `Phi`) is not yet a production
mesh API. The no-H cards are isolated local certificates only. Before any
native recovery integration, derive the full finite source-triangle cavity,
the complete Phi closure, and a global atomic original-boundary transaction.
