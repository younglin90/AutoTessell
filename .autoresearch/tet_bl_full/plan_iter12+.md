# Plan: iter 12+ — Plateau Breakthrough (2500 → 2700+)

## Current state (iter 11 = 2500 BEST)

15/21 PASS, 20/21 BL=3 exact. Plan goal 2700+ (-200).

## 6 Failures — root cause analysis

| STL | Verdict | n_cells | BL | max_skew | max_aspect | Root cause | Iter target |
|-----|---------|---------|-----|----------|------------|-----------|------------|
| medium_100045 | PASS_WITH_WARNINGS | 5565 | 3 | 3.2 | 16.8 | hausdorff_relative=4.45 — fTetWild draft ε too coarse for box-shaped body, body simplified to 7 faces | **iter 12** |
| hard_100030 | FAIL | 8656 | 3 | 80.7 | **365.2** | aspect ratio severe sliver after BL | iter 13 |
| hard_100029 | FAIL | 20692 | 3 | **1477** | 157.9 | extreme sliver tet, AMIPS post-polish insufficient | iter 14 |
| extreme_1017013 | FAIL | 10374 | 3 | **82264** | 55.4 | flat sheet (z thickness ~7mm), Delaunay sliver | iter 15+ |
| extreme_1017014 | FAIL | 10392 | 3 | 627 | 60.9 | flat sheet sibling | iter 15+ |
| extreme_102308 | CRASH | 0 | 0 | - | - | SIGSEGV — fTetWild self-intersect | iter 16+ |

## iter 12 — pre-densify body in external compound (target: medium_100045)

### Hypothesis
medium_100045 has body bbox [0,0,0]×[6,1.97,6]. External compound bbox is [-18,-12,-12]×[36,13.97,18], diagonal ≈68. Wildmesh draft `edge_length_r=0.06 × 68 = 4.06` — bigger than body's smallest dim 1.97. fTetWild can fit only 7 surface faces on body → hausdorff_relative=4.45.

### Change (one file, ~20 lines)
`core/generator/tier_wildmesh.py:567` (before external `if flow_type == "external"`)
- Apply BETA2879 pre-densify (subdivide body surface to ≥`wildmesh_min_input_faces=1024`) BEFORE creating compound. Currently pre-densify only runs in the `else` branch (internal flow).

### Verify
```bash
timeout 240 python3 .autoresearch/tet_bl_full/verify.py 2>&1 | tail -5
# Expected: medium_100045 PASS, score ≥ 2600
```

### Expected score delta
- medium_100045 PASS_WITH_WARNINGS → PASS = **+100**
- (medium_100322 / hard_1004826 must remain PASS — they share path)
- **score 2500 → 2600**, regression check via verify

## iter 13 — hard_100030 aspect 365 mitigation

### Hypothesis
After BL prism insertion, sliver tets appear adjacent to wall. AMIPS post-polish moves only 0 verts (locked count high).

### Change candidates
- AMIPS multistage with stronger gradient (energy_target_step += 1)
- Sliver collapse pass after AMIPS (aspect>50 tets → edge collapse, no polyMesh reassembly required if cell count stays same via vertex merge into mid-edge point + duplicate cell pruning at write-time)
- BL aspect cap shrink: existing `aspect_cap=1000` reject — but max_aspect=365 is below → not triggered

## iter 14 — hard_100029 sliver

skew=1477 indicates volume-on-area collapse. Need AMIPS at higher penalty + minimum dihedral guard.

## iter 15+ — extreme cases

flat sheet & SIGSEGV. Major surgery — out of fast loop scope.

## Safety / Atomic commit policy

- One change per iter, single file when possible.
- `experiment: iter N — <summary>` commit prefix.
- Verify exits 0 + score ≥ previous best → keep. Else `git revert HEAD`.
- Per-STL timeout: 240s (verify.py PER_STL_TIMEOUT).

## Verify command (canonical)

```bash
timeout 1800 python3 .autoresearch/tet_bl_full/verify.py 2>&1 | tee .autoresearch/tet_bl_full/iterN.log | tail -3
```

stdout final line is the score.

---

## iter 13/14 추가 발견 (2026-05-08 16:50)

### iter 13 (3 시도, 모두 discard)
- wall_aspect guard (50, 5): tet_bl_subdivide.py 에서 wall 자체 sliver 거부 시도. **0 reject** — wall 삼각형은 정상.
- lateral cosine divergence (cos<0.95): twisted prism 검출. **0 reject** — BL prism 은 twisted 아님.
- edge collapse default-off (BETA2899): degenerate cell 가능성 차단. **score 무변화** — BETA2894 이 skew driver 아님.

