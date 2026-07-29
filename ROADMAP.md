# AutoTessell Roadmap

AutoTessell is a meshing platform: surface input → native volume engines
(tet/hex/poly) → export. Spec set 2026-07-18.

## Governing invariants

1. **(Spec "최중요사항")** The pre-meshing surface must not be altered
   by volume meshing and must be preserved exactly in the final mesh. Enforced
   today for native_tet by permanent gates (surface-area identity, zero
   off-surface boundary, cylinder wall dev 0.000). Outranks every other goal.
2. GUI never runs heavy compute in-process. Meshing runs in a server/worker
   process so the UI remains responsive and jobs can be isolated.

## 2026-07-26 campaign ledger (current truth)

이 표가 아래의 오래된 역사적 측정 서술보다 우선하는 현재 작업 원장이다.

| 엔진 | 현재 닫힌 범위 | 남은 최우선 카드 | 상태 |
|---|---|---|---|
| native_tet | naca 표면 보존 연쇄 수정, dual_torus CVT 정합성 수정, BSP 후보 비악화 가드, metric/GAP caller import fix, fixed-condition BSP recovery 측정 종료 | FLOW-3 naive ladder는 private 2건 수용 후 worst-Q 불변/rollback, 32 bad-tet·5 rung 60.3s로 예산 초과했으나 round-local incidence cache로 `1.84s`까지 단축. TET-WDEL-2 GSM-ratio proxy는 FSL 실제 wave-1과 8.2% 일치로 measured/falsified. 기본 P4-C pytetwild fallback은 반복 실행마다 다른 점/셀 배열을 내는 결정론 장애이며, `random_device→42` 한 줄 재빌드와 TBB OFF 재빌드도 fresh-process 결과를 고정하지 못해 measured insufficient/falsified. 다음은 self-native 결정론 lane과 영구 gate 비교이며, FLOW-3은 worst-Q 불변으로 default-OFF, WDEL-3는 그 뒤 재개한다. LAZY-1/SHAPE-3(a)는 60/61 private-copy 개선, LAZY-2 bounded 128-edge는 0승인; current `_phase_bc_skip` route와 stellar WIP mismatch는 별도 | fixed-fine OFF/ON 최종 `.80518/.46509/.68116/6` 동일, ON `151.75s` vs OFF `31.40s`. FSL boundary `4588→4588`, mean q `.151544→.152208`, min q 불변. FLOW-3 candidate boundary/input exact, whole rollback; WDEL-2 proxy 폐기; P4-C OFF native-only cylinder repeat byte-identical |
| native_hex | Phase 0 census/ScoreCHE/β-margin, wall-fit·writer·transition 진단, sub-quad winding·mixed-level coverage 수정, wall-fit zero-area rollback guard | surface-constrained local Pareto candidate 문헌/진단; 전역 wall-fit 승격 보류 | gear raw/written `4920/4920`, writer drop `0`, boundary ID delta `0+0`; cylinder/sphere fidelity는 개선되나 skew `0.699→9.486`, `0.930→8.779`; gear skew/warpage 악화, bracket skew `0.326→409.288`; negative volume `0/0/0`; suite `97 passed, 9 skipped` |
| native_poly | FV 지표, AR 방향성 gate, entity-classified dual, point/star validity, fixed-primal plane-membership 최적화, report-only FV MMS | upstream dual face/coplanar-cap 유효성·결정론을 먼저 닫은 뒤 solver-consistent 비직교 face-flux 재측정; exact ConvexHull 우선/QJ fallback으로 fixed-native invalid가 cube `2/30`, cylinder `70/440`, sphere `0/0`으로 개선됐지만 transactional face repair는 미종료; well-centered primal `20/40`, `8/212`, `196/1913`; relocation/hybrid/Ep/face-warpage 후보 모두 충분하지 않음; interior valence<7은 cube `1`, cylinder `1`, sphere `7`; topology map의 초기 `6/46/489`는 boundary-edge 진단 버그로 폐기, corrected incomplete internal links `0/0/0` | Phase 1 topology/dual 완료; sphere dual fixed-primal 4.9–5.3 s/반복·invalid 0·동일 digest. 합성 25% 섭동 MMS는 보정 전 차수 .7658/.6690, 진단 보정 후 2.0094/2.1250이나 native sphere에서는 L2 .559→1707.868로 악화되어 생산 승격 보류; cube/cylinder FV prerequisite blocked; topology repair 미개설, dual face-aware candidate measured insufficient, Phase 2 repair dormant |
| native_tri | Shewchuk FMA 계약, operator-loop split/collapse/flip/smooth MVP, Frey/Dunyach scalar sizing, SPD metric + tangent/BL handoff, guarded operator corpus, opt-in local-guard equivalence lane | `TRI-OPERATOR-PERF-1` exact-result-preserving 성능 후보 재설계 및 thin/feature quality 분리; L2 경로는 baseline으로만 유지 | 7형상 direct round에서 finite·positive-area 유지, cube/sphere/cylinder/thin disk/needle/multi-scale sphere manifold+watertight, wing은 open 유지; local guard는 5형상 byte-identical이나 dual-torus flip이 300 s 초과, 기본 OFF |

