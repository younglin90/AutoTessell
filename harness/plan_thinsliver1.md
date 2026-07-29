# CARD THINSLIVER1 — 내부 축퇴 슬리버 collapse (degenerate_removal 에 4-op collapse arm 추가)

**target_engine**: tet
**모티프**: fTetWild §3.3 4-op 중 **edge-collapse arm** — 현 `native_tet_degenerate_removal`
은 3-2 flip + coplanar-flap 만 있어 flip 불가 config 의 내부 축퇴 슬리버를 남긴다.

## 3형상 baseline 재확인 (P4C=0, 정본 bench, 각 <3min 실측)

| shape | cells | degen | skew | hard_fail | 시간 |
|---|---|---|---|---|---|
| naca0012 | 4041 | **17** | 58.83 | 1(skew) | 58s |
| very_thin_disk | 2129 | 4 | 2.38e28 | 3 | 3.7s |
| needle | 126 | 0 | 559.20 | 1(skew) | 3.3s |

## 근본 원인 실측 (harness/_thin_probe.py — polyMesh 재파싱, native_checker 공식 재현)

- **naca (선택)**: degen 17 = **17/17 전부 fully-interior (경계면 0개)**, vol 1.6e-10..8.7e-10
  (1e-9 문턱 바로 아래 flat 슬리버). **14/17 은 최단 edge 에 interior 끝점 보유**(surface-lock
  collapse 안전), 나머지 3 도 n_surf_v 1~2/4 라 다른 edge 에 interior victim 존재. → **표면 무접촉
  내부 국소연산으로 제거 가능한 curable class**. skew 58.83 driver 는 별개(경계 슬리버, apex 내부,
  n_surf_v 3/4, nd 1.7e-4) → **다음 카드**.
- **degen 이 왜 남나(실측)**: 기존 `degenerate_removal`(mesher.py:2036 Phase1)의 3-2 flip 은
  degenerate edge 가 **정확히 3 owner + 분리삼각형(su≠sv≠0)** 일 때만 발동. 이 17개는 owner≠3 이거나
  su==sv(동측 apex) 라 flip 불가. Phase2 flap 은 **입력면 평면 공면**만 제거 → 내부 슬리버 미해당.
  **collapse arm 부재가 gap**.
- **very_thin_disk / needle = 구조적, 이 카드 제외**: disk 의 skew 2.38e28 은 degen 4 = **전부
  all-surface(allsurf=True) vol=0 2-boundary-face wedge** = FSL4(dual_torus) 와 **동일 구조 known-limit**
  (내부 apex 부재 → volume-only op 불가). needle skew 559 는 단면(cross-section)이 근본적으로 미소해
  경계 슬리버가 기하적으로 강제됨. 둘 다 Garimella near-wall 내부점 삽입 로드맵(FSL4 §다음 로드맵)行.

## 이론적 근거 (≤30줄)

- **문제**: interior sliver σ, |det J(σ)|→0, 4정점 near-coplanar. fTetWild §3.3 은 collapse/split/
  swap/smooth 4-op 로 제거; 현 코드는 flip(swap)만 → flip-무자격 config 잔존.
- **핵심 아이디어**: Phase1(3-2 flip) 과 Phase2(flap) 사이에 **Phase1b: interior-incident
  edge-collapse** 삽입. 잔존 degen cell 마다 (interior victim, keeper) edge 를 골라 victim→keeper
  merge. keeper 는 항상 surface 우선(표면 정점 위치 불변), victim 은 non-surface interior 정점.
  단조성: collapse 는 위상보존·∑|vol| 근사보존(제거 tet vol≈0), 축퇴 1개 소거당 star 재구성.
- **레퍼런스**: Hu 2020 fTetWild §3.3 (collapse); 기존 `local_ops.collapse_short_edges`
  (`allow_surface_keeper`, `_collapse_vectorized_single_pass`) 의 keeper/victim 규약 재사용.
  단, 그 함수는 **길이-keyed** 라 normal-length flat 슬리버를 놓침 → 본 카드는 **volume-keyed**
  targeted collapse.
