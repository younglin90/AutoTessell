# /loop 자동 고도화 사이클 — 3번째 스냅샷 (2026-04-29, beta2425)

## 진행 상황

`/loop` 1분 간격 자동 SOTA-gap 분석 → 카드 → 검증. **59 카드** 완료
(beta2367 - beta2425). 이전 스냅샷 (beta2409) 의 43 카드 이후 **16 추가**.

## 새 카드 (beta2410-2425, 이번 batch)

### GUI parity (12 cards)
| Beta | 카드 | 영향 |
|------|------|------|
| 2410 | history schema integrity flag | tet/poly/hex 의 catastrophic 추출 |
| 2411 | history dialog Integrity 컬럼 | UI 시각적 경고 ⚠/✓ + tooltip |
| 2412 | PDF report Integrity 합격 기준 | 상용 툴 mesh diagnostic 동등 |
| 2413 | schema → pipeline propagation | TierAttempt + ExecutionSummary |
| 2414 | NativeBLPhase2Stats 7 필드 추가 | LCR + aniso_split 통계 |
| 2415 | history bl_n_prism / lcr / aniso_split | 3 신규 필드 |
| 2416 | history dialog BL prism 컬럼 | Pointwise T-Rex parity |
| 2417 | CSV export BL stats | 3 컬럼 추가 |
| 2418 | CLI --seed-gwn / --stellar-split / --poly-budget-s | 3 신규 flag |
| 2419 | GUI 3 신규 체크박스 | env-toggle 노출 |
| 2420 | GUI 체크박스 layout fix | 표시 안 되던 buged |
| 2421 | GUI 체크박스 회귀 테스트 | 1 신규 test |
| 2422 | 파이프라인 완료 시 integrity 경고 로그 | 사용자 즉시 알림 |

### BL fix batch (3 cards)
| Beta | 카드 | 영향 |
|------|------|------|
| 2423 | bbox-relative first_thickness 자동 scaling | 1mm bbox vs 100mm bbox 모두 작동 |
| 2424 | **wall_face_indices stale guard** | **list index error 회피 (큰 bug)** |
| 2425 | beta2423/2424 회귀 테스트 | 잠금 |

## 핵심 발견 (이번 batch)

**큰 bug fix** (beta2424): hard mesh 의 BL 가 patch_cap (beta2393) 과
상호작용해 wall_face_indices 가 stale → IndexError. 새 guard 로 graceful
filter. validator-driven로 발견.

**근본 GUI 갭** (beta2410-2422): mesh_integrity_suspect 와 BL stats 가
schema 까지만 있고 GUI 에 안 보였음. 이제 schema → history → dialog →
CSV → PDF → CLI → GUI checkbox 모두 propagate.

## 누적 개선 (전체 59 카드 기준)

### 정량 효과 (validator-driven)

| 메쉬 | tet (이전 → 현재) | hex (이전 → 현재) | poly (이전 → 현재) |
|------|------------------|-----------------|------------------|
| #1 V=3116 SI+NM | 2 → **1453 cells** | 648s → **325s** | 614s → **125s** |
| #2 V=12k SI+NM | 1 → **1072 cells** | 142s → **88s** | 614s → 509s |

### 핵심 기능 추가
- **Jacobson 2013 generalized winding number** (SI-robust inside test).
- **Pointwise T-Rex 동등 LCR + aniso prism splitting + hex BL** skeleton.
- **3-engine integrity flag parity** (tet/hex/poly).
- **GUI 완전 parity** — schema → CLI → GUI 모두 노출.

## 남은 갭

1. **tet quality D → C** (mq 0.05-0.10 → 0.10+).
2. **hex perf 300s → < 60s** (octree 추가 vectorization).
3. **poly hard mesh cell count 정상화**.
4. **C7 native binary export** (StarCCM+ .ccm / Fluent partitioned).
5. **C8 GPU CUDA full pipeline**.
