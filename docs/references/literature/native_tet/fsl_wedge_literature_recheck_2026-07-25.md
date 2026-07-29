# FSL Wedge Literature Recheck (2026-07-25)

Validation check requested before starting Phase 1 implementation (3-wave attack
on the 61 structurally coplanar-flat unflippable wedges, dual_torus). Question:
does anything published 2019+ supersede the Dassi 2018 + Ni 2017 + Cheng & Dey
2003 evidence base already selected in `evidence_matrix.md` and
`native_tet_literature_integrated_development_plan_2026-07-23.md`? This is a
recheck, not a new literature pass — only flagged if it would change the plan.

## What was searched

Web searches (2019+ filter where the engine honored it):
- "coplanar flat tetrahedra removal guaranteed sliver elimination"
- "unflippable tetrahedra topology repair edge removal mesh generation"
- "degenerate sliver guaranteed removal insertion tetrahedral mesh"
- "structural sliver elimination tetrahedral mesh CFD repair"
- "flat sliver tetrahedra CFD mesh repair unflippable wedge"
- "edge removal" / "multi-face removal" tetrahedral sliver topological improvement
- "sliver exudation" / "weight pumping" boundary follow-up to Cheng & Dey
- fTetWild successor / exact-envelope sliver removal 2022-2024
- "coplanar tetrahedra cannot be flipped" Steiner insertion guaranteed repair

Citation-direction checks: Semantic Scholar page for Dassi et al. 2018 (fetch
returned no usable citation list — search-based citation lookup used instead);
general search for works citing Ni et al. 2017 by name/authors.

## What was found

No paper surfaced that targets exactly our failure class — structurally
coplanar (exactly flat, zero-volume-in-any-retriangulation), boundary-pinned,
unflippable-under-any-topology-change tetrahedra — with a mechanism stronger
than Dassi 2018 + Ni 2017 + Cheng & Dey 2003 combined. Two tangential
candidates surfaced; both screened out:

1. **Ma & Wang 2021, "An efficient method to improve the quality of tetrahedron
   mesh with MFRC"**, *Scientific Reports* 11, 21730 (2021).
   DOI `10.1038/s41598-021-02187-1` — **resolves** (redirects to
   nature.com/articles/s41598-021-02187-1). OPEN full text (Scientific Reports).
   MFRC (multi-face reconstruction) extends edge/multi-face removal to
   larger, expanded-cavity retriangulation, explicitly does not touch boundary
   elements, and targets generic low-quality tets (not specifically exact
   coplanarity). This is a *stronger search radius for the same combinatorial
   idea* our plan already adopts in Wave 1 (`TET-SHAPE-3(a)`, sourced from
   Ni 2017's citation of Shewchuk's edge/multi-face removal). A larger cavity
   does not create a valid non-degenerate retriangulation out of vertices that
   are themselves exactly coplanar — the same geometric limit Dassi 2018
   already states explicitly ("exactly coplanar/degenerate geometry can be
   unflippable at any search depth"). Reinforces Wave 1's premise rather than
   changing it. Not worth a dedicated read; the mechanism it would add
   (bigger-cavity combinatorial search) is a tuning parameter of `TET-LAZY-1`
   / `TET-SHAPE-3(a)`, not a new class of fix.

2. **Quiriny, Lambrechts, Moës, Kučera, Remacle 2026, "Taming Slivers: A Robust
   TFEM Framework for Reliable Computations on Degenerate Tetrahedral
   Meshes"**, arXiv:2606.14301 (submitted 2026-06-12).
   DOI `10.48550/arXiv.2606.14301` — **resolves**. OPEN (arXiv preprint).
   Different problem in kind: this is a *solver-side* tolerance method
   (Tempered FEM, bounds the Jacobian determinant so a degenerate element
   doesn't singularize the stiffness matrix) — it does not remove, repair, or
   even classify slivers; it lets a downstream FEM solver compute through
   them. Auto-Tessell's deliverable is an OpenFOAM `polyMesh` for a standard
   FVM solver, not a TFEM solve — this paper answers a different question
   (how to compute despite bad elements) than ours (how to remove structurally
   bad elements from the mesh itself). Does not change the plan; noted here so
   the "accept slivers, harden the solver" alternative philosophy is on record
   as considered and out of scope.

No other 2019+ candidate appeared across five distinct query framings and two
citation-direction checks. The searches repeatedly surfaced the same
pre-2019 canon already in the evidence matrix (Shewchuk topological-ops
manuscript, Klingner & Shewchuk 2007 Stellar, Cheng/Dey/Edelsbrunner sliver
exudation lineage, Labelle's lattice refinement, Li & Teng 2001) — consistent
with the plan's own citation list, not contradicting it.

## Verdict

**Proceed straight to implementation with the existing 3-wave plan.** No gap
was found and none is manufactured here: Dassi 2018 (`TET-LAZY-1`, reversible
compound flips) + Ni 2017 (`TET-SHAPE-3`, multi-face removal then
GSM-gradient-directed insertion) + Cheng & Dey 2003 (`TET-WDEL-1`/`TET-WDEL-2`,
interior-only weight pumping with a PUMPABLE/LOCKED classifier) still jointly
cover the full decision tree: combinatorial re-test first, then interior
pumping for survivors, then guarded insertion as last resort. Nothing found
changes card sequencing, adds a wave, or removes a wave.

No download queue — neither candidate above changes the plan enough to
warrant a full read before Phase 1 starts.
