# Jiang et al. - Declarative Specification for Unstructured Mesh Editing Algorithms

## Bibliography and access

- Zhongshi Jiang, Jiacheng Dai, Yixin Hu, YunFan Zhou, Jeremie Dumas,
  Qingnan Zhou, Gurkirat Singh Bajwa, Denis Zorin, Daniele Panozzo,
  Teseo Schneider.
- *ACM Transactions on Graphics*, 41(6), Article 251, 14 pages, December 2022
  (SIGGRAPH Asia 2022). This is the wildmeshing-toolkit paper.
- DOI: `10.1145/3550454.3555513`.
- Open access: author-hosted PDF at
  `https://web.uvic.ca/~teseo/profile/publications/toolkit/2022-WildMeshingToolkit.pdf`
  (path recorded in `citation_snowball_batch2.md`, section E).
- Local copy: `papers/pdf/43_jiang_2022_wildmeshing_toolkit.pdf`,
  SHA-256 `5afddbf56bc06adefb34e2ab28e3a3fad0d67b394672cc1dbaae3090255aef42`.
- Code: `https://github.com/wildmeshing/wildmeshing-toolkit` (open source).
- Review status: `FULL_READ` on 2026-07-23. All 14 pages text-extracted and
  read (pages 12-14 are acknowledgments and references).

## Problem and contract

Mesh-editing algorithms (any algorithm that changes connectivity: decimation,
remeshing, tet meshing, mesh improvement) are conventionally written against a
specific low-level data structure, forcing each author to hand-roll (a)
operation "simulation" to evaluate energies/conditions before committing, (b)
per-operation invariant checking, (c) attribute bookkeeping across topology
changes, and (d) parallelization with race avoidance. The paper's claim: raise
the abstraction so the author writes a *declarative specification* and a
generic runtime supplies simulation, rollback, invariant enforcement, and
shared-memory parallelism automatically.

## The IDAS specification model (what an author writes)

The specification is named IDAS - Invariants, Desiderata, Attributes,
Schedule:

1. **Invariants** - hard per-element requirements (e.g., positive volume, no
   self-intersection, envelope containment). The runtime checks them after
   every operation on every modified element and after input load; if a check
   fails the operation is rolled back. Guarantee shape: *if* the user's
   invariant predicate is correct, the runtime ensures it holds on all
   elements at all times.
2. **Desiderata** - soft objectives (element quality, target edge length),
   maximized best-effort via operation priorities, not guaranteed.
3. **Attributes** - user data attached to any simplex, with explicit
   user-provided update rules per operation.
4. **Schedule** - which operation types run, in what priority order, with what
   termination rule.

Concretely the API is two classes (C++):

- `TriMesh`/`TetMesh` own topology and provide the built-in local operations:
  `split_edge`, `collapse_edge`, `swap_edge` (3-2, 4-4), `swap_face` (2-3),
  `smooth_vertex`, plus a non-standard `insert_triangle` (multi-simplex
  subdivision to embed an input triangle, using the connectivity tables of
  TetWild/Hu 2019b - the arrangement primitive). The user subclasses and
  overrides paired hooks per operation: `X_before(t)` sees the valid
  pre-operation mesh (to cache attributes / evaluate pre-energy) and
  `X_after(t)` sees the valid post-operation mesh (to write new attributes /
  evaluate post-energy), each returning bool. A false return, or a failed
  `invariants(new_simplices)` check, triggers automatic rollback of both
  topology and attributes to the previous valid state. Navigation is only
  through the data-structure-agnostic cell tuple (Brisson 1989): a Tuple holds
  (vertex, edge, face, tet) indices with one `switch_*` function per index.
- `Scheduler` takes callbacks: `priority` (orders operations),
  `renew_neighbor_tuples` (re-enqueues affected neighborhood after a success;
  stale queue entries are auto-invalidated by a tuple tagging mechanism),
  `lock_vertices` (declares the lock footprint per operation),
  `stopping_criterion`, `should_process`, plus `num_threads` and
  `max_retry_limit`.

Shortest edge collapse in this form is roughly 15 lines of before/after code
plus 30 lines of scheduler setup (their Algorithms 3-4). The before/after
split is exactly the "simulate, check, commit-or-rollback" transaction our
native-tri plan calls a guarded local operation; here it is the *only* way to
write an operation.

## Runtime, conflict handling, and determinism

Implementation: C++ with Intel oneTBB; indexed data structure (vertices store
incident-simplex lists, simplices store sorted vertex lists) - chosen for
simple local operations, admittedly not the fastest for navigation.

