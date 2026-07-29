# CARD BETA2832 (beta1) — genus multi-body: keep_largest_component가 dual-torus의 절반을 버린다

**target_engine**: tet
**모티프**: fTetWild §3.5 GWN inside-test는 무죄 — 손실은 preprocessor의 무조건적 single-body clamp. 표면 보존 #1 invariant 복구.

## 문제 정의 (실측 로그/수치)

정본 재현 `AUTO_TESSELL_P4C_PYTETWILD=0 python3 scripts/bench_native_tet_matrix.py --stl tests/benchmarks/high_genus_dual_torus.stl`:
```
stl_area=78.51 stl_volume=19.49 stl_watertight=true stl_bodies=1
cells=7776 bnd_area=44.12 area_ratio=0.562 sum_abs_vol=9.20 vol_ratio=0.472
degen=0 neg_vol=0 non_tet=0  verdict=FAIL
```
표면 56%·부피 47%만 채워짐 — 만든 셀은 정상(degen/neg=0)인데 **덮는 범위가 절반뿐**.

## 근본 원인 추적 (실측 로그)

가설을 하나씩 실측 기각/확정했다:
1. **inside-test(ray vs GWN)** — `AUTO_TESSELL_INSIDE_TEST=gwn`로 정본 bench 재실행:
   area 0.562→**1.043**(회복)이나 vol 0.472→**0.468**(변화 없음), skew 19.8→**2125**
   (경계 슬리버 인플레). ⇒ ray 오판은 area 일부만 설명, **부피 손실은 별개**.
2. **interior 밀도 부족** — 동일 orchestrator로 target_cells 2000/6000/12000 sweep:
   cells 7776→8391→8391, area 0.55, vol 0.47 **고정**. ⇒ 밀도는 무관, 기각.
3. **preprocess 단계 트레이스** (structlog):
   ```
   mesh_loaded            num_faces=4096
   keep_largest_component num_components=2
   final_validation       num_faces=2048   ← 정확히 절반
   ```
   ⇒ **`_final_validate`가 dual-torus를 2 컴포넌트로 split한 뒤 큰 것 하나만
   남기고 나머지 torus(2048 face)를 통째로 버린다.** 밀도·inside-test와 무관하게
   meshing 이전에 입력의 절반이 소실.
4. **확정 실험** — drop을 우회해 **전체 2-body STL(4096 face)** 을
   `generate_native_tet`에 직접 투입:
   `n_components(split)=2 faces=[2048,2048]` → **cells=14021 area_ratio=1.086
   vol_ratio=0.956** (둘 다 0.9 초과). ⇒ 근본 원인 100% 특정, 수정 방향 검증 완료.

`stl_bodies=1`(trimesh body_count)과 native split=2가 불일치 — 두 torus는
기하학적으로 disjoint인데 clamp가 이를 "노이즈 파편"으로 오인해 폐기.

## 핵심 아이디어

`_final_validate`의 **무조건 max-component clamp**(core/preprocessor/pipeline.py:805-815)를
**상대 가드 기반 multi-body 보존**으로 교체:
- 각 컴포넌트 surface area 계산, `A_max` = 최대 컴포넌트 area.
- `A_i ≥ rel_keep × A_max` (rel_keep=0.05, 즉 최대의 5% 이상)인 컴포넌트는 **모두 보존**,
  `trimesh.util.concatenate`로 재결합.
- 그 미만(진짜 repair 파편)만 폐기 → thingi10k 109-fragment 노이즈 제거 의도 유지.
- 단일 컴포넌트(cube/cylinder/sphere)는 no-op.

`rel_keep`은 **절대값이 아닌 최대 컴포넌트 대비 비율** — 프로젝트 상대 가드 원칙 준수.
dual-torus: 두 컴포넌트 모두 A_max의 100% → 둘 다 보존.

## 이론적 근거

표면 보존은 이 프로젝트 #1 불변식(ROADMAP "Governing invariants", MEMORY
product-spec-priorities). watertight 다중-body 입력의 body를 폐기하는 것은
solid 4대 불변식 중 "표면 덮임"을 meshing 이전에 파괴. mesh_type은 선호이지
계약이 아니듯(lessons-learned), 노이즈 제거도 상대적 파편만 대상이어야 하며
유효 body를 버려선 안 된다. concatenate 후에도 각 body는 disjoint watertight
manifold → downstream Delaunay+GWN carve가 정상 처리(실험 4에서 grade B 확인).

## 변경

- 파일: **core/preprocessor/pipeline.py** (단일 파일)
- 함수: `_final_validate` (line ~805-815, `keep_largest_component` 블록)
- 핵심 변경 (≤35줄):
  1. `components = mesh.split(only_watertight=False)`; `len > 1`일 때
     각 comp의 `float(c.area)` 산출, `a_max = max(areas)`.
  2. `kept = [c for c,a in zip(components,areas) if a >= 0.05 * a_max]`.
  3. `len(kept)==1` → `mesh = kept[0]` (기존 동작); 아니면
     `mesh = trimesh.util.concatenate(kept)` 후 `merge_vertices()`.
  4. 로그 `keep_largest_component` → `component_filter`:
     `num_components, n_kept, n_dropped, dropped_area_frac` 기록.
