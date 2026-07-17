# CARD BETA2822_SOLID_VOID_FREE_FILTER (beta2822) — filter.py: 품질 기반 내부 tet 삭제 제거 (void-free filtering)

**target_engine**: tet
**모티프**: fTetWild `filter_outside` — 제거 술어는 winding number `W > 0.5` **단 하나** (`third_party/fTetWild/src/MeshImprovement.cpp:1638`)

## 이론적 근거

- **문제 정의**. 현재 `filter.py:104` 의 제거 술어:
  `keep = inside_mask ∧ (q ≥ thr)`
  vendored 레퍼런스 (`MeshImprovement.cpp:1636-1641`) 의 술어:
  ```cpp
  if (W(index) <= 0.5) { t.is_removed = true; } else { n_tets++; }
  ```
  fTetWild `filter_outside` 전체에 **quality 항이 존재하지 않는다**. `W > 0.5` 인 슬리버는 무조건 유지된다. 즉 우리 코드는 레퍼런스에 없는 `∧ (q ≥ thr)` 논리곱을 추가했다. native_tet 은 fTetWild 포팅이라는 표준 지시(MEMORY) 위반이자 버그.
- **void 정리** (본 카드의 수학적 근거). kept set K 의 경계 `∂K = {정확히 1개의 kept tet 에 속한 face}`. 워터타이트 입력 S 의 tet 메쉬가 solid 이려면 `∂K ⊆ S`. 내부 tet t (4 face 전부를 inside tet 과 공유) 를 K 에서 빼면 그 4 face 가 `∂K` 에 편입되나 `S` 에 속하지 않는다 ⇒ void 벽. **따라서 품질 기반 내부 삭제는 solidity 와 원리적으로 양립 불가능**하며, 임계값을 어떻게 조율해도 해소되지 않는다. 슬리버는 삭제가 아니라 위상을 보존하는 국소 연산(split/collapse/swap/smooth)으로 제거해야 한다 (fTetWild §3.4 루프 → §3.5 winding filter 순서; `ftetwild_main_loop.py:16` 이 이미 이 순서를 문서화).
- **실측** (Advisor 3행 + planner 계측). 최종 `filter_slivers` 호출 (cube.stl / draft / N=2000 / P4C=0):
  `n_inside=2402 → n_kept=2035, interior_dropped=361` (**부피의 15.0% 를 삭제**), `bnd_protected=0`.
  → `protect_boundary_faces` 루프는 **한 번도 발화하지 않는다**(표면 정점 덮임만 보므로). 경계면적 20.409 = 참값 6.000 의 **3.40배**.
- **핵심 아이디어**:
  1. `void_free` 파라미터 도입 → `keep = inside_mask` (q 술어 제거). 레퍼런스 `filter_outside` 와 동일 술어.
  2. q 는 계속 계산하되 **보고 전용**: `n_slivers_retained` / `n_interior_slivers_retained` 로 그동안 삭제로 숨겨온 부채를 가시화. 다음 사이클이 0 으로 몰아야 할 지표.
  3. `void_free=False` 는 legacy 동작 그대로 보존 → A/B 가능, 되돌림 1줄.
- **레퍼런스**: `third_party/fTetWild/src/MeshImprovement.cpp:1609-1651` (`filter_outside`), `src/MeshIO.cpp:499` (`skip_tet = is_outside` — export 술어도 outside 단독), Hu et al. 2020 §3.4/§3.5.
- **혁신성**: novelty 2 (레퍼런스 구현과의 술어 불일치 교정) / rigor 3 (void 정리 + 1차 소스 술어 + 실측) / impact 3 (CFD 에서 구멍은 치명적, 231 라운드 미개척 방향) = **8**.

## 변경

- 파일: `core/generator/native_tet/filter.py` (**단일 파일**)
- 함수: `filter_slivers` (line 55-148), `FilterResult` (line 19)
- 핵심 변경 (≤40줄):
  1. `filter_slivers(..., void_free: bool = True)` 추가.
  2. `void_free` 일 때 `keep = inside_mask.copy()` — line 104 의 `& (q >= thr)` 논리곱 제거. q 계산은 유지(보고용).
  3. `FilterResult` 에 `n_slivers_retained`, `n_interior_slivers_retained` 필드 추가:
     `int((inside_mask & (q < thr)).sum())`, `int((~has_surf & inside_mask & (q < thr)).sum())`.
     (기존 361 이 이제 "삭제" 가 아니라 "보유 부채" 로 보고됨 — 동일 수치가 정직하게 드러남.)
  4. `void_free` 일 때 `protect_boundary_faces` 루프는 자동 no-op (`dropped_idx` 가 공집합) — 불필요 연산 skip 가드만 추가. bench 비용 증가 없음.
  5. `void_free=False` 경로는 기존 코드 그대로 (한 줄 분기).
