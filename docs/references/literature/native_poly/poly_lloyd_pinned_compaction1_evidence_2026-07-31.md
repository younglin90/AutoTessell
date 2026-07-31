# POLY-LLOYD-PINNED-COMPACTION-1 Evidence

Date: 2026-07-31

Status: `DEFER / prerequisite`; bounded correctness repair retained on the
research branch, but not eligible for `master` integration. Target-cell work
remains deferred.

## Failure isolation

The immutable Poly L3 shard at commit `bbe7ae3b` ran
`tests/test_native_poly_solid_volume.py` for 240.209 seconds.  Its first four
cube assertions passed and the process group was cleaned, but the cylinder
fixture never completed.

The retained pytest directory provides stage timing without another heavy
run.  Cube generation started at `07:11:14.82`, wrote its polyMesh at
`07:11:47.14`, and wrote its quality report at `07:11:50.21`.  The cylinder
started at `07:11:50.47`; its generator failed after 47.78 seconds with:

```text
boolean index did not match indexed array along axis 0; size of axis is 16560
but size of corresponding boolean axis is 18810
```

The orchestrator then generated a 1.95 MB last-resort reconstructed surface at
`07:12:47.04` and spent the rest of the module budget retrying that enlarged
surface.  The two test fixtures are already module-scoped and each geometry is
generated exactly once.  Changing fixture scope or replacing the canonical
pipeline with precomputed polyMesh data would hide the production defect.

## Root cause and mechanism

`_lloyd_3d_iteration` builds a feature-seed `pinned` mask aligned with the
initial seed rows.  Its inside filter can remove seeds after an iteration, but
the old code compacted only `seeds_inside`.  On the next iteration the
16560-row seed array was indexed by the stale 18810-row mask.  Even without an
exception, failing to compact original positions with the same transaction
could associate a surviving pin with the wrong source row.

The repair keeps three arrays row-aligned: current seeds, current pin flags,
and current original positions.  Both the plateau filter and normal filter
compact all three with the same mask.  Remaining pinned coordinates are
restored from their own original row.  Removed rows cannot reappear.

Primary metric: uncaught mask-shape exceptions on the deterministic two-step
compaction witness, repeated three times.  Acceptance is `3/3 -> 0/3` with
bit-exact surviving pins and three-run output identity.

## Acceptance boundary

- L0 compacts eight rows to six between two Lloyd iterations, with both pinned
  and unpinned rows removed.
- Remaining pinned coordinates are bit-exact; unpinned rows match the frozen
  displacement oracle; removed rows never reappear.
- The no-filter path is exactly unchanged.
- A wrong-length pin mask retains the prior unpinned behavior.
- One bounded cylinder node may run for at most 180 seconds with one OpenMP,
  BLAS, and MKL thread.  The mask mismatch, last-resort reconstruction, and
  child-process leak must all remain zero.
- If the cylinder still cannot emit a valid mesh, only an explicit
  artifact-free refusal is acceptable.  A timeout or truthful refusal does not
  promote the release gate.

Rollback conditions: pinned-coordinate drift, row misalignment, removed-row
resurrection, no-filter output drift, nondeterminism, surface/topology/
provenance or validity regression, continued mask mismatch, or any
`third_party/` change.

This is a Python orchestration correctness repair, not a measured performance
hotspot.  No C++23 port is claimed by this card.  Mesh quality thresholds,
routing defaults, target-cell behavior, and boundary-layer behavior are
unchanged.

## Verification result

- Deterministic compaction witness: `3 passed in 2.31s`.
- Production and test modules: `py_compile` passed.
- `git diff --check`: passed.
- Bounded cylinder node: timed out after 180 seconds.
- Original `16560` versus `18810` mask mismatch: zero recurrences.
- `reconstructed_surface.stl`: absent.
- Child process leak after timeout: absent.

The cylinder advanced beyond the original exception, then entered Poly
boundary-layer prism extrusion even though the selected strategy reported
boundary layers disabled. It added 100 prisms, reported 7074 negative-volume
cells, raised an internal `list index out of range`, and remained active until
the timeout. This is a separate fallback-invariant defect. Because the old
explicit failure at about 48 seconds became a 180-second timeout on the default
runtime path, this repair must not be merged alone. It is a prerequisite for
`POLY-BL0-FALLBACK-INVARIANT-1`; both cards require bounded validation before
integration.