**Locking model.** One mutex per *vertex*. Any read or write of an attribute
on a vertex/edge/face/tet - including navigation and connectivity updates -
requires holding the locks of all vertices of every tet containing that
element. Per operation the runtime pre-acquires a ring: 1-ring of the vertex
for smoothing, 2-ring of both endpoints for edge collapse. Acquisition is
tentative and asynchronous: if any lock is already taken, all acquired locks
are released and the operation is skipped, which also prevents deadlock (the
2-ring footprint is stated to be sufficient for deadlock-freedom for all
implemented operations). Skipped operations are retried (default 10 times)
and *run serially* if they still fail. The mesh is pre-partitioned with
Morton encoding (Karras 2012) to keep threads spatially separated (Section
2.3 also mentions METIS graph partitioning for the same purpose; the
implementation section names Morton, so treat METIS as the earlier/general
statement). Lock overhead is small per event (~2.7-4.5e-7 s per lock, Table
1) but locks are acquired ~1e8 times in remeshing runs, so single-thread
overhead vs. pure serial ranges from ~14% (collapse) to ~3.2x (harmonic
triangulations: 13.0s serial vs 42.2s one-thread).

**Determinism verdict: explicitly nondeterministic.** The paper states plainly
that "our concurrent implementation is not deterministic" (Section 4.1) and
quantifies the run-to-run spread as minor: five parallel uniform-remeshing
runs give average valence 5.999 with std dev 9.885e-7, and average Hausdorff
distance 0.5% of the bbox diagonal vs. the serial result (std 0.2%). Two
further consequences are documented: (a) parallel execution cannot preserve
the user's priority order - a conflicting operation is postponed, so e.g.
longest-edge-first splitting locally degrades (their Figure 10); (b) in the
parallel TetWild run, postponed conflicting operations leave a few very
low-quality tets (AMIPS > 400) at a fixed iteration budget, which disappear
only with extra iterations (Figure 9). There is no seeded replay, no
partition-independent commit order, and no bitwise-reproducibility contract
(contrast Ibanez's Omega_h, which makes that a design goal). Determinism is
simply traded away for lock simplicity.

## Invariant system: what is built-in vs. user-supplied

Built into the runtime: topological validity of the built-in operations
(manifold simplicial connectivity via the operation implementations and
connectivity tables), the before/after transaction with automatic rollback of
topology *and* attributes, invariant re-checking after every modification and
at input load, and stale-queue-entry invalidation. Not built-in as named
predicates: inversion checks, self-intersection, and envelope containment are
all *user-provided invariants* - the framework's pitch is that they slot in
uniformly. Their showcase: adding the exact polyhedral envelope check of Wang
et al. 2020 (fast envelope) to shortest edge collapse and to uniform
remeshing "only requires adding the envelope check to the invariants" - a
few lines (Section 4.2, Figures 11-12). Link-condition-style admissibility is
inside the mesh classes' operation implementations rather than exposed as a
spec-level invariant. Intersection-free simulation (Brochu-style CCD
constraints) is discussed as an easy extension, not demonstrated.

## Performance evidence

Consistent pattern across the five applications: the generic runtime loses to
hand-tuned serial code, and automatic parallelism buys it back on enough
threads.

- Shortest edge collapse (282k faces): serial 4.9s vs libigl 2.74s; 0.52s at
  32 threads (11x self-speedup, up to 9x faster than libigl).
- QSlim (1.9M faces): libigl serial is ~8x faster (41.3s vs 306.6s) because
  libigl mutates the queue directly per collapse; theirs wins ~2x from 16
  threads (13.9s at 32 threads, 25x self-speedup).
- Isotropic remeshing (Botsch-Kobbelt, 2.5M faces): OpenFlipper serial 2.5x
  faster; theirs wins past 4 threads (8.2s at 32 threads vs 31.96s, 11x
  self-speedup).
- Harmonic triangulations (1M points): 2x slower serial than the authors'
  code, 2x faster at 32 threads (3.82s, 11x self-speedup).
- TetWild reimplementation (856k input faces): 153.3s at 8 threads vs
  original TetWild 287.6s (3.4x self-speedup) - but **scaling stops at 8
  threads and then degrades**, attributed to frequent conflicts in
  tetrahedral edge operations. The authors flag this as a lesson for future
  concurrent mesh generation. This is a direct warning for our Phase-6
  parallel plan: vertex-mutex 2-ring locking saturates early on volume
  meshes; surface (tri) workloads scale to 32 threads, tet workloads do not.
- Scale validation on Thingi10k (serial, 15h budget): uniform remeshing
  mostly <10s per model, valence ~6 and target edge length reached almost
  everywhere; TetWild variant capped at 25 iterations - 2.5% of models did
  not finish, 3% retained rational coordinates, only 8 models ended with
  average AMIPS > 10 (optimal 3).
- Envelope-gated variants: SEC with envelope, 858k faces, 731s serial ->
  37.5s at 32 threads (20x); uniform remeshing with envelope, 484s serial ->
  29.1s at 32 threads (16x). The expensive user invariant parallelizes for
  free, which is the framework's best single result.

## Algorithms reproduced and fidelity

Five algorithms: (1) shortest edge collapse (Hoppe), (2) QSlim
(Garland-Heckbert), (3) isotropic remeshing (Botsch-Kobbelt), (4) harmonic
triangulations (Alexa 2019, both the reduced 3-2-swap-only and complete
versions), (5) a TetWild variant differing from Hu 2018/2019b by: triangle
insertion with rational coordinates replacing BSP partitioning, the Wang 2020
exact envelope replacing sampling, and a reduced swap set (2-3 face, 3-2 and
4-4 edge). Outputs are comparable to the references (matched valence/edge
length for remeshing; similar or better AMIPS histograms for tet meshing,
with the parallel-postponement caveat above). No line-count table is given,
but the printed listings show the per-algorithm code is tens of lines, and
the serial and parallel versions are stated to be almost identical. 5-6 swaps
and other exotic operations are not implemented. IDAS covers only simplicial
manifold meshes - no polygonal/hex support.

## Adoption verdict for AutoTessell

**Port the architecture pattern; do not depend on the library.**

- The pattern to port into our C++ kernels is exactly the paper's five
  components: (1) before/after hooks around every local operation with
  automatic topology+attribute rollback; (2) invariants as first-class
  predicates checked by the runtime on every modified element, never by
  operator code; (3) explicit per-operation attribute transfer rules; (4) a
  scheduler owning priority queue, re-enqueue policy, and stale-entry
  invalidation; (5) data-structure-agnostic navigation (tuple/switch) so the
  kernel data structure stays swappable. This validates our guarded
  transactional local-operator loop as the published state of the art, from
  the same NYU lineage as the vendored TetWild code.
- Reasons not to take the dependency: native-first policy; the 2022 library's
  serial overhead (2-8x vs hand-tuned on QSlim/harmonic) is a cost we would
  pay everywhere while our meshes are mid-sized; its parallelism is
  explicitly nondeterministic with no replay mechanism, which conflicts with
  our deterministic-commit ambition (see Omega_h note in batch2); and it
  covers tri/tet only, while we need the same transaction spine under hex and
  poly operators too.
- For Phase 6 (parallelism last): their evidence supports doing surface-mesh
  parallelism with optimistic ring locking (11-20x on 32 threads, biggest
  wins when invariants are expensive), but says vertex-mutex locking
  saturates at ~8 threads for tet edge operations. If we want determinism,
  their design shows what to avoid: postponement-on-conflict reorders the
  user's priority schedule and perturbs results. A deterministic alternative
  (coloring/partition-with-deferred-interfaces a la Loseille 2017, or
  Omega_h-style derived-copy commits) should be benchmarked against their
  simpler optimistic locks before we commit.
- Cheap immediate borrowings: the tuple-tagging queue-invalidation trick; the
  rule that the before-hook is the only place pre-operation state may be
  read (makes rollback total); and the envelope-as-invariant packaging of
  Wang 2020, which we already planned via `TRI-ENV-*` cards.

## High-value references from this paper

- Brisson (1989), *Representing Geometric Structures in d Dimensions*: the
  cell-tuple navigation abstraction IDAS is built on.
- Marot and Remacle (2020), recursive divide-and-conquer shared-memory
  remeshing: the interior-first/boundary-later alternative to optimistic
  locking, relevant to a deterministic Phase-6 design.
- Karras (2012), Morton-encoding parallel construction: the spatial
  partitioning used to keep thread conflicts rare.
- Gumhold, Borodin, Klein (2003), *Intersection Free Simplification*: the
  self-intersection invariant candidate for decimation.
- Wicke et al. (2010), *Dynamic Local Remeshing for Elastoplastic
  Simulation*: the downstream sim-coupled remeshing consumer the framework
  targets; shape of the API a simulation-facing AutoTessell remesher needs.