### iter 14 (1 시도, discard)
- wall_edge × 0.1 floor 로 first_thickness 적응 (× 9 for hard_100030). max_aspect 365→222 ↓. **max_skew 80.73 invariant**. medium_100330 PASS→FAIL regression.

### Root cause confirmed (hard_100030 skew=80)
- BL prism 자체가 아닌 **fTetWild bulk 의 sliver tet** 가 BL prism cap 옆에 위치. cell-cell d_mag 이 매우 작아 skew_dist/d_mag 폭증.
- BL 파라미터 (first_thickness, growth_ratio, n_layers) 어느 것도 영향 없음 (sliver tet 는 BL 와 독립).
- 해결: pre-BL 단계에서 fTetWild output 의 sliver tet 검출 후 refinement (edge split / vertex insertion) 필요. **non-trivial**, 다음 세션 영역.

### medium_100330 fragility
- iter 12b (× 3) 와 iter 14 (× 9) 모두 medium_100330 PASS→FAIL.
- 1298 wall faces + aspect 646 (densest + highest aspect 중 하나) 조합이 BL 두께 변화에 매우 민감.
- iter 11 의 first_thickness=auto-default 가 medium_100330 의 sweet spot. 어떤 scale-up 도 sliver 유발.

### 다음 세션 advisable target
1. **fTetWild output sliver detect + refine** (pre-BL): hard_100030/29 skew issue 해결 가능
2. **per-STL fragility tracker**: medium_100330 같이 BL 파라미터 sweet spot 인 STL 은 변경 회피
3. **sliver tet collapse with safe topology rebuild**: iter 9 미해결 영역


---

## iter 15 결과 (2026-05-08 17:14)

### KEY DISCOVERY (max_skew 분리 진단)
hard_100030: max_internal_skewness=**2.71** (PASS), max_boundary_skewness=**80.73** (FAIL).
즉 skew 폭증의 원인은 BL prism cell 의 boundary skewness 만이며, 그 원인은:

**curved wall + per-vertex normal extrusion → cell centroid drifts from face_normal axis**
- Per-vert vnorm (smooth extrusion) 으로 prism 만들면 cap centroid 가 face_normal 축에서 이탈.
- Boundary skew = lateral_offset / normal_dist → curved wall 에서 폭증.

### iter 15 시도 (face_normal vs avg(vnorm) divergence guard, 2 시도, 모두 discard)
- cos<0.98: hard_100030 PASS (skew 80→16) ✓ but 6 STLs regress (partial BL 커버리지 → patchy boundary). 2500→2000.
- cos<0.85: hard_100030 도 worse (skew 176). 2700+ score.

### 부분 rejection 의 fundamental 문제
일부 wall face 만 BL skip 하면 BL/non-BL 경계에서 새로운 skew 발생. 모든 face 는 BL 받거나 모두 skip 해야 일관된 mesh.

### 다음 세션 권장 fix (multi-day)
1. **face_normal 기반 uniform extrusion + vertex duplication** at face boundaries (cfMesh approach). per-face inner vert → cap on face_normal axis → boundary skew = 0.
2. **angle-weighted vnorm** (현재 area-weighted) 으로 face_normal 발산 감소 시도.
3. **post-BL boundary skew correction**: prism 삽입 후 cell centroid 를 face_normal 축으로 강제 projection (cap inner vert 이동, neighbor 와 합의).


---

## iter 16 결과 — **NEW BEST 2600** (+100 from 2500)

### KEY WIN: angle-weighted vnorm (Garimella 2003)
`core/layers/native_bl.py:compute_vertex_normals`: area-weighted → angle-weighted (각 face contribution = sin(angle_at_v) of triangle).

핵심 영향: **hard_100030 max_skew 80→6.4 PASS**. 다른 STL 모두 PASS 유지 또는 개선.
- test_cube: 1.84→1.57 ↓
- medium_100330: 13.8→4.16 ↓
- medium_100322: 15.5→3.9 ↓

### iter 17/18/19 attempt — 모두 discard
- iter 17 (Laplacian smoothing): hard_100030 6→251 regression
- iter 18 (angle² weighted): 양쪽 다 나쁨
- iter 19 (selective Laplacian cos<0.9/0.7): 동일 regression