- **단조 가드**: 본 카드는 가드를 추가하지 않고 **술어를 교정**한다. `mesher.py:1182` 의 `area_coverage` revert 가드는 내부 삭제를 감지하지 못하므로(표면 평면 덮임이라는 엉뚱한 양을 측정) 무력 — `void_free` 하에서는 `prev == new` 라 발화하지 않아 무해. 교체는 다음 카드.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python -m pytest tests/test_native_tet_solid_volume.py -q -rX
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python -m pytest tests/test_native_tet_target_cells.py tests/test_cylinder_wall_fidelity.py tests/test_native_tet_harness.py -q
```

**xfail strict 주의**: 수정이 통하면 pytest 는 `XPASS(strict)` 를 **failure 로 보고**한다(exit 1). 이는 성공 신호다. maker 는 1번 명령에서 XPASS 확인 후 `tests/test_native_tet_solid_volume.py` 의 `@pytest.mark.xfail(...)` 데코레이터 **블록만 제거**하고 docstring 의 STATUS 표를 새 실측으로 갱신 → 영구 회귀 가드로 승격. **`assert ratio <= 1.05` 는 절대 손대지 말 것** (허용오차 완화 = Rule E 위반). 이 마커 제거 편집에 한해 2번째 파일 수정 예외 허용.

## 합격 기준 (validator 가 평가)

- **(최우선) 경계면적 ratio ≤ 1.05** — 예상 0.99 (5.94/6.00). 미달이면 FAIL.
- `test_native_tet_target_cells`: 예상 통과. N=2000 은 2035 → 2402 (1.20x, band [0.75, 1.45] 내). 게다가 tier 에 **closed loop** (측정→edge 보정, best-of by log-ratio) 이 있어 재수렴하므로 실제론 더 낮을 것.
  **취약점**: `test_exact_small_target_is_hit` (N=50, band 40-60) — attainable set `{35, 50, 171, ...}` 이 이동하면 깨질 수 있음. **깨지면 band 를 넓히지 말고 그대로 보고**.
- `test_cylinder_wall_fidelity`: 테스트가 `P4C_PYTETWILD=1` 을 명시 세팅(line 77)하므로 외부 구제 경로 — 영향 낮음. 깨지면 **완화 금지, 보고**.
- BL: 이 카드는 BL 이전 단계 — BL 합격 분포 동등 기대.

## 예상 부작용 (정직 기록 — revert 사유가 **아님**)

- **skew 10.5 → ~63, non-ortho 상승. cube draft verdict 는 여전히 FAIL.** HEAD 의 skew 10.5 는 품질이 좋아서가 아니라 나쁜 셀을 삭제해서 나온 값 — 증거 인멸이었다. **구멍 ≫ 슬리버** (CFD 에서 void 는 해를 무의미하게 만든다). **skew 회귀를 이유로 이 카드를 revert 하지 말 것.**
- bench tet grade (C2/D3) 가 D 쪽으로 이동 가능. `worst_mq 0.208` 도 하락 가능 — 삭제됐던 셀이 집계에 복귀하는 것이므로 **악화가 아니라 정직해진 것**. validator 는 **이 카드에 한해 grade/worst_mq/skew 회귀를 수용**하고 solid 게이트로만 판정.
- 도달선 근거: pytetwild 가 동일 형상에서 non-ortho 51~58 / mean_q 0.52 / min_q 0.14 달성. `core/generator/native_tet/harness.py:71-75` 의 "tet mesh 는 boundary sliver 로 88-90° 가 구조적 특성" 주석은 **틀렸고 이 버그를 합리화해 온 것** — 믿지 말 것 (별도 카드에서 정정).
- legacy 분기 (`mesher.py:1204-1224`, `enable_phase_a=False`) 는 동일 버그 잔존. default 는 `True` (mesher.py:111) 라 실사용 경로엔 영향 없음 — 후속 카드.

## 카드 시퀀스 위치

solid-volume 시퀀스 **1/4** (신규 시퀀스, 231 라운드 중 최초 — catalog grep 상 solid/void/hole 언급 0회).

1. **(본 카드)** 술어 교정 → solid 확보 + 슬리버 부채 가시화.
2. `mesher.py:1182` area_coverage revert 가드 → void-wall count 기반 무결성 가드로 교체 (엉뚱한 양 측정 중단).
3. 슬리버 부채 감축: `ftetwild_main_loop.py` 의 §3.4 split/collapse/swap/smooth 를 solid 불변식 하에 활성.
   **AVOID 준수**: BSP 직후 `smooth_amips_*` 호출 금지(4회 reject), flip 후 `collapse_short_edges` 금지(reject), 신규 Steiner 카드 금지(3회 reject, 비-Delaunay 구현 전까지). 반드시 main loop 스케줄 **내부**에서만.
4. skew/non-ortho 를 pytetwild 도달선(non-ortho 51~58, mean_q 0.52)까지.

**다음 카드 후보**: BETA2823 — void-wall count 무결성 가드로 mesher.py 의 area_coverage revert 가드 교체.