공통 순서: 측정 → 한 카드/한 메커니즘 구현 → canonical/permanent gate →
결정론 반복 → 문서 갱신. 병렬/MPI는 correctness gate가 닫힌 마지막 단계다.

### 2026-07-27 문헌 후속 조사 — 개선 정체 구간의 분리

이번 라운드의 native_tet 중간 영구 게이트 묶음은 184초에서 출력 없이
timeout되어, 이를 회귀로 단정하지 않고 별도 성능 카드로 유지한다. 현재
hard matrix의 미개선 축은 서로 다른 문제로 분리됐다: naca/cylinder는
경계 고정형 local quality/cavity, thin disk/needle은 thickness-aware
anisotropic generation, dual/perforated는 CDT recovery stage complexity,
native_poly는 concave/star-shaped dual topology, native_hex는
surface-fidelity와 quality의 Pareto 및 transition/feature provenance,
native_tri는 feature/envelope contract다.

읽을 수 있는 문헌과 후속 방법 카드는
`docs/references/literature/improvement_blockers_followup_2026-07-27.md`에
기록했다. 첫 다음 카드는 `TET-CDT-PROFILE1` 또는
`TET-THIN-SECTION-1` report-only 계측이다. `POLY-CONCAVE-SPLIT1`과
`HEX-TRANSITION-TEMPLATE1`은 구조적 provenance/validity 측정 뒤에만 연다.
global threshold 완화, surface movement, unguarded smoothing, ECR/sheet
전역 dispatch는 현재 근거로 승인하지 않는다.

### 2026-07-27 native_hex continuation ledger

`HEX-TRANS-2`를 새 fine/pre-BL 출력에서 재검증했다. volume-ratio >=1.5를
transition proxy로 삼아, bad boundary face의 직접 transition-owner 비율은
cylinder `344/344`, sphere `918/960`, gear `68/68`이었다. 전체 boundary의
직접 transition 비율은 각각 `74.2%`, `94.3%`, `88.5%`라 enrichment는
`1.348x`, `1.014x`, `1.130x`이다. 세 형상의 bad face는 geometry-only
feature proxy상 모두 `smooth/defaultWall`이며, 현재 writer에는 octree
level/patch provenance가 없다. 따라서 transition-only solver는 열지 않고
`HEX-PROV-RETENTION-1`을 report-only로 실행했다. cylinder/sphere는
raw→written topology가 보존됐지만 provenance 입력은 없었고, gear는 writer
직전 이미 zero-thickness hex가 존재해 `HEX-GEAR-DEGEN-DROP-1`로 분리한다.

`HEX-GEAR-DEGEN-DROP-1`에서 optional `native_polymesh` 부재 상태의 Python
fallback을 재현했다. 탈락 셀은 `329,335,4013,4187,4589,4595`이고, 세 쌍의
공유 fatal face key가 모두 centered rank 1/area 0이었다. 발생 단계는
`_wall_fit_snap`으로 확정됐고, 영향 셀 face-area guard를 추가해 후보를
reject/backtrack했다. gear raw/written은 `4920/4920`, writer drop `0`,
boundary ID delta `0+0`으로 복구됐다. 후속 `HEX-WALLFIT-PARETO-1`은
cylinder/sphere의 area·wall_dev 개선과 skew 악화를, gear/bracket의
형상별 악화를 재확인했다. 전역 wall-fit 승격은 보류하고 local
surface-constrained 문헌 후보로 분리한다.

`HEX-OCT-MIXED-LEVEL-COVERAGE-1`을 구현·검증했다. 원인은 부분
`covered` 블록의 미처리 셀 고립과 coarse-face 이웃 level의 단일 인덱스
샘플링이었다. mixed target block finest 승격, 부분 블록 안전 fallback, 인접
face slab 전체 검사로 수정했다. 합성 transition 테스트는 `5 passed`, native_hex
전체 회귀는 `118 passed`다.

대표 2,000-cell cylinder는 이전 mixed-level 상태
`1383 cells / boundary skew 125.761 / area deviation 87.09%`에서
`1655 cells / boundary skew 3.20865134 / area deviation 0.263700907% /
negative volume 0 / writer drop 0 / boundary face-set equal=True`로 회복됐다.
영구 boundary-skew `3.0` 기준은 넘었으므로 완전 PASS로 기록하지 않으며,
잔여 85 bad-face 및 large-budget 품질 원인은 `HEX-OCT-SCALE-QUALITY-1`로
분리한다. mixed-level은 기본 경로로 승격하지 않는다.

