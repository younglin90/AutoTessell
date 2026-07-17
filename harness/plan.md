# CARD BETA2825_DEGENERATE_SLIVER_REMOVAL (beta2825) — mesher.py: 축퇴 tet 50개를 위상보존 3-2 flip + 표면 대각 flip 으로 제거 (skew 1.7e29 → 유한, XPASS)

**target_engine**: tet
**모티프**: fTetWild §3.4 (topology-preserving sliver removal) + Klingner 2008 §"edge removal" (3-2 flip). 축퇴 제거를 **삭제 없이** 위상보존 국소연산으로.

## 이론적 근거 (planner 실측 — cube/draft/N=2000/P4C=0)

- **문제**: 최종 on-disk 메쉬에 축퇴 tet **50/2398** (|det|/6 < 1e-9). 전부 cap/sliver, min-edge 0.798×mean (짧은 변 없음 → collapse 무력), 50/50 경계 접촉. 이들이 max_skew 를 **1.7e29** 로, min_q 를 **0.0** 으로 만든다. fTetWild 는 같은 큐브에 축퇴 0/12866 — 벽이 아니라 우리 결함.
- **실측 분해 (핵심 발견)**: 50 = **37 내부 sliver + 13 표면 flap**. 계측 `scratchpad/exp_residual.py`:
  - 13 flap 은 전부 **4정점이 한 큐브 면 평면에 공면** (`verts_on_cube_plane=4/4`, `flat_in_cube_face=True`), 경계면 2/4, 경계변 5/6, 내부변 1/6. apex 가 자기 공유면과 공면이라 **모든 2-3 flip 이 축퇴** → 어떤 부피보존 내부연산으로도 못 뒤집는 구조적 BSP 표면 잔재.
- **`flip.py` 잠복 버그 (재사용 금지 근거)**: 기존 `flip_faces_23`/`flip_edges_32`/`flip_edges_44` 의 유효성 검사는 `abs(vol6) >= 1e-20` (**절대값**)뿐 — 비볼록(overlap) flip 을 수용한다. 실측: `face_flip_pass` 를 그대로 돌리면 축퇴는 50→0 이지만 **∑|vol| 1.003→1.569 (56% 겹침)**, 경계 파손 (`scratchpad/exp_flip_clears.py`). **이 카드는 그 함수들을 쓰지 말고** 아래 부호기반 유효성을 새로 구현한다.
- **본 카드의 핵심 (2단계, 둘 다 부피·경계 정확 보존 — 실측)**:
  1. **Phase 1 — 부호기반 3-2 flip**: 내부 edge (u,v) 를 3 tet 이 공유하고 반대삼각형 xyz 가 u,v 를 **분리**할 때만 (`sign(orient(x,y,z,u)) ≠ sign(orient(x,y,z,v))`, 둘 다 |·|>eps) → {u,xyz},{v,xyz}. 이는 3-tet 합집합 = 2-tet 의 **정확 항등식** → ∑|vol| 불변. 축퇴 접촉 edge 만 대상, 수렴까지 반복. **실측 50→13, ∑|vol| 1.0034 그대로, 경계 446 그대로** (`exp_signed_flip.py`).
  2. **Phase 2 — 표면 flap 제거 (표면 대각 flip)**: |vol|<1e-9 이고 4정점이 입력면 평면과 공면인 tet 제거. 그 4 face 가 모두 그 평면 안이라 삭제 시 내부 2 face 가 **같은 평면 위 경계면**으로 재노출 → on-surface 면적 보존, 부피변화 0, off-plane void 0. **금지된 '내부 sliver 삭제'와 다르다** (내부 sliver 삭제는 off-plane void 벽을 노출; flap 은 공면이라 노출 안 함). **실측: 13 제거 후 축퇴 0, ∑|vol| 1.0034, on 6.0000, off 0.0000** (`exp_combined.py`).
- **단조 가드 (안전망, 일반 입력 대응)**: Phase 전후 `plane_coverage(V,F,·,·)` 의 `extra_area`(off-surface 면적)와 `area_coverage` 측정. `extra_area_post > extra_area_pre + 1e-6` 또는 `area_coverage_post < area_coverage_pre − 1e-3` 이면 **전체 pass revert**. cylinder 등 곡면에서 flap 조건이 오발동해도 revert 로 무해화.
- **레퍼런스**: Klingner & Shewchuk 2008 (edge removal / 3-2); Hu et al. 2020 fTetWild §3.4; 코드 `plane_coverage.py:_tet_boundary_faces/plane_coverage`, `validate.py:signed_volume6`.
- **혁신성**: novelty 2 (signed-validity 교정 + 37/13 분해 + 표면 대각 flip) / rigor 3 (분리삼각형 정확항등식 + 부피·경계 불변 실측 + extra_area revert) / impact 3 (마지막 solid 결함 제거 → skew 1e29→유한, 축퇴 0/N fTetWild 동급) = **8**.

## 변경

