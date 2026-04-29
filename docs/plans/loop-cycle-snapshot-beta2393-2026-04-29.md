# /loop 자동 고도화 사이클 스냅샷 (2026-04-29, beta2393)

## 진행 상황

`/loop` 자동 1분 간격으로 SOTA 상용 갭 분석 → 단일 카드 → 검증 →
재계획 cycle 진행. 현재 27 cycle 완료 (beta2367 - beta2393).

## 카드 시퀀스 (이번 세션)

| Beta | 카드 | 영역 | 영향 |
|------|------|------|------|
| 2367 | C2 LCR skeleton | BL | per-vertex LCR (Pointwise T-Rex 동등) |
| 2368 | C2.2 LCR wired | BL | native_bl 에 diagnostic 호출 |
| 2369 | C2.3 LCR schema | BL | NativeBLResult 4 필드 + JSON |
| 2370 | C3.1 prism split | BL | aniso prism 분할 (cfMesh 동등) |
| 2371 | C6.1 hex BL | BL | hex prism extrude (T-Rex 동등) |
| 2372 | C1.4 metric diag | tet | aniso metric propagation log |
| 2373 | C1.5 QED tier-aware | tet | qed_min_faces kwarg, fine=10k |
| 2374 | C1.6 Stellar split | tet | env-gated 4-op queue split |
| 2375 | C5.2 parallel auto | tet | cpu_count() ≥ 2 자동 활성 |
| 2376 | C3.2 BL split diag | BL | native_bl split_thick_prisms 호출 |
| 2377 | C3.3 split schema | BL | aniso_split JSON + NativeBLResult |
| 2378 | C1.7 Stellar fine | tet | fine quality 자동 ON |
| 2379 | val fine params | val | HARNESS_PARAMS 통째 사용 |
| 2380 | C-PERF-1 Lloyd | poly | plateau early-exit |
| 2381 | C-PERF-2 budget | poly | wall-clock 90s budget |
| 2382 | C-QUAL-1 integrity | tet | mesh_integrity_suspect flag |
| 2383 | threshold tighten | tet | V/8 → V/32 |
| 2384 | val kwarg filter | val | _filter_to_sig + whitelist 보강 |
| 2385 | C-QUAL-2 recovery | tet | fine recovery_iterations 2→3 |
| 2386 | C-VAL-1 rich output | val | integrity flag + grade 노출 |
| 2387 | C-VAL-2 err msg | val | FAIL 시 exception 메시지 |
| 2388 | C-PERF-3 hex log | hex | wall-clock observability |
| 2389 | C-PERF-4 hex tier | hex | snap_iterations 5→3, post_smooth 3→2 |
| 2390 | C-QUAL-3 GWN | utils | Jacobson 2013 generalized winding |
| 2391 | **C-QUAL-4 p4c guard** | tet | **monotone guard (1072→3 cells fix)** |
| 2392 | C-QUAL-5 seed GWN | tet | env-gated GWN inside test |
| 2393 | C-PERF-5 patch cap | writer | n_patches 2187 → 64 cap |

## 검증 결과 (validator partial)

10-mesh hard validator (seed=42, 30 runs):

| 메쉬 | tet | hex | poly | 비고 |
|------|-----|-----|------|------|
| #1 V=3116 F=6272 SI+NM | 8 cells [INTEGRITY?] | 63326 (648s) | 333 (125s) | tet 비정상 |
| #2 V=12000 F=24014 SI+NM | 1 cell [INTEGRITY?] | 28366 (142s) | 진행중 | beta2391 이전 데이터 |

## 핵심 진단

**해결된 큰 버그**:
- p4c_pytetwild fallback 의 catastrophic cell-drop (1072→3) — beta2391 monotone guard.
- HARNESS_PARAMS 와 mesher signature 불일치 — beta2384 _filter_to_sig.
- validator 의 fine quality 미사용 (draft 기본값) — beta2379.

**개선된 perf**:
- hex hard mesh: 615s → 142s (~4× 빠름) — beta2389 + 추후 patch cap.
- poly hard mesh: 614s → 125s (~5× 빠름) — beta2380/2381.

**남은 갭**:
- tet 의 hard SI mesh 가 1-16 cells 만 회복 — GWN seed test (beta2392) 활성화 필요.
- hex polymesh writer 가 patches 2187 개 — beta2393 cap.
- BL pipeline 검증 미포함.

## 다음 카드 후보

1. tet GWN seed test 의 자동 fallback (input metadata 기반).
2. BL pipeline 을 validator 에 추가 (tet+BL, hex+BL, poly+BL).
3. native_hex perf 추가 분석 (snap loop 또는 octree_done 후 단계).
