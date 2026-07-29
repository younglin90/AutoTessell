# AutoTessell C++-first migration and workspace cleanup

Date: 2026-07-29

## Decisions

- Keep Python for CLI, Pydantic contracts, orchestration, structured logging, and tests.
- Implement new performance-sensitive geometry, topology, quality, and search kernels
  in C++23. Expose NumPy-compatible APIs through pybind11.
- Port one measured hot path per card. Keep the Python implementation as the reference
  until native/Python parity, input-surface preservation, determinism, and the
  L0 -> L1 -> L2 -> L3 verification ladder pass.
- Do not translate the repository mechanically. A wholesale rewrite would erase
  validated behavior and make regression attribution impossible.
- Third-party Python libraries stay behind adapters until their required operation has
  a licensed C++ API or an in-tree native equivalent. The product contract must not
  depend on an optional Python fallback.

## Binding contract

- Input: contiguous typed NumPy views; reject incompatible shape/dtype explicitly.
- Output: owned arrays or documented lifetime-safe views; no hidden Python callbacks in
  hot loops.
- Release the GIL only around code that does not touch Python objects.
- Convert native failures to typed Python exceptions at the binding boundary.
- Preserve stable ordering and deterministic tie-breaking across platforms.
- Every topology-changing kernel receives or computes current boundary IDs and verifies
  boundary face keys, area, orientation, and surface hash before acceptance.
- Exact predicates compile without FMA contraction where their arithmetic proof requires
  it.

## Finite migration order

1. **M0 workspace hygiene — complete.** Recover dangling branch refs, remove clean
   worktree checkouts, remove only reproducible caches/build output.
2. **M1 salvage existing native kernels.** Extract `native_metrics`,
   `native_polymesh`, and `native_snap` from the old `cpp-hotpath` WIP as three separate
   cards. First card: poly volume/topology census because prior measurement recorded
   about 18.19 s Python versus 0.75 s native. Reproduce that result on current master;
   old staged code is evidence, not merge-ready code.
3. **M2 native_tet hot paths.** Port boundary-face census/invariant checks, candidate
   influence-set construction, exact predicate batches, and accepted local-operation
   application. Keep recovery policy/orchestration in Python until parity is complete.
4. **M3 native_tri/native_quad operators.** Port split/collapse/flip/smooth transaction
   kernels after native_tet shared primitives stabilize.
5. **M4 engine consolidation.** Remove Python reference kernels only after all callers
   use native implementations and L3 regression plus benchmark budgets pass.

Parallel execution and SIMD begin only after correctness gates close.

## Workspace cleanup performed

- Recovered 24 missing branch refs from each worktree's last valid reflog commit.
- Removed one stale `/tmp` worktree metadata entry.
- Removed 27 clean worktree checkouts; all branch refs and commits remain recoverable.
- Preserved root and 12 dirty worktrees. No dirty code was discarded.
- Removed 1,223 cache directories and 21 `.pyc` files.
- Removed reproducible CMake/build/installer output and the ignored 2.0 GB
  `octree.vtk` artifact. Removed worktree checkouts occupied about 7.4 GB before removal;
  removed build/artifact targets occupied about 3.7 GB.
- Preserved `.venv` because Python wrappers/tests still require it. Preserved papers,
  reference source trees, benchmark evidence, and every tracked/untracked WIP file.

## Remaining dirty worktrees

- root `AutoTessell`: large mixed WIP; preserve and split by card.
- `AutoTessell-autoresearch-bl`
- `AutoTessell-boolmerge4`
- `AutoTessell-cpp-hotpath`: 65 staged files, 13,812 added lines; salvage only by card.
- `AutoTessell-hex`, `AutoTessell-hex-phase-next`
- `AutoTessell-poly`, `AutoTessell-poly-next`
- `AutoTessell-tet-chen-l0`, `AutoTessell-tet-core-cert-clean`,
  `AutoTessell-tet-handoff`, `AutoTessell-tet-v4-target-edge-h2`
- `AutoTessell-tri`

These require card-level review or commit before checkout removal. Directory age or name
alone is not evidence that code is disposable.