- 파일: `core/generator/native_tet/mesher.py` (**단일 파일**)
- 함수: `generate_native_tet`, **line 1923 직후 / `_prog("write", 0.9, …)` (line 1925) 직전** 에 try-block 삽입. 근거: non-skip 경로의 유일 write 는 **line 1938**; 이후 W3/flip/VAL1 은 in-memory 만 바꾸고 disk 미반영 → 이 지점의 `final_pts/final_tets` 가 disk 메쉬. 여기서 축퇴 50개가 존재. `V, F, final_pts, final_tets` 모두 scope 내 (1893/1906 에서 이미 사용).
- 핵심 변경 (≤70줄):
  1. `n_degen_pre` 및 `plane_coverage(V,F,…)` 의 `extra_area_pre/area_cov_pre` 측정. 축퇴 0 이면 no-op.
  2. **Phase 1**: edge→tets(dict) 구성 → 축퇴 접촉 내부 edge 중 owners==3 인 것에 부호기반 3-2 flip (분리삼각형 검사) → 새 2 tet 전부 재배향 후 +eps 양수 확인 → 교체. 축퇴 잔존 시 재빌드, 최대 6 sweep.
  3. **Phase 2**: 잔존 |vol|<1e-9 tet 중 입력면 평면과 공면(4정점 coplanar)인 것 제거.
  4. **가드**: `extra_area_post/area_cov_post` 재측정 → 위 revert 조건 위배 시 `final_pts,final_tets = pre_pts,pre_tets` + `log.warning("native_tet_degenerate_removal_revert", …)`. 통과 시 `log.info("native_tet_degenerate_removal", n_flip32=…, n_flap=…, n_degen_pre=…, n_degen_post=…)`.
- **단조 가드**: n_degen_post ≤ n_degen_pre AND extra_area 비증가 AND area_coverage 비감소. **검증 신호**: revert 로그 **0회** 발화 = flap 조건과 3-2 유효성이 정확하다는 증명.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 AUTO_TESSELL_P4C_PYTETWILD=0 python -m pytest tests/test_native_tet_solid_volume.py -q
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python -m pytest tests/test_native_tet_target_cells.py tests/test_cylinder_wall_fidelity.py tests/test_native_tet_harness.py tests/test_native_tet_phaseA.py -q
```

## 합격 기준 (validator 가 평가)

1. **(정의 지표) `test_native_tet_solid_volume.py::test_native_tet_has_no_degenerate_cells` XPASS** (축퇴 0). XPASS 확인되면 **xfail 마커만 제거**해 영구 가드 승격 (assert 불가침). 실측 근거: 50→13(3-2)→0(flap).
2. **(최우선 회귀 금지) 3개 solid 게이트 계속 통과**: `test_native_tet_covers_input_surface` (on 6.000), `test_native_tet_has_no_interior_voids` (off 0), `test_native_tet_mesh_encloses_true_volume` (∑|vol| 1.003x). 실측 전부 불변. 하나라도 되돌리면 즉시 FAIL.
3. **max skew 유한화**: 1.7e29 → 유한 (축퇴 0 의 직접 귀결). draft 임계 8.0 도달은 보너스, 미달이어도 이 카드 사유로 revert 금지.
4. 회귀 가드 계속 통과: `test_native_tet_target_cells`(셀수 2398→2348, target 2000 에 더 근접), `test_cylinder_wall_fidelity`, `test_native_tet_harness`, `test_native_tet_phaseA`.
   **알려진 결함 — 쫓지 말 것**: `test_native_tet_phase_a_improves_cube_boundary`(플래키), `test_generator.py::TestTierGracefulFail::{test_tier_wildmesh_quality_params_draft, test_tier_wildmesh_section_topology_detects_hole}`(pristine HEAD 도 실패).
5. bench ≤ 기존 +15% (edge-map O(T) + 6 sweep, 2400 tet 무시 가능).

## 예상 부작용 (정직 기록 — revert 사유 아님)

- 축퇴 tet 제거로 in-memory mean_q/min_q 가 바뀌나 **disk 메쉬만 판정 대상**이고 min_q 는 0.0→양수로 **개선**된다. Phase 2 는 삭제지만 **공면 flap 한정 + extra_area 가드**라 사이클 1~3 의 void-free 불변식을 깨지 않음 (off 0.0000 실측). 일반 곡면 입력에선 flap 조건 미충족 → Phase 2 no-op (안전).

## 카드 시퀀스 위치

solid-volume 시퀀스 **4/4 (마감)**. 1✅ 술어교정(BETA2822) → 2✅ smoothing lock(BETA2823) → 3✅ sliver-drop void-free(BETA2824) → **4 축퇴 위상보존 제거(본 카드)**. 이 카드 PASS 시 cube 는 표면·void·부피·축퇴 4 불변식 전부 만족 = self-impl tet 이 큐브에서 fTetWild 급 solid.

**다음 카드 후보** (본 카드 PASS 후, tet 회전): hard-mesh(V>500) worst_mq 0.076→0.20 격차 — `flip.py` 의 signed-validity 교정을 hard mesh 의 mean_q<0.15 경로 flip 패스에 적용 (본 카드에서 발견한 abs-value 버그를 산업 격차 축소로 확장). 또는 poly/hex 회전.
