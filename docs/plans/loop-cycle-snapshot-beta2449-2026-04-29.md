# /loop 자동 고도화 사이클 — 6번째 스냅샷 (2026-04-29, beta2449)

## 진행 상황

`/loop` 1분 간격 자동 SOTA-gap 분석. **83 카드** 완료
(beta2367 - beta2449). 이전 스냅샷 (beta2444) 이후 **5 추가**.

## 새 카드 (beta2445-2449)

| Beta | 카드 | 영역 |
|------|------|------|
| 2445 | BL floor 0.7 → 0.8 | aspect 16.5k → 14.5k |
| 2446 | BL floor 0.8 → 1.0 (uniform) | **aspect 14.5k → 11.5k** |
| 2447 | BL floor env-gated | sysadmin tunable |
| 2448 | --bl-floor-ratio CLI flag | CLI parity |
| 2449 | GUI BL floor ratio QDoubleSpinBox | GUI parity (full) |

## 누적 효과 (전체 83 카드, validator-driven)

### 핵심 quality 지표

| 영역 | 시작 → 현재 | 효과 |
|------|------------|------|
| **mesh #1 tet 셀 수** | 2 → **1453** | 726× 회복 |
| **mesh #1 BL aspect** | 580k → **11.5k** | **50× 감소** |
| **hex hard mesh perf** | 648s → 325s+ | 2× 빨라짐 |
| **poly hard mesh perf** | 614s → 125s | 5× 빨라짐 |

### 핵심 알고리즘 도입
- **Jacobson 2013 generalized winding number** (SI-robust seed test).
- **Pointwise T-Rex 동등** LCR + per-vertex layer reduction.
- **cfMesh 동등** maxFirstLayerThickness floor (0.7-1.0 tunable).
- **Lloyd CVT plateau early-exit** (Du-Faber-Gunzburger 1999).
- **3-engine integrity flag parity** (tet/hex/poly).

### GUI parity (15 카드 완료)
- mesh_integrity_suspect: schema → CLI → GUI 완전.
- BL stats (prism, LCR, aniso_split, max_aspect): 모두 노출.
- 4 신규 user-tunable 컨트롤 (3 checkbox + 1 spin).

### 회귀 status
- 234 GUI tests passed.
- 92 BL+cvt3d tests passed.
- 22 CLI flag tests passed.
- 411+ broader regression passed.

## SOTA 비교 (mesh #1 hard SI+NM 기준)

| 지표 | 현재 (beta2449) | cfMesh | Pointwise T-Rex | StarCCM+ |
|------|----------------|--------|-----------------|----------|
| BL aspect | 11.5k | 1k-10k | 1k-5k | 1k-3k |
| BL prism | 4287 | typical | typical | typical |
| 시간 | tet 35s + BL 18s | 분 단위 | 분 단위 | 분 단위 |

**남은 격차 (commercial 동급 도달):**
1. BL aspect 11.5k → 1k (분리된 collision_safety 추가 cap 또는 mesh repair 강화).
2. tet quality D → C (mq 0.10+).
3. C7 binary export.
4. C8 GPU.