추가 계측(`HEX-OCT-SCALE-QUALITY-1`)에서 coverage fix 이후 builder bad-face는
0건이었지만 `_wall_fit_snap` 후 80건(전체 pipeline 85건)이 생겼고,
transition owner/vertex-adjacent는 모두 0건이었다. wall-fit ON은
`3.20865134` skew와 `0.263700907%` area deviation, OFF는 `0.974373881`
skew지만 `15.3787224%` area deviation이었다. 후보 `496`건 중 `376`건이
local quality 회귀를 동반하고 strict 비회귀는 `120`건뿐이었다. 표면 fidelity
이득을 잃는 단순 quality rollback은 거부하고, 문헌 근거가 있는
surface-constrained Pareto repair를 별도 카드로 남긴다.

이번 라운드에는 `HEX-WALLFIT-PARETO-1` 문헌 카드를 추가했다. HexOpt의
surface-constrained optimization, octree transition preconditioning,
transition quality control, boundary-sheet/feature provenance 후보를
P0/P1로 분류했지만, 아직 전문 미확인 문헌이 남아 있어 production repair는
보류한다. 다음 측정은 cylinder/sphere/gear/bracket의 후보별
`Δskew/Δwarpage/Δarea/Δwall_dev/Δsigned-volume` Pareto frontier다. 기존
surface face-key·area·negative-volume·determinism·skew gate는 완화하지 않는다.

---

## Track A — Meshing                                          **~72%**

### A-1 Surface input                                        **100%**
Complete (2026-07-19): STL/OBJ/PLY/OFF/3MF/STEP/IGES/BREP readers; global
integrity checks; L1/L2/L3 repair; revisioned source preservation.
- **S1 Multi-file upload + assembly/patch naming:** stable user-facing source
  names survive temporary storage paths; `assembly_manifest.json` records source
  order and operation; output patch order and zero-face absorbed sources remain
  deterministic.
- **S2 Boolean merge:** union/intersection/difference for 2+ inputs use per-input
  winding-number volume classification in native tet and native hex. Native poly
  uses the validated hex-backed polyhedral path. All families preserve source
  provenance and fail closed instead of silently changing CSG semantics.
- **S3 Defect localization + selected auto-fix:** deterministic face/edge/vertex
  locations cover degenerate and duplicate faces, open loops, non-manifold edges,
  inconsistent winding, and self-intersection. The web UI focuses exact faces,
  offers only supported repairs, creates immutable revisions, rejects stale
  edits with HTTP 409, and preserves the original upload.
- **Acceptance:** 177 A-1 tests pass after the patch-name regression fix; live
  browser verification confirms the diagnostics panel, revision display, 3D
  face overlay path, and zero console errors.

### A-2 Volume engines                                        ~65%
- **native_tet — Phase 0b isolation unresolved (measured 2026-07-24)**:
  clean `eb846f43` measured `naca0012` at skew `60.399`, area-ratio
  `1.000000`, vol-ratio `1.003539`, and `degen=10` (FAIL); the canonical
  dual-torus driver timed out at 120 s (a diagnostic direct run completed in
  126.9 s with skew `2.210e6`). Cell B matched this clean result because
  `eb846f43` predates the 13 rescue env-gates, so its eight exported flags were
  inert. The prior `~85%` / `~60.3` rescue-contaminated narrative is suspended;
  no valid current-WIP native-only percentage is asserted until the gate patch
  is applied to the clean tree and the isolation is rerun.
- **native_tet Phase 0i split commit (`8a226df8`, 2026-07-24):** CVT3D locks
  the complete current boundary ID set in both passes, and Klingner local
  candidates require exact boundary face-set and area preservation; dual CVT
  boundary movement was zero. Naca's stale-caller explanation is superseded:
  the corrected `358/358` lock set plus `1,068` protected edges still gives
  collapse `712 -> 974`; root cause is open as
  `TET-COLLAPSE-BULK-ROOTCAUSE-1`. Dual BSP insertion/recovery is open as
  `TET-BSP-INSERT-ROOTCAUSE-1`. Phase 1 remains blocked; 61 wedges remain
  strict-xfail.
- **boundary-layer engine 100% (validated scope, 2026-07-19)**: requested
  3/3 layers survive all hard12 cases; dedicated topology, quality, layer-state,
  persistence, and subdivision regression suite is 247/247 green.
