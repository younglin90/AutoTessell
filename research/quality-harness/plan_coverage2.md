# CARD BETA2833 (coverage2) — L1 pymeshfix 다중-body 붕괴 상대가드

**target_engine**: tet (preprocessor L1 repair — native_tet 커버리지 회복)
**모티프**: BETA2832 상대 컴포넌트 가드를 한 단계 앞(L1 repair)으로 이식 — pymeshfix `remove_smallest_components` 파괴 차단

## 재측정 결과 (BETA2832 이후, P4C=0, 실측)

두 형상 모두 3분 이내(perforated 2.1s, sharp_ridge 19s) 완료. BETA2832는 두 클러스터를 **고치지 못함** — 근본원인이 `_final_validate`보다 **상류(L1 repair)**에 있었기 때문.

- **many_small_features_perforated_plate.stl** — 여전히 붕괴. area_ratio **0.011**, vol_ratio **0.003** (변화 없음).
  - 실측 트레이스: 입력 `is_watertight:true, 65-body, 8204 faces` → L1 `pymeshfix_repaired input_faces=8204 output_faces=128` → `final_validation num_faces=128`.
  - **근본원인 확정**: `repair.py::_repair_with_pymeshfix`의 `meshfix.repair()`가 pymeshfix 기본값 `remove_smallest_components=True`로 **65 body 중 largest 1개만 남기고 64개 폐기**. BETA2832의 `_final_validate` 컴포넌트 필터는 이미 1-body가 된 뒤 실행되어 무력(보존할 컴포넌트가 없음).
- **sharp_features_micro_ridge.stl** — **BETA2832 무관, 별개·더 어려운 문제**. 이번 실측은 area_ratio가 아니라 아예 **polymesh:false**(negative_volumes로 polyMesh 미기록), hausdorff_rel 218888, plane_coverage 0.0.
  - 실측 트레이스: 입력 `6 faces, non-watertight, open_boundary` → L1 `pymeshfix 6→4 faces`(열린 ridge를 **평평한 4-face sliver로 닫아** 지오메트리 파괴, volume 0.0167) → L2 강제 remesh `quadwild rc=139(segfault)` + `vorpalite rc=127(libgeogram.so.1.9.9 없음)` → naive subdivide `4→256`(파괴된 sliver를 세분). 결과 지오메트리 완전 오류.
  - **이 카드 범위 밖**: open-surface 보존 + 깨진 외부 remesher(env 의존) 문제로 상대가드 1개로 해결 불가. 후속 카드로 분리(아래 시퀀스).

## 이론적 근거 (근본원인 = pymeshfix 파괴적 기본동작)

