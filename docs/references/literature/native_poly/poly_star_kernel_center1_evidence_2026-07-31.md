# POLY-STAR-KERNEL-CENTER1 Evidence

Date: 2026-07-31

Base: `65add70d05207ffa1ea4b5b26ba858db37a04a6e`

Scope: star-validity witness selection only.  No mesh point, face, owner,
neighbour, boundary, tolerance, routing, target-cell, source-geometry, or
`vendor/dependencies/` change.

## Hypothesis and fixed acceptance

The arithmetic mean of a cell's vertices is only one possible star-kernel
witness.  Rejecting a polyhedron solely because that point violates a signed
face-edge-region subtet inequality creates false negatives when another point
lies in the intersection of all oriented half-spaces.

Primary metric on the deterministic sphere `seed_density=10` primal:

- primal digest: `edb4ea5e162b2334e8f17d0267e5cf1851169f34f89bd54048f1187f6264b73c`
- baseline: 698 points, 1,895 tets; two invalid dual cells and 14 invalid
  subtets; no output because the write remains transactional
- acceptance: zero invalid dual cells/subtets and a successful write, without
  changing the generated dual mesh candidate
- rollback: any tolerance relaxation, previously valid output-byte change,
  invalid fixture success/artifact, native/Python classification mismatch, or
  more than 10% valid-fast-path runtime regression

The search is deterministic and bounded to eight sequential projection
sweeps.  It starts from the arithmetic mean, moves only the local validation
witness into violated half-spaces, and then reevaluates every original
signed-subtet inequality at the unchanged `1e-12` tolerance.  The witness is
never written to the mesh.  Arithmetic-fast-path cells perform no projection.
Failure to obtain a finite witness within the cap retains fail-closed behavior.

## Independent feasibility diagnosis

The final seed-10 dual topology was captured before the transactional refusal
for diagnosis only.  With the existing tolerance included in every half-space:

- cell 653: 114 constraints, arithmetic violations 7, LP maximum common margin
  `9.030808594103325e-05`; projection converged in one sweep with maximum
  violation `-5.907342215220879e-13`
- cell 668: 168 constraints, arithmetic violations 7, LP maximum common margin
  `8.567649639274383e-05`; projection converged in one sweep with maximum
  violation `-5.907342757321965e-13`

The residual-invalid 15-point/40-tet cube was checked independently before its
assertions changed.  Four previously reported cells have genuine feasible
witnesses, while cell 6 does not:

- cells 0, 1, and 4: LP common margin `4.15443681306867e-03` or greater;
  projection converged within eight sweeps
- cell 11: LP common margin `3.2567461984459624e-03`; projection converged
  within eight sweeps
- cell 6: LP maximum common margin `-1.4694459771696627e-03`; projection did not
  converge, with nine original inequalities still violated

Therefore its diagnostic changes from 5/25 to the more accurate 1/9, but the
result remains `success=false` and all five `polyMesh` artifacts remain absent.
This is not a weakened fixture or threshold.

## Result

Three independent native sphere dual runs on the frozen primal each returned:

- success: true
- cells / points / faces: `698 / 5737 / 7072`
- invalid star cells / subtets: `0 / 0`
- elapsed dual generation: `2.2434`, `2.2536`, `2.2589` seconds
- deterministic output: true

All five output files were byte-identical across the three runs:

- `points`: `2e3b1e019bef087c64339de7936e78ab8484267bbab041d84ffa02ce69ff2e31`
- `faces`: `3050040d48e9a144c5de712df6d5b86dbf808c1443f3ff220713d22f992689c5`
- `owner`: `af6ef1e577e70d98e1d8879635518f56b4fdefa43647e7f6c595ec32949b1348`
- `neighbour`: `7445996b56e79b95e9e3d0988524ddebd925fec2cb8cee191b7a7af6405c8ee9`
- `boundary`: `664e998bab2128870add6f3de60761c89a1336343f1faa118461d7af0d617812`

The Python oracle independently returned the same sphere classification and
dimensions (`698 / 5737 / 7072`, `0 / 0`) in 6.6902 seconds.

On a 20,000-cell valid tetrahedron census, seven-run native medians were:

- base arithmetic validator: `0.005811221` seconds
- new arithmetic fast path: `0.005642231` seconds
- change: `-2.91%`; no regression and within the preregistered `+10%` bound

## Research and license boundary

- Sorgente, Biasotti, Manzini, and Spagnuolo, *Polyhedral mesh quality
  indicator for the Virtual Element Method* (2022), DOI
  `10.1016/j.camwa.2022.03.042`: a non-empty cell/face kernel is the
  non-compensable star-shapedness condition.
- Sorgente, Biasotti, and Spagnuolo, *Polyhedron Kernel Computation Using a
  Geometric Approach* (2022), arXiv `2202.06625`, *Computers & Graphics* 105,
  94-104: a polyhedron kernel is an intersection of oriented half-spaces and
  linear programming is the standard algebraic feasibility approach.
- Nehring-Wirxel, Kern, Trettner, and Kobbelt, *Exact and Efficient Mesh-Kernel
  Generation* (2025), DOI `10.1111/cgf.70187`: kernel existence is an oriented
  half-space feasibility problem; exact predicates are the robust long-term
  direction.
- `TommasoSorgente/polyhedron_kernel` is AGPL-3.0.  CGAL algorithms are
  package-dependent GPL/LGPL.  Both are research references only.

The projection and final-recheck implementation is independently authored.
No external code, generated artifact, dependency, or `vendor/dependencies/` file was
copied or modified.  This preserves the future MIT native-core boundary.

## Verification and remaining blockers

Fresh isolated `native_polymesh` built with GCC 13.3.0, C++23, Release,
`-Wall -Wextra -Wpedantic -Werror`.

Focused native/Python parity, residual invalid fail-closed behavior, frozen
classified-bipyramid output/provenance hashes, malformed connectivity, convex
and non-manifold regressions pass: `32 passed, 4 sphere tests deselected in
2.94s`.  Ruff, Black, and `git diff --check` pass.  Strict focused mypy reports
the 17 pre-existing diagnostics in `dual.py` and no diagnostic on the new
projection block or focused test.

The complete sphere `NativeMeshChecker` test remained CPU-active beyond both
90- and 120-second bounds after dual generation had succeeded; the combined
direct+harness command likewise timed out at 180 seconds.  Those full-checker
and harness outcomes remain unverified, not passed.  The two seed-8 sphere
tests fail earlier in native Tet source-topology validation and never enter the
Poly lane; they remain Tet-lane blockers.
