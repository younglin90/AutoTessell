# CARD BETA2823_SMOOTH_LOCK_BOUNDARY_VERTS (beta2823) — mesher.py: Laplacian smoothing 의 lock set 을 boundary vertex 전체로 (표면 주름의 진범)

**target_engine**: tet
**모티프**: fTetWild §3.5 — smoothing 은 surface vertex 를 입력 표면 밖으로 절대 내보내지 않는다 (`third_party/fTetWild/src/MeshImprovement.cpp` smooth 단계는 `is_surface_fs` 정점을 표면에 구속). 우리 코드엔 그 구속이 8 개 정점에만 걸려 있다.

## 이론적 근거

- **사이클 2 전제 정정 (실측)**. Advisor 가 제시한 "경계면적 6.128 = 2% 잔차 = 몇 도짜리 주름" 은 **면적 메트릭이 눈이 멀어서 생긴 과소평가**다. 실측 (cube.stl / draft / N=2000 / P4C=0):
  - 경계면적 **5.939 (0.99x)** — solid 테스트는 **통과**한다.
  - 그런데 **∑|cell volume| = 0.869** (참값 1.0) → **부피의 13% 가 없다**. 발산정리 값은 0.770 이지만 경계에 **불일치 방향 edge 62/1330** 이 있어 (닫힌 orientable manifold 가 아님) 신뢰 불가 — 두 값의 불일치 자체가 증상이다.
  - 경계 정점 **199/236 이 입력 표면에서 이탈**, median **0.0319**, max **0.153** (= 큐브 한 변의 15%). "몇 도" 가 아니다.
  - 면적이 0.99x 인 이유: 안쪽으로 우그러진 주름은 부피를 13% 먹으면서 면적은 거의 보존한다. **면적 ratio ≤1.05 게이트는 크레이터에 대해 구조적으로 맹목**이다.
- **문제 정의**. carve (winding filter) 직후 메쉬는 **완벽하다**: `plane_coverage=1.00`, 경계면 **322/322 전부 축정렬**, boundary vertex median off-plane **0.00000**. 표면은 이미 정합돼 있다. 그 다음 한 호출이 그것을 부순다.
- **범인 (call-site 단위 계측)**. `plane_coverage` 를 caller line 별로 spy:

  | caller | n_tets | bnd | axis-aligned | pc | median off-plane |
  |---|---|---|---|---|---|
  | mesher.py:1290 | 1520 | 322 | **322** | 1.00 | 0.00000 |
  | mesher.py:1304 | 1520 | 322 | 1 | 0.00 | 0.06363 | ← 손상, 그러나 **guard 가 revert** |
  | mesher.py:1771 | 1520 | 322 | **322** | 1.00 | 0.00000 | ← 복구됨 |
  | mesher.py:1842 | 1518 | 330 | **5** | 0.00 | 0.03199 | ← 손상, **revert 없음 → 최종 메쉬로 유출** |

  1779 과 1842 사이의 유일한 point-이동 블록 = `smooth_then_drop_slivers` (**mesher.py:1804-1829**).
- **직접 계측** (`smooth_then_drop_slivers` 입출력 spy, 동일 호출):
  ```
  n_pts=300  n_locked=8  (max_lock_id=7)
  boundary_verts=163  →  LOCKED=8,  UNLOCKED=155
  boundary verts MOVED by smoothing: 133/163,  max_move=0.11392
  median off-plane  BEFORE=0.00000  →  AFTER=0.03186
  ```
  **한 호출에서 0.0 → 0.0319.** 최종 메쉬의 결함값과 정확히 일치한다. 증명 끝.
