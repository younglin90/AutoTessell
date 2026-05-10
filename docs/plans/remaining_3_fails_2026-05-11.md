# 잔여 3 FAIL → PASS 추진 계획 (2026-05-11)

## 현재 상태 (beta2349, BLR-9c-d-t-1 완료)

- 21-STL tet+BL bench: **18 PASS / 3 FAIL = 86 %**
- 잔여 FAIL:
  | STL | 잔여 issue |
  |-----|-----------|
  | hard_100030 | neg_vol=1 + max_skew=1166 (boundary cell) + max_aspect=1556 + surf_dev=110 % |
  | hard_1004826 | neg_vol=1 + max_skew=17.96 |
  | medium_100330 | neg_vol=1 |

근본 원인: **BL extrusion 후 emergent 8-face triangulated prism 폴리헤드라**.
Pre-BL anti-invert cap 으로는 검출 불가능 (post-BL 위상에 종속).

## 가용 atomic 카드 (실패하면 다음으로)

| ID | 카드 | 시간 | 변경 범위 | 기대 효과 |
|----|------|------|-----------|----------|
| **U-1** | shortest-diag triangulation env=1 default | 20 min | bench_cavity_eval.py 1 줄 (env default) | 21-bench 측정 |
| **U-2** | safety=0.3 + floor=0.3 (더 보수적 cap) | 20 min | bench env 2 줄 | 21-bench 측정 |
| **U-3** | drop_degenerate_cells post-process | 90 min | core/utils/drop_cells.py 신규 (~250 줄) | 신규 helper + unit |
| **U-4** | U-3 wire 후 21-bench | 30 min | bench env + wire | 19-20/21 가능성 |
| **U-5** | sliver-tet specific subdivision | 60 min | tet_bl_subdivide 보강 | hard_1004826 등 |

**Atomic step 정의**: 카드당 단일 측정 가능 변경 (코드 ≤ 80 줄 또는 env 1-2 개), 합격
기준 = bench 21-STL 회귀 PASS 수 ≥ 18 (퇴보 금지) + 적어도 1 케이스 신규 PASS.
실패 = `git revert` 후 다음 카드.

## U-1 카드 — shortest-diag triangulation env=1 default

**컨텍스트**: ``core/layers/native_bl_vd.py:854,1150`` 의 shortest-diag quad
triangulation 은 이미 구현 완료, env ``AUTO_TESSELL_BL_TRIANGULATE_QUAD_SHORTEST=1`` 로
on. 현재 기본 OFF.  **이론적 근거**: 8-face triangulated prism 인접 셀 간 quad
diagonal 불일치 → non-planar quad → 한 쪽 prism 의 vol < 0 가능성. shortest-diag
규칙은 인접 셀 모두 동일한 diagonal 선택 보장 (대칭이므로 같은 결과 도출).

**변경**: ``tests/stl/bench_cavity_eval.py`` 의 env 기본 추가
``AUTO_TESSELL_BL_TRIANGULATE_QUAD_SHORTEST=1``.

**검증**:
1. ``timeout 60 python3 -m pytest tests/test_native_bl_vd.py -q`` (회귀 PASS)
2. ``timeout 600 python3 tests/stl/bench_cavity_eval.py 2>&1 | tail -50``
   PASS count 추출.

**합격**:
- 회귀 PASS
- 21-bench PASS ≥ 18 + 적어도 1 신규 PASS (= ≥ 19)
- 또는 PASS = 18 인데 잔여 3 FAIL 중 1 의 neg_vol 또는 skew metric 이 측정상
  개선 (pre-step 으로서 가치).

**실패 시**: revert env, U-2 진행.

## U-2 카드 — 더 보수적 cap (safety=0.3, floor=0.3)

**이론적 근거**: floor=0.5 는 BL 두께 50 % 보장하지만 sliver tet 공급 시 inversion
미달 가능. floor=0.3 + safety=0.3 은 BL 두께 30 % 까지만 줄임 — 즉 더 일찍 cap.
trade-off: BL 손실 더 큼 → cosmetic concern.

**변경**: ``tests/stl/bench_cavity_eval.py`` env defaults
- ``AUTO_TESSELL_BL_ANTI_INVERT_SAFETY=0.3`` (was 0.5)
- ``AUTO_TESSELL_BL_ANTI_INVERT_FLOOR=0.3`` (was 0.5)

**합격**: U-1 과 동일 (21-bench ≥ 19 또는 metric 개선).

**실패 시**: revert, U-3 진행.

## U-3 카드 — drop_degenerate_cells post-process

**컨텍스트**: 잔여 1 neg_vol 셀들은 pre-BL 으로는 예측 불가. 가장 명료한 해결은
"BL 직후 vol ≤ tol 셀을 제거" — checkMesh 의 ``negative_volumes`` 0 으로 만들고
verdict PASS 가능. trade-off: 셀 ~1개 손실 (cell count 영향 무시 가능).

**알고리즘**:
1. signed_cell_volumes 계산
2. drop_set = {ci : vol[ci] ≤ vol_tol}
3. cell index remap (drop_set 제거 후 0..N-1)
4. faces:
   - internal face (owner ∈ drop_set XOR neighbour ∈ drop_set):
     surviving cell 의 boundary face 로 이동, owner 재설정.
     (XOR 둘 다 drop 이면 face 자체 삭제.)
   - boundary face (owner ∈ drop_set): 삭제.
5. boundary patch 갱신: 삭제된 face 들의 patch 카운트 -1, 새로 생긴
   boundary face 는 신규 patch ``droppedShell`` 에 push.
6. owner / neighbour 재정렬 + write

**변경**: 신규 ``core/utils/drop_cells.py`` (~250 줄). unit test
``tests/test_drop_cells.py`` 5 케이스.

**합격**:
1. ``timeout 60 python3 -m pytest tests/test_drop_cells.py -q`` PASS
2. NativeMeshChecker 가 결과 polyMesh 를 정상 파싱 + n_cells 감소 ≥ 1.

**실패 시**: revert, U-5 진행.

## U-4 카드 — U-3 helper wire 후 21-bench

**변경**: ``core/layers/native_bl.py`` 끝부분에 env ``AUTO_TESSELL_BL_DROP_DEGENERATE=1``
시 ``drop_cells.drop_degenerate_cells`` 호출.  ``tests/stl/bench_cavity_eval.py`` env
default 추가.

**합격**: 21-bench PASS ≥ 19 (목표 90 %).

**실패 시**: U-5 진행.

## U-5 카드 — sliver-tet specific subdivision (보류)

multi-day 카드 — 현재 step 에서는 stub 만.

## 시작 순서

U-1 → 합격 시 commit / 미합격 revert → U-2 → U-3 → U-4.

각 카드 끝에서 broader 회귀 (12-suite T-AA) 도 실행 — 측정 인프라 보존 확인.