- **문제 정의**: L1 repair 목표는 표면 보존(#1 불변식) 하 watertight 화. pymeshfix `MeshFix.repair()`는 단일-manifold 가정으로 `remove_smallest_components=True`를 강제 — 다중-body/미세-feature 입력에서 커버리지를 파괴한다. perforated는 **이미 watertight**인데도 warning=1로 repair가 트리거되어 오히려 64 body 손실.
- **핵심 아이디어**(BETA2832 상대가드의 상류 이식):
  1. 전역 `meshfix.repair()` 전에 `mesh.split(only_watertight=False)`로 컴포넌트 분해.
  2. 컴포넌트가 1개 → 기존 전역 경로 유지(cube/cylinder 무영향).
  3. >1개 → area ≥ `rel_keep(0.05)·A_max`인 body마다 **per-component pymeshfix** 후 `trimesh.util.concatenate`로 재결합(모든 유효 body 보존).
  4. **단조 면적 가드**: 재결합 결과 총면적 < `guard_frac(0.5)·입력면적`이면 입력 메시로 revert(표면 보존; sharp_ridge류 파괴적 붕괴의 안전망 겸용).
- **수렴/안정성**: per-component repair는 각 body를 독립 처리하므로 body 수 보존이 결정론적. 면적 가드가 최악의 경우 no-op(입력 반환)을 보장 → worst-case에서 회귀 불가.
- **레퍼런스**: pymeshfix `MeshFix.repair(remove_smallest_components=...)` 인자; BETA2832 `pipeline.py:805` 상대가드; 표면보존 #1 불변식(MEMORY product-spec).
- **혁신성 평가**: novelty 1 / rigor 2(단조 면적 가드 + 결정론적 body 보존) / impact 3(12-STL 커버리지 붕괴 잔여 1개 클러스터 해소). 합 6 — 진행.

## 변경

- 파일: `core/preprocessor/repair.py` (단일 파일)
- 함수: `_repair_with_pymeshfix` (line ~246)
- 핵심 변경 (≤70줄):
  1. try 진입부에서 `comps = mesh.split(only_watertight=False)`; `A_max`, `rel_keep=0.05` 계산.
  2. `len(comps) <= 1`: 기존 전역 `meshfix.repair()` 경로 그대로(무회귀).
  3. `len(comps) > 1`: `[c for c in comps if c.area >= rel_keep*A_max]` 각각 pymeshfix.repair → 결과 `concatenate` + `merge_vertices`. 실패 컴포넌트는 원본 컴포넌트로 유지(개별 fallback).
  4. `log.info("pymeshfix_component_repair", n_comps, n_kept, in_faces, out_faces)`.
  5. 단조 면적 가드: `out_area < 0.5*in_area`이면 입력 mesh 반환 + `log.warning("pymeshfix_area_guard_revert")`.
- 단조 가드: pre(입력) vs post(재결합) 총 surface area 비교; post < 0.5·pre → 입력 그대로 반환(revert). body 수는 상대가드로 결정론적 보존.

## 검증 명령 (unit_tester 가 그대로 실행, 각 ≤3분)

```bash
# 1) perforated 회복 (커버리지 회복 핵심, ~2s)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 90 python3 scripts/bench_native_tet_matrix.py \
  --stl tests/benchmarks/many_small_features_perforated_plate.stl
# 2) cube 회귀 (N=500, ~1s)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 60 python3 scripts/smoke_native_tet.py 500
# 3) cylinder 회귀 (정본 smoke)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 90 python3 scripts/smoke_native_cylinder.py
# 4) dual-torus 재회귀 금지 (BETA2832 회복분 보존; ~55s, 초과 시 기록만)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 170 python3 scripts/bench_native_tet_matrix.py \
  --stl tests/benchmarks/high_genus_dual_torus.stl
```

## 합격 기준 (validator 가 평가, 정량)

- **perforated (핵심)**: area_ratio ≥ **0.85** (현 0.011), vol_ratio ≥ **0.80** (현 0.003), neg_vol_cells=0. body 보존이 목적이므로 grade는 무관(quality는 별도 축).
- **cube 회귀**: smoke PASS 유지, area_ratio 1.00 ±0.01, cells 무붕괴(≥400 @N500).
- **cylinder 회귀**: 신규 회귀 금지 — area_ratio 1.00 유지, cells·skew 기존과 동등(±5%). (cylinder skew FAIL은 기존 알려진 별개 축, 악화 없으면 OK.)
- **dual-torus 재회귀 절대금지**: area_ratio ≥ **0.95**, vol_ratio ≥ **0.95** (BETA2832 baseline 1.010). 170s 초과 시 그 사실 기록 후 target 축소 orchestrator 호출로 대체 측정.
- **bench 시간**: perforated ≤ **10s** (현 2.1s + per-component 오버헤드, tiny body 65개).
- **BL 영향 없음**: 전처리 단계 변경이라 BL 합격 분포 불변.

## 카드 시퀀스 위치

- 커버리지 붕괴 클러스터 정리 시퀀스의 **2/3번째** (1: BETA2832 dual-torus `_final_validate` 상대가드 완료 / **2: 본 카드 — L1 pymeshfix 상대가드(perforated)** / 3 예정).
- **다음 카드 후보**(본 카드 PASS 후): `BETA2834_L1_OPEN_SURFACE_GUARD` — sharp_ridge류 open/thin 입력에서 L1 pymeshfix가 6→4 face로 지오메트리를 닫아 파괴하는 문제. non-watertight & 저-volume(thin) 입력은 pymeshfix hole-fill 대신 표면 보존 경로(면적·hausdorff 가드)로 우회. (env 의존 quadwild/vorpalite 깨짐은 별개 인프라 이슈로 분리 기록.)