- **근본 원인** (mesher.py:1809-1811):
  ```python
  n_surface_in = int(V.shape[0])                      # cube.stl → 8 (dedup 된 STL 정점)
  locked_smooth = np.arange(min(n_surface_in, final_pts.shape[0]))   # = [0,8) = 8 개 코너뿐
  ```
  `V.shape[0]` 은 **입력 STL 정점 수**이지 메쉬의 표면 정점 수가 아니다. BSP 삽입이 큐브 면 위에 만든 155 개 표면 정점은 lock 밖 → Laplacian (`n_smooth_iter=2, relax=0.25`) 이 이웃 무게중심(대부분 내부)쪽으로 끌어당김 = 교과서적 **Laplacian 부피 수축**. 부피 13% 손실, 법선 ~7° 기울어짐, skew 63~108 전부 여기서 나온다.
  **주의**: `n_surface = V.shape[0]` (mesher.py:797) 이므로 `arange(n_surface)` 로 바꾸는 것은 **같은 8** 이다. 무의미. 코드베이스에 "표면 정점 전체" 집합은 **존재하지 않는다** — carve 된 메쉬의 boundary face 에서 유도해야 한다.
- **가드 누락**. 이 블록의 채택 조건은 `new_tets.shape[0] >= final_tets.shape[0] * 0.9` — **셀 수만** 본다. 바로 앞 블록(1764-1799)과 바로 뒤 블록(1832-1870)은 **둘 다 `plane_coverage` revert guard 를 갖고 있다**. point 를 움직이는 유일한 블록만 그 가드가 없다.
- **레퍼런스**: fTetWild §3.5 (smoothing 은 surface 정점을 표면에 구속), Hu et al. 2020 §3.2 `track_surface_fs`; 코드 내 동일 패턴 `mesher.py:1764-1799`, `mesher.py:1832-1870`.
- **혁신성**: novelty 2 (표면 정점 집합을 carve 된 경계에서 유도 — 기존에 없던 구속) / rigor 3 (call-site 단위 before/after 실측 + 함수 입출력 직접 spy, 0.0→0.0319 단일 호출 귀속) / impact 3 (부피 13% 손실 + skew 의 단일 진범) = **8**.

## 변경

- 파일: `core/generator/native_tet/mesher.py` (**단일 파일**)
- 함수: `generate_native_tet`, 블록 **line 1804-1829** (`smooth_then_drop_slivers`)
- 핵심 변경 (≤30줄):
  1. `from core.generator.native_tet.plane_coverage import _tet_boundary_faces, plane_coverage as _pc_jj3` 추가.
  2. **lock set 교정**: `_B = _tet_boundary_faces(final_tets)` → `_bnd = np.unique(_B.ravel())` →
     `locked_smooth = np.union1d(np.arange(min(n_surface_in, final_pts.shape[0]), dtype=np.int64), _bnd.astype(np.int64))`.
     근거: carve 직후 boundary vertex 는 **입력 표면 위에 정확히** 있다 (median off-plane = 0.00000 실측). 그러므로 lock 은 근사가 아니라 정확하다.
  3. **가드 추가** (이웃 블록과 동일 패턴): 호출 전 `prev_pts_jj3 / prev_tets_jj3 / prev_area_jj3 = _pc_jj3(...).area_coverage`, 채택 후 `new_area_jj3` 재측정 → `prev_area_jj3 > 0 and new_area_jj3 + 0.05 < prev_area_jj3` 이면 `log.warning("native_tet_smooth_then_drop_revert", ...)` + `final_pts, final_tets = prev_pts_jj3, prev_tets_jj3`.
  4. 기존 `new_tets.shape[0] >= final_tets.shape[0] * 0.9` 채택 조건은 **그대로 유지** (건드리지 않음).