- **혁신성**: novelty 2 (flip-only pass 에 collapse arm 신설, length 아닌 degeneracy-keyed) /
  rigor 3 (17/17 fully-interior + collapse-safety 14/17 실측 + orientation·area·volume 3중 가드) /
  impact 2 (degen 17→0 correctness, skew 카드 준비, disk/needle 정직 이관). 합 = 7 (≥5).

## 변경

- 파일: `core/generator/native_tet/mesher.py` (단일 파일), degenerate_removal 블록.
- 위치: Phase1 3-2 flip 루프(line ~2103) 직후, Phase2 flap(line ~2105) 직전에 **Phase1b** 삽입.
- 핵심 변경 (≤65줄):
  1. `surf_set` = boundary-face 접촉 정점 집합(∵ surface 위치보존 lock). residual
     `degen_mask` cell 열거.
  2. 각 degen cell 의 6 edge 중 **victim=non-surf interior, keeper=상대끝점** 인 것 선택
     (없으면 skip). edge_owners 로 victim 의 incident tet star 수집.
  3. victim→keeper 치환 후 star 내 전 tet의 signed-vol6 **동부호 & |vol6|>_DEGEN_V6** 확인
     (orientation guard). 위반 시 이 collapse skip(무변경). 통과 시 victim-incident tet
     재작성(중복/축퇴 row drop), keeper 로 병합. 정점배열 불변(재인덱싱 없이 라벨치환).
  4. 1 sweep 당 consumed 정점 재사용 금지(중복 collapse 회피).
- 단조 가드(기존 재사용 + 1 추가): 블록 말미 기존 revert 조건
  (`extra_area_post>pre+1e-6 or area_cov_post<pre-1e-3`) 에 **`|Σvol|_post` < `|Σvol|_pre`·0.999**
  추가 → 표면(#1 불변식)·coverage·부피 3중 보호, 위반 시 pre 로 전량 revert.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 170 python3 -m pytest tests/test_native_tet_thin_sliver.py -q
timeout 175 python3 -m pytest tests/test_native_tet_solid_volume.py -q
```
신규 `tests/test_native_tet_thin_sliver.py`: `generate_native_tet` 직접호출(P4C=0,
target_cells=2000) 로 naca0012 메쉬 생성 → polyMesh 파싱 → `degen(|det|/6<1e-9)` 카운트.

## 합격 기준 (validator 평가)

- **naca degen 17 → 0** (게이트: `n_degen ≤ 2`; 실측 목표 0).
- **#1 표면보존 불변**: naca `area_ratio` = 1.000 ± 0.002 유지, plane_area_coverage 비감소.
- **부피 불변**: `Σ|vol|/input_vol` = 1.004 ± 0.02 유지, `negative_volumes = 0`.
- **skew 개선 요구 안 함**(별개 축·다음 카드) — 이 카드로 naca verdict 는 여전히 FAIL(skew) —
  **정직 기준**: correctness(degen) win 이지 verdict flip 아님.
- 회귀: `test_native_tet_solid_volume.py` 4/4 PASS. cube/cylinder/sphere/dual_torus/
  perforated/sharp_ridge **회귀 절대 금지**(degenerate_removal 은 이미 이 형상들에 발동 중 —
  Phase1b 는 잔존 degen 있을 때만 추가 동작, guard revert 로 무해 보장). bench 시간 ≤ 기존 +5%.

## 카드 시퀀스 위치

- "얇은/샤프 피처 슬리버" 클러스터 착수 **1/2 (naca)**. 이 카드 = **degen(내부 슬리버) 축**.
- **다음 카드 THINSLIVER2 (naca)**: 경계 슬리버 skew 58.8→게이트 — surface-lock 하 **내부 apex
  reposition(boundary-skew-directed smoothing)**. worst 4셀 실측 n_surf_v 3/4·interior apex·
  nd 1.7e-4 → apex 를 face-centroid 법선 위로 밀어 nd↑·tangential↓ (surface 무접촉). 이게 FAIL gate.
- **별도 로드맵(이 시퀀스 아님)**: very_thin_disk(all-surface vol=0 wedge) + needle(미소단면) +
  dual_torus(FSL4) 공통 **Garimella near-wall 내부점 삽입** — 구조적 known-limit, 다카드 재설계.