- Historical native_tet closure record: solid gates green (cube P4C=0, PASS, skew 1.81);
  cylinder fidelity 0.000, skew 4160→44.9→**40.8** (2026-07-18, see below).
  **Coverage-collapse cluster closed (3/3)**: `high_genus_dual_torus.stl`
  (BETA2832 — `_final_validate`'s unconditional keep-largest-component was
  discarding a whole disjoint torus body; replaced with a relative guard,
  area/vol-ratio 0.56/0.47→1.01/1.01), `many_small_features_perforated_plate.stl`
  (BETA2833 — the same destructive clamp lived one layer upstream in L1
  pymeshfix's `remove_smallest_components`; fixed with per-component repair +
  an aggregate guard so many-small-bodies inputs can't be filtered away
  piecemeal even when no single body trips the 5%-of-max threshold),
  `sharp_features_micro_ridge.stl` (SHARPRIDGE1 — L2's cotan Laplacian
  smoothing has no free-boundary pin and was collapsing a thin open ridge
  to a point; added the same monotone area/Hausdorff revert-guard pattern).
  All three verified via the same canonical bench script, all three fixes
  are pure relative guards that no-op on healthy single-body input.
  **Sphere-class TIMEOUT cluster closed**: `core/utils/aabb.py`'s BVH leaf
  routine was called once per query point (660k scalar calls, 71% of
  profiled wall) instead of batched; vectorizing it dropped cumtime
  62.4s→2.8s and took `sphere.stl`/`sphere_watertight.stl` from 143s
  TIMEOUT to 29s PASS. The same investigation caught a **pre-existing
  correctness bug** in `TriangleBVH.build()` (a local argsort rank written
  as if it were a global triangle id, corrupting `tri_order` below the
  root — backs every envelope/hausdorff/cdt_recovery/signed_distance query
  project-wide) — fixed, ~80 BVH-adjacent tests unchanged.
  **Flat-all-surface-sliver sequence closed (FSL1→FSL4)** on dual_torus's
  residual quality FAIL: detector (read-only) → guarded 2-3 flip
  (infrastructure proven safe, but 0/9 eligible slivers were actually the
  FAIL driver — correctly a no-op) → known-limit gates (61 unflippable
  wedges are structurally coplanar-flat, cure needs the same
  near-wall-insertion class of fix as cylinder skew, out of scope; volume
  tiling locked at 0.99 so it can never silently regress, cure target
  pinned as xfail(strict) so a future fix trips a loud alarm instead of
  going unnoticed). **CYLSKEW1** landed the first card of that
  near-wall-insertion sequence (Garimella offset-ring seeding, default OFF,
  seeding-stage-only hook, proven not to leak onto the boundary) — as an
  unplanned bonus, even this unrefined seeding measured skew 44.9→40.8
  before any of the filtering/guarding follow-up cards.
  Sequence continued (CYLSKEW2-4): the originally-planned wall-adjacent
  filter was measured and falsified twice (cylinder has no pure side-wall
  vertex to filter for since it only has 2 z-rings; sphere's regression at
  N=500 is a holistic seed-density effect, not a per-vertex class problem),
  redirecting the sequence to a monotone best-of-two selector instead:
  scale-invariant guards (CYLSKEW2), a pure decision function verified
  against 3 measured cases including sphere's default-ON-breaking regression
  (CYLSKEW3), and wiring via a cheap pre-optimization Delaunay proxy since
  full best-of-two doubles bench time past budget (CYLSKEW4, default path
  unchanged, proxy/final correlation still open — the one case checked
  disagreed with the known-good full-pipeline result, flagged for CYLSKEW5).
  **Coverage-collapse-adjacent quality cluster** (naca0012, was FAIL from
  degen 17 + skew 58.83): THINSLIVER1 closed most of the degenerate axis
  (22->11 in a controlled config, correctness win, permanent regression
  lock + xfail(strict) for the remaining higher-valence victims). THINSLIVER2
  set out to fix the skew axis but, on independent reconfirmation, measured
  zero effect on the *current* baseline (which had already dropped from
  82.44 to ~60.3 via the cards above stacking) — the 123-line mechanism was
  discarded rather than kept as unexercised complexity; what's real (the
  ~60.3 state) is now a regression-locked permanent gate. A real skew fix
  needs fresh diagnosis against that baseline, not the stale one.
  Remaining: 12-STL hard-geometry bench sweep beyond the shapes closed so
  far, full 4-op schedule, CYLSKEW5 (proxy/final correlation, default-ON).
