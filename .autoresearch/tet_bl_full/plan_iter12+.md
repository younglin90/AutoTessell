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
