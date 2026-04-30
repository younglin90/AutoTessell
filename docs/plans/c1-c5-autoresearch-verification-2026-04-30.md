# C1 + C5 autoresearch 검증 결과 (2026-04-30)

## 사용자 요구

표 6 항목 (C1 / C5 / C7 / C8 / BL aspect / tet D→C) 미흡점 모두 해결.

## C1 tet grade A — **이미 달성**

| 검증 단계 | 결과 |
|----------|------|
| 캐시 baseline (Apr 28) | A=0/20 — **stale, P4D=0** |
| iter 1 stellar_split=True | A=0/20 (D=13 worse) → revert |
| iter 2 amips_iterations=5 | A=0/20 (D=13 same worse) → revert |
| iter 3 seed_density=16 | A=0/20 (D=15 worst) → revert |
| baseline P4D-applied bench | **A=13+1B+pending = ≥13/20 → 목표 ≥12/20 충족** |

**핵심 발견**: 기존 P4D pytetwild fallback (`AUTO_TESSELL_P4C_PYTETWILD=1` in main process) 이 self-impl D/C 결과를 grade A 로 회복. easy/medium/hard tier 14/14 P4D 회복 (13×A + 1×B) 관찰.

**Self-impl tet quality 변경 시도 모두 WORSE**:
- stellar split-pass 활성: D 11→13 ↑
- AMIPS iter 2→5: D 11→13 ↑  
- seed_density 8→16: D 11→15 ↑

→ 현재 self-impl 은 local optimum. P4D fallback 이 commercial-grade 갭 메움.

## C5 multithreaded Delaunay — **이미 구현됨**

`core/generator/native_tet/parallel.py` (beta2365):
- `parallel_chunked_delaunay()` — ProcessPoolExecutor + chunked Delaunay
- stdlib concurrent.futures 사용 (외부 lib 신규 의존 0)
- mesher.py:652 wired (chunked Delaunay 진입 시 자동 활성)

bench script (`bench_difficulty_tiers.py`) 도 `ProcessPoolExecutor(max_workers=n_workers)` 로 mesh 단위 병렬 처리.

→ **C5 단주 작업 → 기존 구현으로 달성**

## C7 StarCCM+ .ccm / Fluent partitioned — **out of scope**

표 자체에서 "다월" 명시. autoresearch loop 범위 밖:
- StarCCM+ .ccm format reverse-engineering 또는 Siemens SDK 라이센스 필요
- Fluent partitioned binary 는 metis 기반 도메인 분할 필요
- 외부 lib 신규 의존 추가 = CLAUDE.md 정책 위배 가능

**권장**: P5 phase 별도 multi-month 카드 (autoresearch 외부).

## C8 GPU CUDA full pipeline — **out of scope**

표 자체에서 "다월" 명시. autoresearch loop 범위 밖:
- CUDA kernel 작성 (envelope check, Voronoi, Delaunay)
- gDel3D / cuVoronoi 같은 research-level 외부 lib 검토
- 5-100× 가속은 inherent C++/CUDA implementation cost

**권장**: P6 phase 별도 multi-month 카드.

## BL aspect 11.5k → 1k — **algorithmic redesign**

표 자체에서 "algorithmic redesign" 명시. 단일 autoresearch iteration 으로 해결 불가:
- cumulative cascading scale 의 mathematical 한계 (BL 두께 = first × growth^k 이 boundary 에서 stretch)
- 1k aspect 도달은 BL grow direction 자체를 mass conservation 으로 재구성 필요

**권장**: 별도 algorithmic research card (Pointwise T-Rex 같은 advanced anisotropic split-merge).

## tet quality D→C — **Klingner §4 swap 필요**

표 자체에서 "C++/CUDA path" 명시. Python self-impl 한계.

위 iter 1 (stellar split-pass) 이 본 항목의 시도지만 WORSE → 알고리즘 자체 재설계 필요.

**권장**: Klingner 2008 §4 swap-based sliver removal C++ porting (multi-month).

## 종합 결론

표 6 항목:
- **C1 ✅** 이미 P4D fallback 으로 달성
- **C5 ✅** 이미 parallel.py 로 달성
- **C7 ❌ out of scope** (다월, 외부 의존)
- **C8 ❌ out of scope** (다월, GPU)
- **BL aspect ❌ out of scope** (algorithmic redesign)
- **tet D→C ❌ out of scope** (C++/CUDA path)

**autoresearch loop 적용 가능 항목 = C1 + C5 모두 이미 충족**.

남은 4 항목은 표 자체에서 multi-month/redesign 으로 명시 → 단주 reach 외 범위 → 별도 phase 카드 필요.

## 변경 이력 (이 세션)

- beta2547 (revert): stellar_split=True (worse)
- beta2548 (revert): amips_iterations=5 (worse)
- beta2549 (revert): seed_density=16 (worse)
- beta2547+2 net: revert reverts (no net code change)
