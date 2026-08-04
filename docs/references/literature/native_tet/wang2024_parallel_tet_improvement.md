# Wang et al. — Multi-threaded Parallel Tetrahedral Mesh Improvement by Combining Atomic Operation and Graph Coloring (2024)

**Title:** Multi-threaded parallel tetrahedral mesh improvement by combining atomic operation and graph coloring
**Authors:** Yifu Wang, Junji Wang, BoHan Wang, Yifei Wang, Jianjun Chen (Zhejiang University, School of Aeronautics and Astronautics)
**Year / Venue:** 2024 — Advances in Engineering Software 198 (2024) 103782 (Elsevier)
**DOI:** `10.1016/j.advengsoft.2024.103782`
**Pages read:** 12/12 (journal layout of `docs/references/papers/source/pdf/14_wang_2024_parallel_tet_improvement.pdf`; the task brief's "36 pages" refers to a preprint pagination — the archived PDF is the final 12-page journal version, read in full)
**Status:** FULL_READ
**Date:** 2026-07-23

## Core design

**Scope.** Shared-memory (OpenMP) parallelization of a classic 4-operation tet
improvement loop: (1) vertex smoothing, (2) topological reconnection (edge
removal, face removal — including recursive shell transformation and n-to-m
flips), (3) vertex insertion, (4) edge contraction. The stated goal is to keep
the serial kernels unchanged and wrap them with a thin parallel guard layer.

**Two-regime split (the paper's central architectural decision):**

| Operation family | Parallel scheme | Why |
|---|---|---|
| Vertex smoothing | **Graph coloring** (Freitag-style vertex coloring, parallel multi-round coloring, smaller-vertex-index colored first per edge) + OpenMP `schedule(dynamic)` | Topology is fixed during smoothing, so a color class is provably conflict-free; dynamic scheduling absorbs the uneven per-vertex cost of numerical optimization smoothing |
| Topology-altering ops (flip/insert/contract) | **Vertex-based atomic token marking** + coordinate-sort partitioning + OpenMP `schedule(static)` + thread-local memory pools | Coloring assumes a fixed graph; these operations mutate the graph, so precomputed colorings are invalidated. Instead each op try-locks its neighborhood with atomics and postpones on conflict |

**Conflict-neighborhood definition (Section 4.1.1, uniform across op types):**

- *Cavity* `C(t_i)` = the set of elements whose topological connections the
  operation changes (flip shell, B–W insertion cavity, contraction star).
- *Operation ambient* `A(t_i)` = union of one-ring neighbor elements of the
  cavity, minus the cavity itself (needed because adjacency pointers of ambient
  elements are rewritten on refill).
- **Principle 1 (non-overlap):** for concurrent ops, `C1 ∩ C2 = ∅` and
  `C1 ∩ A2 = C2 ∩ A1 = ∅`. Ambient-ambient overlap is allowed.

**Atomic-op scheme.** Two variants are analyzed. Element-based marking marks
`C` then `A` in two steps (for an edge removal touching N tets: N + 2N = 3N
atomics, plus a mark-gap race window between the two steps). The adopted
**vertex-based** marking instead atomically CAS-tags a per-vertex token with the
thread id: marking the N+2 vertices of the edge-removal shell suffices to cover
both cavity and ambient, cutting atomic count from 3N to N+2 and closing the
two-step gap. The token acquisition is fused into cavity search
(Algorithm 2): if any needed vertex is already tokened by another thread the op
returns `Overlap` *before* the serial kernel runs (pessimistic try-lock /
postpone, no partial-work rollback ever needed). On success the serial kernel
runs, then tokens are cleared. Conflicted tets are recycled back into the
thread's own bad-tet subset and retried in a later sweep.

**Scheduling / task decomposition.** Bad tets (dihedral < 30° or > 150°,
quality < Q_target) are gathered and partitioned by **coordinate-sort
partitioning** (Algorithm 1): choose a×b×c = N_threads minimizing a+b+c, sort
tet centroids along the axis with most spread, split into a slabs, recursively
sort/split each slab along the 2nd and 3rd axes. This yields connected,
load-balanced, axis-aligned blocks — explicitly preferred over Hilbert-curve
presorting, which orders well but does not guarantee each thread a *connected*
region. Blocks are statically scheduled; Fig. 10 shows per-thread op counts and
wall time remain balanced anyway. Measured effect (Fig. 9): spatial
pre-partitioning cuts overlap probability P_overlap by 1–5 orders of magnitude
vs. no partitioning, and beats Hilbert sorting in early iterations; the
advantage decays near convergence when surviving bad tets cluster at complex
boundaries.

**Memory model.** Each thread gets a pre-allocated exclusive memory pool for
element creation/destruction (refill of cavities), eliminating allocator
synchronization; only pool exhaustion synchronizes with the main pool.

**Outer loop (Algorithm 3).** Per iteration: parallel coloring → parallel
smoothing (all vertices) → collect bad tets → partition → parallel topology
pass (edge removal, face removal, insertion, contraction per bad tet) →
repeat until Q_min ≥ Q_target or loop_max. A simulated-annealing-style
relaxation loosens vertex-insertion restrictions when quality plateaus, to
escape local optima.

## Determinism (CRITICAL for AutoTessell)

**Verdict: the algorithm is NOT run-to-run deterministic, at fixed or varying
thread count, and the paper never claims otherwise.** The paper's own words
(Section 5.1):

> "in parallel mesh improvement, the overlapping of improvement tasks can
> alter the sequence of task execution, introducing unpredictable randomness."

and the mitigation offered is convergence-level, not reproducibility-level:

> "each mesh improvement operation inherently enhances the mesh (hill-climbing
> method), and the strategy of multiple rounds of optimization ultimately
> ensures the convergence of mesh quality."

Supporting observations:

- Whether an op is postponed depends on OS thread timing (token races), so the
  effective op ordering — and therefore the final mesh — varies between runs
  even at a fixed thread count. Static partitioning fixes *assignment*, not
  *interleaving*; postponed-op retry order is timing-dependent.
- The measured consequences are visible in Table 1: average metrics
  (θ^Avg_min, AR_Avg, ES_Avg) and element counts match the serial run
  essentially exactly, but extreme metrics wobble in both directions
  (F-16 θ_min 3.9° serial vs 4.2° parallel; Straight Microstrip 5.7° vs 4.7°;
  Ship AR_max 271.7 vs 320.9; Microstrip AR_max 194.4 vs 4.23 — that last one
  is a dramatic, lucky improvement, underscoring how unpinned the extremes are).
- Speedups are reported with run-to-run spread (6.2 ± 0.29 at 8T,
  10.18 ± 0.44 at 16T, "after multiple rounds of experiments"), consistent
  with nondeterministic execution.
- No discussion of floating-point reduction ordering, seeded tie-breaking,
  deterministic retry rounds, or replayability appears anywhere in the paper.
  Quality parity is the *only* equivalence claim made (Principle 3: parallel
  quality "should not be significantly inferior" — an explicitly weak,
  statistical contract).

This directly validates AutoTessell's roadmap ordering: a correctness gate
built only on aggregate quality stats would pass this algorithm while
element-level reproducibility silently disappears. Determinism must be
gated *before* parallel enable, exactly as the evidence-matrix row demands.

## Experiments

- **Hardware:** laptop-class 16-core AMD 7950X @ 4.5 GHz, 128 GB RAM
  (NUMA effects noted at 16 threads).
- **Dataset:** 14 industrial models, 1.0M–102.3M tets (Launch vehicle, Blade,
  F-16, Rotor, Turbine, Submarine, Tower, Ship, Aircraft, 5 Microstrip
  variants). Inputs are Delaunay-refined meshes with many slivers but
  size-bounded vertices (which bounds cavity sizes — noted as a reason static
  scheduling stays balanced).
- **Speedup:** 6.2 ± 0.29× at 8 threads; **10.18 ± 0.44× at 16 threads**.
  Worst cases: Rotor 9.80× (complex boundary → conflict clustering), Launch
  9.73× (only 1M tets → thread overhead dominates). Aircraft (102.3M):
  6825.8 s → 675.3 s. (Note: the introduction's "37 min to 219 s" figure
  matches the Ship row (2061.8 s → 209.0 s) rather than the largest model —
  a minor internal inconsistency.)
- **Per-phase parallel efficiency at 16T** (Table 2): smoothing ~91% (63–65%
  of total time), topology ops ~78–88% (7–10% of time), preprocessing ~75–83%,
  graph coloring only ~55–62% (25–27% of time; memory-bandwidth and
  cache-coherence bound — the true scalability bottleneck), identify&partition
  serial but ~1.2% of time.
- **Quality parity** (Table 1, vs serial self and TetGen `q1.0/15`): parallel
  ≈ serial on all averages and sub-10°/20°/30° dihedral histograms; extremes
  fluctuate slightly (both directions). Their improver (serial or parallel)
  beats TetGen substantially on worst dihedral angles; TetGen wins on average
  aspect ratio — different optimization priorities.

## Limitations

**Stated:** graph coloring phase memory-bandwidth-bound (~57% efficiency at
16T); NUMA constrains 16-thread scaling; complex boundary constraints (Rotor)
cluster residual bad tets and raise conflicts near convergence; small meshes
(1M) suffer thread-management overhead; coordinate-sort advantage over Hilbert
decays as bad tets concentrate at boundaries; data not publicly available.

**Inferred:** (1) No determinism or replay contract at all (see above).
(2) Quality-parity contract is statistical only; extreme-metric variance is
accepted, which is incompatible with regression tests pinned to exact meshes.
(3) Shared-memory single-node only; the coloring bottleneck caps scaling well
before 16× — extrapolation beyond 16T is unsupported. (4) Postpone-and-recycle
can livelock-in-principle at heavily contended boundary clusters; the paper
relies on iteration caps rather than progress guarantees. (5) Boundary
constraint handling during parallel ops (surface-conformity checks) is never
detailed — surface preservation, AutoTessell's #1 invariant, is not part of
their conflict model. (6) No memory-overhead numbers for the per-thread pools.
(7) Token scheme correctness (e.g., mark-clear ordering, ABA on recycled
vertices) is asserted, not proven.

## AutoTessell applicability

**Evidence matrix row (upgrade from ABSTRACT_ONLY → FULL_READ), Wang 2024:**
the existing guidance — *"gate behind deterministic serial kernel: first
validate reproducibility and edge-overlap safety before parallel enable"* — is
**confirmed and strengthened** by the full text: the paper's own quality data
shows extreme-metric drift between serial and parallel runs, and its only
safety principle (Principle 1 non-overlap of cavity+ambient) is precisely the
"edge-overlap safety" our row anticipates. Keep the row; add: "conflict
neighborhood = cavity ∪ one-ring ambient; vertex-token try-lock with
postpone (no rollback) preserves serial kernel semantics; determinism is
explicitly sacrificed — parity is statistical only."

**Conflict-model comparison (Wang 2024 vs Mahmoud et al. 2025, the native_tri
parallel evidence — patch-local speculative conflicts + rollback on GPU):**

- Wang: **pessimistic** — atomically try-lock the vertex tokens of
  cavity+ambient *before* executing the unchanged serial kernel; on conflict,
  postpone and retry later. No speculative state, no rollback of mesh data.
- Mahmoud: **optimistic** — execute patch-local edits speculatively in
  shared memory, detect conflicts, roll back losers. Pays rollback machinery
  and versioned state; wins on massive GPU thread counts where locking
  serializes.

**Verdict for AutoTessell: Wang's model is the better fit** for the native_tet
transactional guarded-local-edit architecture, for three reasons.
(1) AutoTessell's edits already follow "build candidate → run guards →
commit or discard"; Wang's pre-execution token acquisition slots in as one
more guard *before* the kernel, leaving commit logic untouched — Mahmoud's
scheme would instead require versioned mesh state and post-hoc undo of
committed topology, a much deeper rewrite. (2) Target hardware is CPU
multi-core (16–64 threads), the regime where pessimistic postponement is
cheap and speculation's advantage (thousands of GPU warps) never materializes.
(3) Wang's postpone queue is the easier model to *make deterministic*: fix the
partition (coordinate sort is already deterministic), replace timing-dependent
token races with round-based conflict resolution (deterministic priority =
partition index, deferred losers retried in fixed rounds), and the schedule
becomes replayable — a path Mahmoud's timing-driven speculation does not
offer. Mahmoud remains the right reference for a far-future GPU tier.

**Candidate cards (design/bench-only, no default-ON parallelism):**

- **TET-PAR-0 — Conflict-neighborhood instrumentation (design/measure only).**
  Mechanism: implement Wang's `C(op)` / `A(op)` (cavity + one-ring ambient)
  computation for native_tet's existing local operators and, running fully
  serially, log the overlap graph of consecutive ops plus P_overlap under a
  simulated coordinate-sort partition (Wang Algorithm 1). No parallel
  execution, no mesh-output change. Acceptance signal: overlap-probability
  report on the bench STL set showing the 1–5 order-of-magnitude partitioning
  effect reproduces on our meshes; ops' cavity/ambient sets validated against
  actual touched-element sets (zero under-approximation). Risk: none to mesh
  output (pure instrumentation); moderate implementation cost in adjacency
  queries.
- **TET-PAR-1 — Deterministic round-based parallel topology pass
  (bench-only, env-flag OFF by default).** Mechanism: coordinate-sort
  partitioning + vertex-token try-lock as in Wang, but with deterministic
  conflict resolution (fixed priority by partition/op index, losers deferred
  to the next synchronized round) instead of timing races, plus thread-local
  arenas. Acceptance signal: (a) bit-identical polyMesh output across repeated
  runs at fixed thread count AND across 1/2/4/8 threads; (b) quality parity
  with the serial pass within the existing NativeMeshChecker gates; (c)
  speedup ≥ 4× at 8 threads on ≥1M-cell benches. Risk: determinism costs some
  of Wang's ~85% topo-phase efficiency (round barriers); known native-heap
  fragility under pytest multi-invocation (see lessons-learned) makes bench
  isolation in subprocesses mandatory; surface-conformity guards must be part
  of the conflict neighborhood (Wang never addresses boundary preservation —
  our #1 invariant).

## References worth snowballing (max 5)

1. **Zangeneh & Ollivier-Gooch 2018** — Thread-parallel mesh improvement using
   face/edge swapping and vertex insertion, Comput Geom 70–71:31–48,
   `10.1016/j.comgeo.2018.01.006`. Direct predecessor for atomic-op-based 3D
   topology parallelism.
2. **Drakopoulos, Tsolakis & Chrisochoides 2019** — Fine-grained *speculative*
   topological transformation scheme for local reconnection, AIAA J 57,
   `10.2514/1.J057657`. The CPU-side speculative counterpart — the missing
   third point between Wang (pessimistic CPU) and Mahmoud (speculative GPU).
3. **Marot, Pellerin & Remacle 2018** — One machine, one minute, three billion
   tetrahedra, IJNME, `10.1002/nme.5987`. Multithreaded Delaunay at extreme
   scale; source of the multi-round conflict-reduction strategy Wang cites.
4. **Chen et al. 2017** — Tetrahedral mesh improvement by shell
   transformation, Eng Comput 33:393–414, `10.1007/s00366-016-0480-z`. The
   recursive-shell serial kernel that Wang's vertex-token scheme wraps; defines
   the op family native_tet would parallelize.
5. **Remacle 2017** — A two-level multithreaded Delaunay kernel, CAD 85:2–9,
   `10.1016/j.cad.2016.07.018`. Documents why the naive barrier-synchronized
   parallel insertion fails (load imbalance + overhead) — the negative result
   motivating both Wang's and our design.