- **단조 가드**: 2번(lock)이 근본 수정, 3번(revert)이 안전망. **검증 신호**: lock 이 옳다면 revert 는 **0 회 발화**해야 한다 (`native_tet_smooth_then_drop_revert` 로그 부재 = lock 정확성 증명). 발화하면 lock set 유도가 틀린 것 → 그 로그를 근거로 보고.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 AUTO_TESSELL_P4C_PYTETWILD=0 python -m pytest tests/test_native_tet_solid_volume.py -q
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python -m pytest tests/test_native_tet_target_cells.py tests/test_cylinder_wall_fidelity.py tests/test_native_tet_harness.py tests/test_native_tet_phaseA.py -q
```

## 합격 기준 (validator 가 평가)

**기준선은 planner 실측** (cube.stl / draft / N=2000 / P4C=0). Advisor 제시값(482 중 469 이탈, skew 107.9, area 6.128)과 다른 것은 mesher 가 다중 pass 를 돌리고 `_score` 가 그중 하나를 고르기 때문의 run 간 변동 — 방향은 동일.

1. **(최우선) boundary vertex median off-plane: 0.0319 → ≤ 1e-9.** 이 카드의 정의 지표.
2. **∑|cell volume|: 0.869 → ≥ 0.97** (참값 1.0). 면적이 못 보는 크레이터를 보는 지표.
3. **축정렬 경계면 비율: 10/464 → ≥ 95%.**
4. `tests/test_native_tet_solid_volume.py` **계속 통과** (area ratio 0.99 → ~1.00, 여전히 ≤1.05). solid 회귀는 즉시 FAIL.
5. skew: 63.3 → **큰 폭 하락 기대** (주름이 진범이므로). draft 임계 8.0 미도달이어도 **이 카드 사유로 revert 금지** — 방향과 폭만 본다.
6. 회귀 가드: `test_native_tet_target_cells`, `test_cylinder_wall_fidelity`, `test_native_tet_harness`, `test_native_tet_phaseA`. **기존 플래키/실패는 쫓지 말 것**: `test_native_tet_phase_a_improves_cube_boundary` (플래키), `test_generator.py::TestTierGracefulFail::{test_tier_wildmesh_quality_params_draft, test_tier_wildmesh_section_topology_detects_hole}` (pristine HEAD 에서도 실패).
7. bench 시간 ≤ 기존 +15% (`_tet_boundary_faces` 1 회 O(T) 추가, 2400 tet 기준 무시 가능).

## 예상 부작용 (정직 기록 — revert 사유가 **아님**)

- **worst_mq 0.208 이 하락할 수 있다.** `smooth_then_drop_slivers` 는 지금 163 중 133 개 경계 정점을 자유롭게 움직여 sliver 를 "고쳐" 왔다 — **표면을 부수는 대가로**. 자유도를 뺏으면 sliver 개선폭이 준다. 사이클 1 과 동일한 판정 원칙: **형상을 부숴서 얻은 품질 수치는 가짜다.** validator 는 이 카드에 한해 worst_mq/grade 회귀를 수용하고 **기준 1-4 (fidelity) 로만 판정**한다.
- 반대로 skew/non-ortho 는 크게 좋아질 것이다 (주름 제거).

## 카드 시퀀스 위치

solid-volume 시퀀스 **2/4** (사이클 1 의 "다음 카드 후보" 를 실측으로 재정의 — area_coverage 가드 교체가 아니라 **가드가 아예 없는 블록** 이 진범이었다).

1. ✅ (BETA2822) 술어 교정 → solid 확보.
2. **(본 카드)** smoothing lock set 교정 → 표면 정점 고정, 부피/평면성 회복.
3. `_score` (mesher.py:1920) 가 fidelity 를 무시한다 — 실측: 후보 중 `pc=1.00 axis=322/322` 인 **완벽한 후보가 존재했는데 broken 후보가 선택**됐다. scoring 에 plane_coverage 반영.
4. 슬리버 부채 감축 (solid 불변식 하에서 §3.4 local op). **AVOID 준수**: BSP 직후 `smooth_amips_*` 금지(4회), flip 후 `collapse_short_edges` 금지, 신규 Steiner 금지(3회), `envelope_relocate.py` 재활성 금지(2회).

**다음 카드 후보**: BETA2824 — `n_surface = V.shape[0]` (mesher.py:797) 잠복 버그. `filter_slivers` 의 `has_surf = (tets < n_surface)` 가 8 개 코너만 boundary tet 으로 인식 (void_free 가 현재 무해화 중이나 legacy 경로엔 잔존).