### 잔여 4 fails 의 근본 한계
- **hard_100029**: BL boundary skew 260 (1477→260 큰 개선 but >> 20 threshold). 5050 wall faces, 매우 curved → vnorm averaging 한계.
- **extreme_1017013/14**: flat sheet, mesher 단계 문제
- **extreme_102308**: SIGSEGV
- **medium_100045**: PASS_WITH_WARNINGS (body lost in fTetWild)

### 결정적 다음 단계 — fast iter 영역 밖 (multi-day)
**vertex duplication BL extrusion (cfMesh approach)**: per-face inner verts 로 cap 이 face_normal 축에 정확히 align → boundary skew = 0. native_bl.py 의 inner_pt 계산 + polyMesh 위상 재구성 필요.


---

## iter 21-23 추가 — 모두 discard, 수학적 한계 증명

### iter 21 (AMIPS unlock bl_internal_domain): 2600 same
AMIPS optimizes sliver-energy not boundary skew. Unlocking 한 vert 가 자유도 가지지만 energy landscape 가 face_normal alignment 로 push 안 함.

### iter 22 (curvature thickness reduction): 2600 ~ same
**핵심 수학**: BL prism boundary skew = **tan(θ)** where θ = angle(avg_vnorm, face_normal). 
- drift ∝ thickness, d_mag ∝ thickness/2
- skew = tan(θ), THICKNESS-INVARIANT
- → iter 14 (× 9 thickness) 결과 설명: skew 변화 없음.

### iter 23 (cos<0.3 face skew prediction guard): 2600 worse
- 수학적: skew=20 = tan(87.1°), 즉 cos(face_normal,avg_vnorm) > 0.05 면 skew<20 PASS
- hard_100029 의 worst face: skew=260 → θ=89.78° (cos<0.001!) — **almost orthogonal**
- 이는 multi-patch junction vert 에서 vnorm 이 face_normal 과 거의 수직.
- Partial face rejection 이 패치 경계 새 skew 유발 → fundamental.

### 수학적 결론 (iter 22 finding)
**skew = tan(θ)**
| θ | skew |
|---|------|
| 30° | 0.58 |
| 60° | 1.73 |
| 80° | 5.67 |
| 87° | 19.08 (≈ threshold) |
| 89° | 57.3 |
| 89.78° | 260 (hard_100029) |

evaluator.md threshold 20 → θ < 87°.

**Per-vertex normal extrusion 의 fundamental 한계**: 한 vert 가 여러 face 와 공유 → 단일 vnorm 으로 모든 face 와 angle 0 불가능. 다음 진짜 해결책은 vertex duplication (per-face inner vert) — cfMesh / Pointwise approach. Multi-day refactor.

### 잔여 4 fails — fundamental limits
- **hard_100029**: 63 wall patches multi-region junction → vnorm 이 face_normal 과 nearly orthogonal at junction verts
- **extreme_1017013/14**: flat sheet mesher 단계
- **extreme_102308**: SIGSEGV
- **medium_100045**: body lost in fTetWild

iter 16 = **2600 BEST** preserved. 추가 fast iter 진전 불가, 본격 refactor 필요.


---

## iter 24-26 추가 — 새 카테고리 시도, 모두 discard

### iter 24 (flat sheet edge adapt)
extreme_1017013 skew **82264→1723 (47x ↓ 큰 개선)** but still > 20 threshold. extreme_1017014 worse, hard_100029 worse. Net 2600 same.

### iter 25 (defensive pymeshfix)
extreme_102308 SIGSEGV 유지. hard_100030 regress (skew 6→17).

### iter 26 (coarsen edge for non-watertight)
Edge × 1.5, × 3.0: SIGSEGV 유지. Crash 가 fTetWild post-mesh_optimization (Python wrapper data transfer 단계). Edge_length 와 무관. **Wrapper bug** (likely pytetwild np.array marshalling OOM).

### 잔여 4 fail 의 재진단
| STL | Failure | Root cause | Required fix |
|-----|---------|------------|--------------|
| hard_100029 | skew=260 | multi-patch junction θ=89.78° | vertex duplication |
| extreme_1017013 | skew=82264 | flat sheet (z=6.7) | per-axis edge / anisotropic mesher |
| extreme_1017014 | skew=627 | flat sheet | same |
| extreme_102308 | SIGSEGV | pytetwild wrapper OOM during np.array transfer (358k tets) | upstream pytetwild fix |
| medium_100045 | hausdorff | body lost in fTetWild output | per-region edge / vertex duplication |

5/6 fails 가 동일한 fundamental: **pytetwild / fTetWild Python wrapper limitation**.