- **native_hex ~45%**: solid gates green on the cube (surface 6.000/void
  0.000/vol 1.000/degen 0, skew 3.6e-16). Curved-wall **staircase** fixed on
  both quality levels (3-card sequence, all permanent gates now):
  (1) per-vertex wall-fit snap (envelope-projected, accepted only on
  strictly-decreasing surface distance + positive-volume/orientation guard
  on every incident cell) closed cylinder standard wall_dev_max
  0.0466→0.0032; (2) envelope generalized to per-vertex local sizing
  (fTetWild-style) — measured harmless but not the fine blocker
  (n_reject_envelope=0 before/after); (3) root cause was the guard's
  all-or-nothing structure: full projection got reverted entirely on any
  face flip even though 39/39 rejected vertices had a safe partial move
  (binary-search fraction t*, min 0.706). Backtracking to the largest t*
  that still passes the *same* unmodified guard (no relaxation) took fine
  wall_dev_max 0.0353→0.008 (gate <0.02); negative_volumes=0 throughout.
  Follow-up: post-snap boundary skew (4.64) was decomposed to its root
  (wall-fit snap collapses the boundary cell's wall-normal thickness |nd|);
  freezing surface vertices and relaxing only the free interior vertices of
  flagged sliver cells restored it to 2.84 (new permanent gate ≤3.0) with a
  bonus fix — fine's pre-existing (undetected) negative_volumes=8 dropped to
  0 too, now permanently gated on both quality levels. Next: further skew
  reduction, then extend the solid-preservation methodology to poly.
  **2026-07-24 clarification**: the 2.84 boundary-skew figure is confirmed
  (exact reproduction: 2.840553147) for `standard` quality specifically.
  `fine` quality's boundary skew was never separately measured/gated by this
  fix — a fresh measurement puts it at 3.208651 (14 disconnected high-skew
  components, not a coherent sheet). This is a newly-measured open number,
  not a regression; see native_hex_literature_integrated_development_plan
  Phase 1 "2026-07-24 wave 0 result".
- **native_poly ~55%** (revalidated 2026-07-19, S1→S5): canonical
  smoke (`scripts/smoke_native_poly.py`) + all **4 solid invariants now
  permanent gates** on cube.stl, matching tet and hex's status. S1 measured
  a blind verdict=PASS hiding void 7.588 and volume 1.177x. S2's working
  hypothesis (boundary open-wall) was disproved by measurement — the real
  cause was tet->dual's per-cell ConvexHull triangulating each non-planar
  interior dual interface differently, so adjacent cells' shared face never
  vertex-matched and leaked as void on both sides; fixed with a topological
  path (each interior tet edge's ordered centroid ring emitted directly as
  the shared face) — void 7.588→2.435. S3 found two more boundary-only bugs
  in the same file (cap faces over-classified as boundary; boundary-edge
  seams between adjacent boundary cells had no separating face) — void
  →**0.000 exactly**. S4 root-caused the residual volume overfill (1.077x)
  with a controlled experiment: feeding dual.py's *unmodified* code a
  well-formed Kuhn tetrahedralization gives Sigma|vol|=1.0000 exactly, so
  the dual construction itself was never the bug — native_tet's interior
  Steiner points make sliver tets whose non-convex dual cells the
  pyramid-volume measure overestimates. Laplacian-smoothing only the
  interior tet vertices (boundary fixed, so surface/void stay
  structurally unchanged) pulled volume to 1.026 and even improved skew
  (0.457→0.422). Next (POLY-S5): generalize past the cube (sphere/cylinder),
  then quality. S5 now passes native-poly E2E on sphere and cylinder at
  N=2,000; cylinder measures 1,781 cells, zero negative volumes, skew 2.17,
  non-ortho 16.66, and 0.154% surface-area deviation. The cylinder quality
  gate is permanent; remaining work is broader topology/patch coverage.
- **native_poly Phase 0 FV census (2026-07-24):** report-only face planarity,
  normal spread, Juretić ψ, h, Circle Ratio, sphericity, and Uniformity Factor
  metrics are now emitted by `NativeMeshChecker`; no quality gate was changed.
- **native_poly directional AR gate (2026-07-24):** high aspect-ratio cells are
  accepted by the evaluator only when conservative evidence confirms principal-
  axis alignment, neighbor stretch-direction consistency, and surface
  tangent/normal alignment. Missing or weak evidence keeps the legacy scalar
  AR gate active, so isotropic poor cells remain rejected. Producer/schema
  wiring for these four diagnostics remains the next step before real BL cases
  can use the relaxation.
- **native_hex Phase 0 census (2026-07-24):** report-only cell-type/volume
  fractions, ScoreCHE, hex-cluster, and β-margin diagnostics are emitted from
  written topology; pairing remains absent and no all-hex claim is made.
- **native_hex transition realization/quality audit (2026-07-26):** an opt-in
  mixed-level lane now emits a synthetic transition cell, but real cylinder /
  sphere / gear runs expose writer drops, boundary-set changes, high transition
  skew, and five builder-side negative emitted signed volumes on gear. The lane
  remains default-OFF; next is writer-boundary and face-winding contract
  isolation, not transition repair.
- **native_hex writer-boundary audit (2026-07-26):** predicted generic-writer
  degenerate-face drops matched actual drops exactly (cylinder 18/18, gear 8/8),
  and predicted exposed internal faces matched added boundary keys (60/60 and
  23/23). The writer is exonerated; upstream snap/wall-fit stage bisection is
  next, with mixed-level realization still default-OFF.
- **native_hex wall-fit face-area guard (2026-07-26):** an opt-in guard prevents
  cylinder/gear writer drops (18→0, 8→0) and restores boundary-set equality, but
  transition skew/warpage and gear's five builder-side negative signed volumes
  remain. Keep default-OFF; it is an invariant aid, not a quality repair.
- **native_hex HEX-TRANS-2 (2026-07-26):** cross-tabulation at canonical
  boundary skew `>=2.0` falsified transition-local concentration on the current
  mixed-level fine pre-BL outputs. Transition-owner overlap was cylinder
  `36/550`, sphere `0/960`, gear `10/135`; the broader transition-vertex proxy
  was `168/550`, `0/960`, `22/135`. The next card is a report-only wall-fit
  candidate-quality transaction, not a transition-only repair. Both mixed-level
  realization and face-area guard remain default-OFF.
- **native_hex wall-fit candidate quality (2026-07-26):** opt-in candidate
  snapshots observed local quality regression across cylinder/sphere/gear:
  applied-regression counts `128/128`, `104/128`, and `186/271` at the small
  diagnostic setting. Boundary face keys stayed equal, but surface relocation
  changed boundary area on most candidates. This is a generic wall-fit issue;
  no transition-only repair or quality rollback is enabled. Next is denominator
  and signed-orientation contract closure before any relative transaction.
- **native_hex wall-fit surface-distance trade-off (2026-07-26):** candidate
  distance improvements were cylinder `128/128`, sphere `128/128`, gear
  `253/271`; quality regressions overlapped `128`, `104`, and `186`. A
  quality-only rollback would block the entire measured cylinder fit, so the
  next card compares final wall deviation against local quality delta at
  representative mesh sizes. No Pareto transaction is enabled.
- **native_hex wall-fit surface fidelity (2026-07-26):** stage mean surface
  distance improved cylinder `0.027915→0.014200`, sphere `0.078905→0.046371`,
  gear `0.026542→0.001380`; gear p95 improved `0.096807→0.005295`. Quality
  regression and surface benefit coexist, so no quality-only rollback or new
  absolute threshold is authorized. Next is connection to existing final
  wall_dev/skew gates at representative sizes.
- Common: N-targeting (tet+netgen done; hex/poly open), BL growth-ratio GUI
  done, per-patch BL toggles blocked on S1, MPI absent, threading partial.
  Parallelism deliberately LAST (invariant: correctness gates must be able to
  catch parallel nondeterminism first — the dead-zone lesson).

### A-3 Export                                                ~90%
10 formats live. Remaining: per-format fixtures; patch-name round-trip after
S1; CGNS mesh and patch/BC semantics validation.

## Sequencing (near-term)

```
now      native_hex HEX-WALLFIT-FINAL-GATE-CROSS1 report-only connection
         · A: CYLSKEW2-4 · POLY-S4 boundary-cell overfill
next     native_hex HEX-OCT-TRANSITION-TEMPLATE-1 (mixed-level root cause)
         · S1 multi-file+patch naming  ←— unblocks per-patch BL
         · A: 12-STL hard-geometry bench sweep beyond the closed cluster
then     S2 boolean merge · S3 defect localization UI
last     parallel/MPI after correctness and determinism gates
```

## Method (keep)

Measure before planning (guessing refuted 4+ times) · one canonical
measurement script per geometry · primary-source diffs against vendored
references · relative before/after guards, never absolute · surface
preservation as a non-negotiable floor · new engines enter through the
strategy registry with declared capabilities, disabled when incompatible.

## Long-term product architecture — 3D surface / 3D volume

AutoTessell will expose two first-class, visually and operationally distinct
3D meshing products. A surface mesh has two-dimensional topology but is
embedded in 3D coordinates. They share import, geometry diagnosis, feature detection,
patch semantics, sizing fields, provenance, quality reporting, and job
execution.  They do not share output contracts: a surface operation must never
claim a volume mesh, while a volume operation must preserve its selected
surface contract exactly.

### Surface mesh (3D)

- **native_tri:** deterministic triangular surface meshing/remeshing for CFD
  and structural-analysis pre-processing.
- **native_quad_dom:** quad-dominant surface meshing with explicit triangle
  remainder reporting; it must not label an arbitrary triangle mesh as
  quad-dominant.
- Geometry-heavy kernels (surface sizing, feature classification, planar
  padding/extrusion, topology construction, quality checks) are C++ native
  extensions by default. Python owns orchestration, schemas, UI/API wiring,
  and file-format integration only; any development fallback is explicit and
  never presented as the optimized production path.
- Both engines detect and preserve wall/feature **edges**.  Users can select
  wall-edge groups and create a 2D boundary-layer band along them, with layer
  count, first height, growth ratio, collision/gap checks, feature protection,
  and per-edge provenance.
- Surface hard gates: manifold/watertight contract appropriate to input,
  no degenerate or flipped faces, feature-edge preservation, geometry drift
  bound, boundary-band evidence, deterministic output, and explicit rejection
  with original geometry preserved when a gate fails.

### Volume mesh (3D)

- **native_tet:** all-tetrahedral volume meshing.
- **native_hex_dom:** hex-dominant volume meshing; actual cell-type coverage
  is reported rather than inferred from engine name.
- **native_polyhed:** native polyhedral volume meshing with protected feature
  seeds and native-poly provenance.
- Each engine detects and preserves wall **faces**.  Users can select wall-face
  patches and create a 3D boundary-layer volume there, with layer count, first
  height, growth ratio, collision/gap checks, transition topology, and
  per-face/layer provenance.
- Volume hard gates: surface fidelity/provenance, non-manifold and duplicate
  topology zero, negative volumes zero, requested wall-face/BL evidence,
  quality limits, explicit fallback disclosure, and deterministic or
  conservative repeated-run quality evidence.

### Shared UX and delivery sequence

1. UI has a top-level **Surface mesh (3D)** / **Volume mesh (3D)** choice
   before engine selection.  Output panel, viewer mode, quality cards, export
   formats, and terminology switch with this choice.
2. A single wall-selection model maps edges only to surface BL and faces only
   to volume BL.  Invalid cross-dimensional actions are disabled rather than
   silently converted.
3. Engine capability registry declares dimensionality, native cell/face types,
   wall entity type, BL support, feature preservation, required input
   topology, and supported exports.  UI and API use this registry; they do not
   duplicate engine-name conditionals.
4. Add independent deterministic quality corpora and autoresearch loops for
   native_tri, native_quad_dom, native_tet, native_hex_dom, native_polyhed,
   and native_face_remesh.  Each uses isolated worktrees, real artifact-based
   metrics, repeated-run determinism gates, and no threshold/coverage
   weakening.
5. AI remains advisory: it may predict sizing, feature, wall, or quality
   fields, but deterministic native meshing and the same hard acceptance gates
   own final acceptance.  The application never represents an AI hint as a
   validated mesh result.

### 2026-07-27 native_tet performance continuation

`TET-CDT-SCALE-PERF-1`에서 dual_torus fine native-tet의 CDT outer rounds가
약 102/107/112초로 반복되고, 480초 내 end-to-end 완료되지 않았다. 고정
메시지에서 병목은 `edge_flip_recovery`의 missing-edge × 전체-tet 선형검색으로
확정됐다. `AUTO_TESSELL_TET_EDGE_FLIP_INDEX=1` opt-in 인덱스는 결과 배열과
통계를 byte-identical하게 유지하면서 targeted flip 9.48배, one-cycle CDT
4.00배를 측정했다. 기본값은 fine replay·영구 게이트·결정론 확인 전까지 OFF다.

다음 순서: (1) `TET-BSP-RECOVERY-CORRECTNESS-1`에서 surface-face/positive-
orientation 보존 원인을 먼저 닫고, (2) indexed lane fine bounded replay와
permanent gate·strict-xfail을 재검증하며, (3) 이상 없을 때만 기본값 전환을
검토한다. 그 후 재현 가능한 native_poly repair 카드와 native_tri anisotropic
metric four-fixture measurement으로 이동한다. batch BSP + 500-point 조합은 `cdt_face_ratio=0.452`,
`n_val_flipped=4621`, `n_val_degen=6`으로 default-on 후보에서 제외했다.

현재 코드 재검증(`target_cells=600`, P4C off, indexed order, guard on)에서도
OFF/ON 최종 통계가 각각 `12219/2855`, `12616/2903` cells/points와 기존
constraint·plane·quality 수치를 재현했다. wall은 `26.53→34.15 s`였고,
full-fine `480 s` BSP replay는 여전히 timeout이므로 lane은 기본 OFF다.

2026-07-27 BSP correctness guard: B-W 후보는 누락 면 수가 줄고 물리적
boundary 면적이 보존될 때만 채택하며, 그렇지 않으면 후보 전체를 복원한다.
full re-Delaunay fallback도 같은 기준을 사용한다. scalar BSP 기본 경로와
batch opt-in 분리는 유지하고, fine end-to-end 결과가 나오기 전에는 카드 종료나
기본값 전환을 하지 않는다.

고정 상태 재측정에서는 scalar BSP `60.1438 s`, batch BSP `1.4736 s`,
Bowyer–Watson `13.3494 s`였지만, batch+B-W 후보는 missing face를
`1032→1076`으로 악화시켜 correctness guard에서 복원된다. 따라서 B-W
adjacency 재구축 최적화는 별도 성능 카드로 보류하고, 먼저 실제로 missing
face를 줄이는 deterministic candidate를 확보해야 한다.

추가 고정 상태 진단에서 indexed targeted 2-3 edge flip 200회는 missing edge
`604→452`, missing face `1032→779`를 만들었지만 non-positive/degenerate
count가 `8964→9071`로 증가했지만 퇴화체 수는 `131→131`이고 후단
orientation normalization이 부호를 복구한다. 따라서 다음 correctness
카드는 `TET-CDT-EDGE-FACE-MONOTONE-1` 후보 단위 local-degeneracy/boundary
guard로 구현되었다. `AUTO_TESSELL_TET_EDGE_FLIP_GUARD=1`에서 valid flip은
통과하고 coplanar flip은 rollback되며, 고정 상태 200회에서 boundary
key/area와 `1032→779` face 개선이 유지된다. sorted candidate order를
고정한 재실행에서는 edge가 `604→455`, guard reject 1건이었고 두 실행의
`17869×4` tetra 배열이 byte-identical했다. boundary는 `1320→1320`, 면적은
`103.399255187455→103.399255187455`였다. 음수 orientation만으로는 거부하지
않고 후단 deterministic normalization에 맡긴다. fine replay·영구 게이트·
전체 파이프라인 반복 실행 byte identity를 확인하기 전까지는 indexed lane과
guard 모두 기본 OFF다.

후속 fixed-state 감사에서 후보 edge 순서가 raw/sorted/reversed일 때
`152/452`, `149/455`, `144/460`으로 달라지는 결정론 결함을 확인했다.
`edge_flip_recovery`가 `(min(u,v), max(u,v))` canonical key를 정렬한 뒤
bounded loop를 수행하도록 수정했고, 세 입력 순서 모두 `149/455`, guard
reject 1건, 동일한 `17869×4` tet 배열로 수렴했다. full pipeline fine
결정론과 기본값 승격은 여전히 보류한다. 최신 집중 게이트는
`19 passed, 2 xfailed`다.

### native_tet BETA2832 multi-body coverage

전처리기의 상대 component filter가 dual-torus의 두 body를 모두 보존하는
것을 재검증했다(`num_components=2`, `n_kept=2`, `n_dropped=0`). 결과는
`area_ratio=1.0094878`, `vol_ratio=1.0097687`, `cells=11071`, `degen=0`,
`neg_vol=0`, `129.1 s`로 커버리지 gate를 통과했다. cube solid smoke와
solid-volume/dual-torus 회귀는 `7 passed, 1 xfailed`였다. 남은
`max_skew=2.21e6`와 낮은 CDT 회복률은 BETA2834 품질/recovery 카드로
분리하며, 이번 커버리지 카드의 성공으로 간주하지 않는다.

BETA2834 direct opt-in 측정에서는 edge recovery가 CDT ratio를 `.881→.925`,
face ratio를 `.707→.800`, mean quality를 `.1482→.1524`로 개선했지만 plane
coverage는 `.897→.880`, 시간은 `6.73→14.24 s`가 되었다. production harness는
현재 `enable_edge_recovery=False`라 env index만으로는 연결되지 않는다. 따라서
surface-conformity/area guard 없는 edge recovery는 기본 승격하지 않는다.

추가 stage snapshot에서 direct edge lane의 midpoint/B-W 50점 삽입은 missing
edge를 `682→682`로 줄이지 못했지만, flip 포함 전체 lane의 boundary face와
면적은 각각 `1352→1352`, `103.399255187455→103.399255187455`로 보존됐다.
따라서 plane coverage 저하는 boundary key/area 파괴가 아니며, 후속
recovery/BSP/quality 상호작용 카드로 이동한다.

### 2026-07-27 native_tet result contract and boundary continuation

최종 반환 배열·카운트·on-disk `polyMesh`를 동일한 final mesh로 동기화했다.
Naca stage audit에서 NN1 bulk collapse `696→984`, 구 4-4 ring ordering
`984→1008`, VVV8 boundary-Laplacian area drift를 각각 확인했고, candidate
collapse guard, cycle-validated 4-4 guard, VVV8 boundary keys/area guard를
적용했다. 현재 naca thin-sliver는 `2 passed, 1 strict xfailed`, boundary
`696`, internal prewrite skew `60.399`이다. 전체 hard-12와 permanent gate
재검증 전까지는 미커밋 WIP으로 유지한다.
## 2026-07-27 native_tet hard-geometry continuation

- Final-result synchronization plus boundary-safe collapse/flip/stellar/VVV8
  guards are active in the current WIP and the naca boundary lane is green.
- Draft/P4C-off target-2000 matrix: 7/13 PASS-ish. Cube, cylinder, sphere,
  watertight sphere, boxes, and micro-spike sphere pass with zero degenerates.
- Naca: area `1.000`, volume `1.001`, degen `0`, max skew `34.80`; still a
  general-quality failure, not a surface-preservation failure.
- Dual torus and perforated plate hit the 120 s worker timeout. Thin disk and
  micro-ridge have independent geometry/input failures. No gate was relaxed.
- Runtime-contract suite is now `6/6`, focused native-tet set is `19 passed, 1
  strict xfailed`, and W3 best-of rejects candidates below
  `ceil(0.30*target_cells)`; no permanent threshold was relaxed.
- Current target-2000 matrix is `6/13` PASS under the P4C/pytetwild-off protocol:
  naca remains a quality failure (`skew 34.80`) despite exact-looking
  surface/volume and zero degenerates; cylinder also fails quality; thin disk,
  needle, and micro-ridge remain geometry/input failures; dual-torus and
  perforated plate remain 120-second timeouts.
- Next: split native-tet work into quality, geometry/input, and timeout cards;
  preserve the current gates, then re-run the permanent suite per file rather
  than allowing the monolithic legacy collection to mask the failing case.