- 단조 가드: `n_kept` 컴포넌트의 총 area가 폐기 전 총 area 대비 감소분이
  `dropped_area_frac`로 로깅됨. 폐기는 오직 `< 0.05·A_max` 파편 → 유효 body 절대 미폐기.
- 신규 외부 의존 없음(trimesh 기존 사용, `util.concatenate` 가용 확인).

## 검증 명령 (unit_tester 그대로 실행)

```bash
# 회귀 (단일 컴포넌트 — no-op 이어야 함)
timeout 120 python3 scripts/smoke_native_tet.py
timeout 120 python3 scripts/smoke_native_cylinder.py
# 영구 4-불변식 게이트
timeout 90 python3 -m pytest tests/test_native_tet_solid_volume.py -q
# 타깃 (genus-2 dual-torus)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 150 \
  python3 scripts/bench_native_tet_matrix.py --stl tests/benchmarks/high_genus_dual_torus.stl
```

## 합격 기준 (validator 평가 — 정량)

- **high_genus_dual_torus**: `area_ratio ≥ 0.9` **AND** `vol_ratio ≥ 0.9`
  (실험 4 실측: area 1.086 / vol 0.956 — 여유 있게 통과 예상).
- cube smoke: area/vol/셀수 사전값과 동등(단일 컴포넌트 no-op) — 회귀 0.
- cylinder smoke: 동등 — 회귀 0.
- `test_native_tet_solid_volume.py`: cube 4-불변식 PASS 유지.
- 파일 1개·≤35줄 변경. bench 시간 증가 ≤ 기존+15%(다중-body는 face 2배라
  meshing 자체는 다소 증가하나 이는 정상 — 소실된 절반을 실제로 메싱하는 비용).

## 카드 시퀀스 위치

- "genus/multi-body 커버리지 붕괴" 시퀀스의 **1번째** 카드 (총 3개 예상).
- 다음 카드 후보 (PASS 후):
  - BETA2833: `many_small_features_perforated_plate`(area 0.011)·
    `sharp_features_micro_ridge`(0.345) — 동일 "커버리지 붕괴" 클러스터가
    같은 component-filter 또는 다른 원인(perforation을 통한 GWN 오판)인지 트레이스.
  - BETA2834: dual-torus quality 후속 — 현 grade B/mean_q 0.12, skew 잔존.
    커버리지 확보 후 다중-body sliver 개선(카드 분리 — 커버리지와 품질은 별개 축).

## 2026-07-27 — BETA2832 measured implementation

The relative component filter is present in the working tree and preserves
both comparable disjoint bodies (`num_components=2`, `n_kept=2`,
`n_dropped=0`). The dual-torus bench now reports `area_ratio=1.0094878`,
`vol_ratio=1.0097687`, `cells=11071`, `degen=0`, and `neg_vol=0` in `129.1 s`.
The coverage acceptance criterion therefore passes. The remaining
`max_skew=2.2101786e6` and low CDT recovery are quality/recovery problems and
are explicitly not folded into this coverage card.

Cube smoke remained solid (`surface=6.000`, `void=0.000`, `vol=1.008`,
`degen=0`), and the solid-volume/dual-torus regression set was `7 passed,
1 xfailed`. New unit tests cover comparable-body preservation and relative
small-fragment removal. BETA2832 is closed for coverage and BETA2834 remains
open for dual-torus quality.

## 2026-07-27 — BETA2834 first edge-recovery comparison

The real harness keeps `enable_edge_recovery=False`, so setting only the
indexed-lane environment flag does not change the production run; that run
remained at `cdt_ratio=0.005` and `max_skew=2.21e6`. A direct opt-in comparison
with `enable_edge_recovery=True` was therefore measured separately:

| lane | cdt ratio | cdt face ratio | plane coverage | mean q | time |
|---|---:|---:|---:|---:|---:|
| default direct | 0.881 | 0.707 | 0.897 | 0.1482 | 6.73 s |
| indexed + guarded edge recovery | 0.925 | 0.800 | 0.880 | 0.1524 | 14.24 s |

The opt-in lane improves CDT recovery and mean quality but worsens plane
coverage and costs about `2.11x`. It is therefore not promoted. The next
candidate must enforce a surface-conformity/area transaction around the full
edge-recovery lane, not expose the current direct result as a default quality
fix.

### Edge-lane boundary audit

The diagnostic snapshot around the direct opt-in lane recorded midpoint/B-W
insertion of `50` points with missing edges unchanged at `682`, followed by
the targeted flip passes. Across the complete edge-recovery lane, boundary
faces remained `1352→1352`, area remained
`103.399255187455→103.399255187455`, and the shared invariant was preserved.
Therefore the observed plane-coverage decrease is not a boundary-key/area
violation from this lane. The lane remains a measured CDT trade-off, while
the residual plane/skew issue is moved to the later recovery/BSP/quality
interaction rather than receiving an unjustified local boundary guard.
