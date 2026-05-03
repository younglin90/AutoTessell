# CARD BETA2820_HEX_SMALL_BBOX_PREFLIGHT (beta2820) — hex small-bbox pre-flight seed_density bump

**target_engine**: hex
**모티프**: cfMesh / classy_blocks octree resolution 자동 결정 — bbox_diag 가 작은 모델에서 default seed_density (그리드 분할수) 로 계산한 cell 변 길이 h = diag/seed_density 가 surface feature 보다 커서 winding-number filter 후 kept hex < 50 으로 떨어져 mesh_integrity_suspect 발동 → grade B 이하.

## 이론적 근거 (≤30줄)

- **문제 정의**: kept hex 수 N_kept(h) 는 h ↓ 일수록 대략 V_in / h^3 으로 증가. small-bbox (diag < 1) 에서 default seed_density=24 면 h ≈ diag/24 가 model thinnest feature t_min 보다 커서 N_kept < 50 → integrity suspect (mesher.py line 137 `_smallhex_floor`).
- **현 코드의 동작**: `mesher.py:681` 의 retroactive escalate 는 grid 생성 + winding-number 평가 후 N_kept 확인 후에야 발동 → 최대 10 회 retry × full grid 재구성 비용. 실패 케이스 (20-sample bench) 에서 escalate 6-8 회 진입 → 시간↑ + 일부는 cap binding 으로 회복 실패.
- **본 카드의 핵심 아이디어**:
  1. line 536 `diag_pre` 계산 직후 (grid 생성 전), `diag_pre < THRESH (default 1.0)` 이고 `target_edge_length` 가 user_set 이 아니면 `effective_seed_density = max(seed_density, ceil(seed_density * (THRESH/diag_pre)^α))` 로 pre-bump.
  2. α = 0.5 (sub-linear) — 매우 작은 bbox 에서도 over-shoot 방지.
  3. 기존 retroactive escalate 는 그대로 유지 (fail-safe). pre-bump 로 첫 시도부터 N_kept ≥ 50 달성 → escalate 진입률 감소 → wall time 단축.
- **단조 가드**: `diag_pre >= THRESH` 일 때 no-op (큰 모델 영향 0). user 가 `target_edge_length` 명시한 경우 no-op.
- **env gate**: `AUTO_TESSELL_HEX_SMALL_BBOX_PREFLIGHT` (default "1"). "0" 시 baseline 재현.
- **레퍼런스**: cfMesh `cfMeshLib::octreeModifier` resolution auto-bump, classy_blocks `Mesh.set_default_patch` adaptive cell count.
- **혁신성 평가**: novelty=2 (기존 retroactive 를 proactive 로 전환), rigor=2 (단조 가드 + α 안전계수), impact=2 (small bench 5/5 유지 + 20-sample bench 16→19/20 기대). 합=6.

## 변경

- 파일: `core/generator/native_hex/mesher.py` (단일 파일)
- 함수: `generate_native_hex` (≈line 536-540 사이 삽입)
- 핵심 변경 (≤30줄):
  1. `diag_pre` 계산 직후, `_p1_te_user_set == False` 이고 env gate ON 이면 small-bbox 검사.
  2. `_THRESH = float(env.get("AUTO_TESSELL_HEX_SMALL_BBOX_THRESH", "1.0"))`
  3. `if diag_pre < _THRESH and diag_pre > 1e-9:` → `_factor = (_THRESH / diag_pre) ** 0.5`; `_eff_sd = max(int(seed_density), int(np.ceil(seed_density * _factor)))`; `seed_density = min(_eff_sd, int(seed_density * 8))` (8x cap).
  4. `h_pre` 재계산: `h_pre = diag_pre / max(1, int(seed_density))` (line 537-539 식 그대로 적용).
  5. log.info("native_hex_small_bbox_preflight", diag=diag_pre, seed_density_orig=..., seed_density_eff=...).
- 단조 가드: bbox 큰 경우 (diag_pre >= 1.0) early-return → 회귀 0; user-set target_edge_length 경로 우회.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 90 python3 -m pytest tests/test_native_hex.py tests/test_native_hex_octree.py tests/test_native_hex_snap.py -q
```

## 합격 기준 (validator 가 평가)

- 회귀 PASS (3 hex test files)
- bench 시간 ≤ 75s (small bench, 5 samples)
- hex small bench: A >= 5/5 유지 (현 baseline)
- syntax 무오류 (`python3 -c "import core.generator.native_hex.mesher"`)
- env OFF (`AUTO_TESSELL_HEX_SMALL_BBOX_PREFLIGHT=0`) 시 baseline metric 동등 재현 (manual smoke)
- 단조 가드: 큰 bbox (diag>=1) sample 의 grid resolution / wall-time 변화 0

## 카드 시퀀스 위치

- HEX P1 시리즈 #1 of ~3 (sharded-weaving-raccoon.md P1.1 → 20-sample bench A 16→19/20 목표)
- 다음 카드 후보 (PASS 후): P1.2 hex_fragmentation_dropout (small-island hex cluster 제거 — 4 fail mesh 중 fragmentation 케이스), P1.3 hex_buffer_layer_adaptive (BL 인접 cell 자동 refine).
