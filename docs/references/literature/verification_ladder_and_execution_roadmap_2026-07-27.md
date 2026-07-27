# AutoTessell native engines — staged verification and execution roadmap

Date: 2026-07-27

This document turns the permanent rule in
`.claude/rules/verification-ladder.md` into the next execution sequence. It
does not relax any permanent gate or discard prior hard-fixture evidence.
Existing hard results are reclassified by level and retained as evidence.

## 1. Reclassification of current blockers

| Engine | Existing evidence | Correct level | Interpretation |
| --- | --- | --- | --- |
| native_tri | sphere collapse 240/240 sampled drift; strict support 0/240 | L1 diagnostic | topology guards are insufficient; single-face support is conservative, not the final epsilon-envelope gate |
| native_tri | cylinder flip 128 accepted, 64 sampled-drift violations, 0 strict single-face support | L1 diagnostic | split coplanar/patch-union candidates from truly drifting candidates before production gating |
| native_tet | thin disk 94 missing faces/79 edges; Chen closure components up to 10 tets | L2 targeted hard | valid recovery target, but too complex to be the first template implementation |
| native_poly | cube/sphere k-means cuts fail exact parent-volume reconstruction | L1/L2 diagnostic | plane selection is not the blocker; oriented face-loop/cap reconstruction is missing |
| native_hex | thin disk/needle sparse-leaf estimate returns zero leaves | L2 targeted hard | centroid occupancy aliases thin solids; first prove occupancy on an L0 crossing fixture |

The native_tri evidence ledger currently has one presentation inconsistency:
the metric-flip table says 128 drift false accepts while the executable result,
test, and prose say 64/128. The table must be corrected in the next tri docs
card; this is a documentation correction, not a changed measurement.

## 2. Round A — L0 mechanism foundations

### A1. TRI-ENVELOPE-L0

Build three local two-triangle fixtures: coplanar patch, gently folded patch,
and feature-edge patch. Measure flip/collapse candidate triangles against:

1. single-source-face support;
2. source-patch-union coverage;
3. an explicit epsilon-envelope.

Acceptance: the coplanar operation passes patch-union coverage; the folded and
feature cases either satisfy the declared epsilon or reject transactionally;
all repeats are identical. No global sphere/cylinder result is used until this
distinction is regression-locked.

### A2. POLY-ORIENTED-CUT-L0

Cut one analytic convex polyhedron by a plane. Reconstruct both oriented
face-loops and the cap with opposite orientation.

Acceptance: two closed children, positive signed volume, child-volume sum
equal to parent within `1e-12`, exact owner/patch accounting, and deterministic
face ordering. This precedes any cube/sphere k-means sweep.

### A3. HEX-SPARSE-OCCUPANCY-L0

Create one coarse AABB crossed by a thin triangle/slab whose centroid is
outside the solid. Compare centroid occupancy with triangle-AABB/surface
intersection occupancy.

Acceptance: the crossing cell is retained and refined; an empty separated
cell is rejected; 2:1 and owner-incidence checks remain deterministic. No full
thin-disk octree is built before this passes.

### A4. TET-CHEN-CASE1-L0

Construct a hand-checkable tetrahedron/source-face intersection matching one
Chen case-1 template, followed by one adjacent conformity fixture for the S/Z
choice.

Acceptance: explicit child tet list, exact positive orientation, parent-volume
conservation, identical external cavity boundary, recovered constraint count
strictly reduced, and rollback on the negative fixture. No thin-disk mutation
is attempted at L0.

## 3. Round B — L1 canonical geometry

1. **native_tri:** run the L0 envelope classifier on cube/cylinder/sphere;
   enable only geometrically certified candidate classes behind a default-OFF
   flag. Reclassify the cylinder 128 flip candidates into patch-valid versus
   true drift.
2. **native_poly:** apply exact oriented cutting to selected cube cells first;
   require closed children, star validity, volume conservation, unchanged
   external boundary/patches, and no writer loss.
3. **native_hex:** build the sparse tree for cube/sphere/cylinder using the L0
   occupancy predicate; compare cell budget to dense construction and run 2:1,
   all-cell Jacobian, wall deviation, and byte-repeat gates.
4. **native_tet:** run the bounded Chen case-1 transaction on a simple convex
   canonical fixture containing a manufactured missing constraint; require
   exact pre-meshing boundary identity.

Each engine remains default OFF until its L1 before/after baseline and
permanent tests pass.

## 4. Round C — L2 targeted hard geometry

1. **native_tet:** thin disk first, expanding case 1 -> case 2 -> full 1--4
   closure only when the prior template passes. Needle is a separate contact/
   degeneracy card because it had zero strict Chen face penetration.
2. **native_hex:** thin disk and needle occupancy/refinement, with nonzero leaf
   coverage, no surface aliasing, 2:1 conformity, and bounded memory. Gear and
   bracket remain post-snap provenance/quality cases, not occupancy cases.
3. **native_poly:** sphere and the non-manifold fan only after exact convex
   cutting passes; separate concave split from untangling rather than forcing
   one mechanism to solve both.
4. **native_tri:** curved sphere/cylinder plus a feature-edge fixture under the
   declared error tier; exact single-face support remains diagnostic while the
   epsilon-envelope and feature provenance decide acceptance.

At L2, failure is recorded as target not solved, expected rejection, or new
regression. Only the third category invalidates an earlier safe implementation.

## 5. Round D — L3 full regression

For each engine, run permanent tests and the declared campaign corpus once the
card's L2 target is measured. Produce one row per shape with route, cell/face
count, surface/topology/volume-quality metrics, runtime, determinism, and one
of the five L3 classifications from the permanent rule.

No parallelization card opens until all correctness cards being promoted have
reached `L3_REGRESSION_PASS`.

## 6. Immediate execution order

The next four cards are deliberately small and independent:

1. `TRI-ENVELOPE-L0` — fixes the current over-strict single-face-versus-patch
   ambiguity and corrects the 64/128 ledger row.
2. `POLY-ORIENTED-CUT-L0` — establishes the missing closed-child primitive.
3. `HEX-SPARSE-OCCUPANCY-L0` — establishes a thin-feature-safe refinement seed.
4. `TET-CHEN-CASE1-L0` — establishes one exact recovery template before the
   thin-disk cluster.

After these four L0 cards, advance in the same engine order through L1. Do not
skip directly to hard-12 or treat an L2 torture fixture as the first proof of a
new mechanism.
