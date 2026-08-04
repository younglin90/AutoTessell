---
type: changelog
status: append-only
updated: 2026-07-26
stability: contract
source_paths: [docs/llm-wiki]
tags: [wiki-log]
---

# 위키 작업 기록

## 2026-07-26 — ingest — 저장소 최초 합성

- 프로젝트 규칙, 공통 스키마, 5단계 orchestrator, tier 선택/생성, native tet·hex·poly, native tri·quad 표면 작업, 경계층, 평가/fidelity, 강건 술어, UI/API, 빌드, 테스트, 로드맵, 문헌 evidence matrix를 조사했다.
- 대규모 미커밋 WIP가 존재하므로 작업트리 관찰과 커밋·계획·실측 주장을 분리했다.
- MOC, 소스 지도, 유지보수 스키마, 불일치 원장, 세부 서브시스템 문서를 만들었다.

## 2026-07-26 — rewrite — 전체 한국어화

- 코드 식별자·경로·수식은 유지하고, 본문·제목·표·유지보수 지침을 한국어로 바꿨다.
- 외부 설계 참고: Karpathy, “LLM Wiki,” gist `442a6bf555914893e9891c11519de94f`.

## 2026-07-26 — literature-read — 다음 개선 카드의 문헌 근거 정리

- Dassi et al. 2017과 MFRC 2021 공개 원문을 읽고, 내부-only smoothing/가역 flip/cavity transaction의 조건을 `native_tet` 다음 카드에 연결했다.
- hex 전이 셀, poly concave split, quad messy grid map 관련 논문은 출판사 초록 또는 공개 초록까지 확인한 상태와 FULL_READ 대기 상태를 분리했다.
- [[2026-07-26 문헌 읽기와 다음 개선 카드]]에 네 엔진의 다음 진단 카드와 다운로드가 필요한 DOI를 기록했다.

## 2026-07-26 — measurement — 문헌 기반 다음 카드 진단

- `HEX-TRANSITION-DIAG1`: 기존 fixture metadata 부족으로 `BLOCKED`; production route 변경 없음.
- `TET-LAZY-2`: 품질은 개선됐지만 signed-volume orientation 혼합으로 rollback.
- `POLY-CONCAVE-SPLIT1`: conical geometry candidate는 가능하지만 non-manifold fan과 synthetic provenance 때문에 승인 불가.
- `QUAD-MESSY-GRID-TOL1`: bracket half-index 손실은 0이지만 unresolved 18개가 남음; tolerance는 아직 정의하지 않음.
- 새 진단과 관련 회귀 검증은 `21 passed in 24.09s`; 이번 라운드에는 production 메커니즘을 추가하지 않았다.

## 2026-07-26 — literature-ingest — 사용자 제공 hex 논문 3편 보관·전문 판독

- `xu2018.pdf`, `wei2015.pdf`, `1-s2.0-S0010448524001520-main.pdf`를 `docs/references/papers/source/pdf/52_...`부터 `54_...`까지 보관했다. 원본과 보관본의 SHA-256을 대조해 세 파일 모두 byte-identical임을 확인했다.
- `10.1016/j.cag.2017.07.002`(Xu et al. 2017), `10.1016/j.cad.2014.09.003`(Wei et al. 2015), `10.1016/j.cad.2024.103825`(Zheng et al. 2025)를 전 페이지 읽고 제목·초록·알고리즘·도식·실험·한계를 확인했다.
- Xu의 local-region 저장/rollback, Wei의 현재 iteration boundary/feature constraint, Zheng의 feature-aware sheet collapse/inflation을 native_hex의 다음 진단 순서에 반영했다. generic ECR/sheet repair 구현은 아직 열지 않았다.

## 2026-07-26 — measurement — HEX-TRANSITION-PROVENANCE-DIAG1

- native_hex octree builder에 report-only provenance census를 추가하고, generic writer 경계에서 builder metadata가 전달되지 않는 지점을 계측했다.
- cylinder/sphere/gear의 `max_cells=8000` fine pre-BL 출력은 각각 builder→writer `6320→6320`, `4224→4224`, `4920→4914`였다. 세 형상 모두 builder target level은 4뿐이고 transition cell/face는 `0/0`으로 측정됐다.
- gear에서 writer가 6개 cell을 기존 degenerate-cell filter로 제거한 것은 별도 감사 카드로 분리했다. authoritative lineage/template/hanging-node/patch provenance는 여전히 최종 cache에 없다.
- 관련 native_hex 테스트 `55 passed`, 신규 provenance 테스트 `4 passed`; 기본 경로와 품질 게이트는 변경하지 않았고 커밋하지 않았다.

## 2026-07-26 — measurement — HEX-OCT-ADAPTIVE-TRANSITION-REALIZATION-DIAG1

- 4×4×4 synthetic mixed-level 입력(`{1: 8, 2: 56}`)을 opt-in flag로 실행해 level 1 cell 1개, level 2 cell 56개, coarse→fine interface face 12개를 확인했다.
- forced-ON 실제 형상 통합은 curved-wall/skew/fine-volume/adaptive-budget 관련 gate 5개를 깨서 기본 ON 승격을 거부했다. `AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION`은 default-OFF로 격리했다.
- 기본 native_hex 회귀는 `57 passed`로 복구됐다. 다음 카드는 `HEX-OCT-TRANSITION-QUALITY-1`이다.

## 2026-07-26 — measurement — HEX-OCT-TRANSITION-QUALITY-1

- opt-in quality census를 추가했다. signed/orientation-free volume, warpage,
  canonical skew, boundary set/area, face incidence, writer drop을 report-only로
  측정한다.
- synthetic mixed-level은 transition cell 1개, transition face 3개,
  interface face 12개, boundary face 87개를 재현했다.
- 실제 cylinder/sphere/gear는 각각 transition `173/229`, `63/111`, `11/36`;
  builder→writer `2463→2445`, `2684→2684`, `4542→4534`였다. cylinder/gear는
  boundary set이 변했고 gear는 builder signed-volume 음수 5개를 보였다.
- 결론은 **측정 완료·production 승격 기각**이다. mixed-level flag는 계속
  default-OFF이며 다음은 writer-boundary/face-winding contract 분리다.
- targeted `3 passed`, native_hex 전체 파일군 `113 passed`; 커밋/스테이징 없음.

## 2026-07-26 — measurement — HEX-OCT-TRANSITION-WRITER-1

- generic writer의 공개 degenerate-face 조건을 report-only로 재현했다.
- cylinder 예측/실제 drop `18/18`, 노출 내부면/실제 boundary 추가 `60/60`;
  gear는 `8/8`, `23/23`으로 정확히 일치했다.
- 첫 사례는 snap 후 두 쌍의 정점이 겹쳐 면적 0이 된 cylinder cell 145 face 5와
  gear cell 329 face 3이다.
- 결론은 **writer 무죄**이며, boundary 변경은 upstream snap 이후 cell drop의
  owner 재분류다. 다음은 snap/wall-fit/skew-relax 단계 이분 계측이다.

## 2026-07-26 — measurement — HEX-OCT-WALLFIT-FACE-AREA-GUARD-1

- wall-fit candidate에 face-area floor를 검사하는 opt-in guard를 추가했다.
- mixed-level cylinder/gear에서 writer drop `18→0`, `8→0`, boundary set 일치가
  확인됐다.
- transition skew/warpage와 gear signed-volume 음수는 남아 있어 partial result로
  판정했다. 기본 OFF 유지, 다음은 transition-aware wall-fit 품질 조건이다.

## 2026-07-26 — measurement — HEX-TRANS-2

- canonical boundary skew `>=2.0`와 transition owner/vertex adjacency를
  교차표로 측정했다. 실제 mixed-level fine pre-BL cylinder/sphere/gear에서
  wall-fit 이후 나쁜 면은 `550/960/135`개였다.
- transition-owner 겹침은 `36/550`, `0/960`, `10/135`; 넓은 transition-vertex
  proxy 겹침은 `168/550`, `0/960`, `22/135`였다. snap 전과 iterative snap 후에는
  세 형상 모두 0개였다.
- 전이 셀 국소 집중 가설은 **measured, falsified**로 기록했다. transition-only
  repair를 열지 않고, 다음은 wall-fit 후보 단위의 report-only 품질 delta
  계측이다.

## 2026-07-26 — measurement — HEX-WALLFIT-CANDIDATE-QUALITY-1

- `_wall_fit_snap` 후보별 before/trial/after snapshot을 opt-in으로 연결했다.
  기존 accept/reject, permanent gate, mesh connectivity는 바꾸지 않았다.
- `max_cells=500`에서 applied regression은 cylinder `128/128`, sphere `104/128`,
  gear `186/271`; boundary key는 유지됐지만 area 변화는 `128/128`, `128/128`,
  `238/271`이었다.
- cylinder `max_cells=2000`에서는 `560` 후보 중 `481` applied regression,
  `521` area changes를 확인했다. 최대 skew outlier는 near-zero denominator
  때문에 gate 근거로 쓰지 않는다.
- 결론은 일반 wall-fit candidate 품질 문제 관측이다. 다음은 분모/부호
  계약을 닫는 `HEX-WALLFIT-QUALITY-TRANSACTION-1`이다.

## 2026-07-26 — measurement — HEX-WALLFIT-QUALITY-TRANSACTION-1 전제

- checker와 후보 진단의 skew 분모는 동일하다. 작은 cylinder에서 최소 trial
  `|normal_dist|=0.0149533`, near-zero 0인데 applied skew Δ `+1.5313`이어서
  작은 run의 품질 회귀는 실제 metric 변화로 기록했다.
- 큰 run의 `2.7756e13`은 분모 민감성 outlier로 분리했다.
- 실제 no-inversion은 native face-sign reference 보존이고, centroid-fan
  signed-volume은 winding 의존 report-only 값이다. transaction 구현 전 기존
  sign contract와 상대 품질/area tolerance를 함께 정의한다.

## 2026-07-26 — measurement — HEX-WALLFIT-QUALITY-TRANSACTION-1

- strict max 기준 비회귀 후보는 cylinder `0/128`, sphere `24/128`, gear
  `85/271`; p95 기준은 `0/128`, `0/128`, `66/271`이었다.
- quality-only rollback은 cylinder의 모든 후보를 막으므로 너무 보수적이다.
  boundary key는 전부 보존됐다.
- 다음은 후보별 surface-distance/wall-deviation 개선과 local quality delta의
  trade-off 교차 측정이다. 아직 transaction 동작은 켜지 않았다.

## 2026-07-26 — measurement — wall-fit surface-distance trade-off

- 후보별 `d_before - d_after`를 계측했다. 거리 개선 후보는 cylinder `128`,
  sphere `128`, gear `253`개였다.
- 그중 quality regression은 `128`, `104`, `186`개였다. cylinder에서는 전부
  겹쳤으므로 quality-only rollback은 부적합하다.
- 다음은 대표 mesh 크기에서 최종 wall deviation과 local quality delta를 함께
  비교하는 진단이며, transaction은 아직 OFF다.

## 2026-07-26 — measurement — HEX-WALLFIT-FINAL-GATE-CROSS1

- 후보 snapshot과 최종 checker 결과를 같은 report-only 실행에서 연결했다.
- `max_cells=500`에서는 cylinder/sphere/gear의 final boundary skew가
  `2.73027/2.85183/1.38997`, negative volume은 모두 `0`이었다. 전체
  evaluator verdict는 다른 조건 때문에 FAIL로 남았다.
- `max_cells=2000` cylinder에서는 후보 `560`, 거리 개선 `537`, local 품질
  회귀 동반 `481`, combined 비회귀 `49`, final boundary skew `125.761`,
  negative volume `0`이었다.
- 결론: final-gate 연결은 확인했지만 transition-only 원인은 아니다. 품질-only
  rollback은 surface fitting 이득을 대부분 제거하므로 구현하지 않고, 대규모
  wall-fit scale/root-cause 카드를 다음 우선 작업으로 연다.

## 2026-07-26 — measurement — HEX-OCT-MIXED-LEVEL-ROOTCAUSE-1

- 2,000셀 cylinder에서 mixed-level × wall-fit을 분리했다. mixed OFF/wall-fit
  ON은 `1781 hex`, boundary skew `3.20865`; mixed ON/wall-fit OFF는
  `1363 hex + 22 other`, skew `1.16279`지만 area deviation `93.4942%`; 둘 다
  ON이면 skew `125.761`이었다.
- mixed-level builder의 `before_snap`부터 transition `22`, boundary face
  `1479`, report-only signed-negative `2`가 존재했다.
- `_build_nlevel_cells`는 coarse face만 sub-quad로 나누고 fine 이웃 쪽
  대응 face/template을 만들지 않는다. 따라서 writer가 아니라 비정합
  transition realization이 1차 원인, wall-fit은 증폭기다.
- 결론: `HEX-OCT-TRANSITION-TEMPLATE-1`을 별도 카드로 열고, mixed-level은
  기본 OFF 유지한다.

## 2026-07-26 — correction — HEX-OCT-TRANSITION-WINDING-1

- synthetic face-key 감사 결과 coarse sub-quad와 fine quad는 2:1에서 서로
  대응했다. 실제 결함은 `_sub_quads_on_face`의 cyclic winding이
  `_HEX_FACES`와 반대였던 것이다.
- wrapper에서 sub-quad를 한 번 reverse한 뒤 synthetic signed-negative `1→0`,
  face incidence `{1:87,2:132}` 유지, targeted test `4 passed`.
- real mixed cylinder builder signed-negative `2→0`, wall-fit OFF writer drop
  `0` 확인. 다만 area deviation `93.4942%`와 wall-fit ON skew `125.761`는
  남아 broader mixed-level quality 카드는 계속 열린다.

## 2026-07-26 — measurement — HEX-WALLFIT-SURFACE-TRADEOFF-1

- wall-fit stage surface distance 평균은 cylinder `0.027915→0.014200`, sphere
  `0.078905→0.046371`, gear `0.026542→0.001380`으로 감소했다.
- gear p95는 `0.096807→0.005295`, max는 `0.108621→0.019445`로 개선됐다.
- 표면 품질 이득과 local skew/warpage 회귀가 공존하므로 quality-only rollback을
  열지 않는다. 다음은 기존 최종 wall_dev/skew gate와 후보 delta를 연결하는
  검증이다.

## 2026-07-27 — implementation — HEX-OCT-MIXED-LEVEL-COVERAGE-1

- `_build_nlevel_cells`의 실제 결함을 두 건으로 확정했다. finer leaf가
  `covered` 블록 원점만 소비해 같은 블록의 level-3 셀을 고립시키는 문제와,
  coarse face 이웃 level을 한 인덱스만 읽어 fine 이웃을 놓치는 문제다.
- mixed target block을 finest로 사전 승격하고, 잔여 partial covered block을
  안전하게 finest로 채우며, coarse-face의 인접 slab 전체에서 최대 level을
  검사하도록 수정했다. surface 위치·기본 mixed-level flag·permanent gate는
  변경하지 않았다.
- 합성 transition 회귀는 `5 passed`; 실제 builder의 내부처럼 보이는
  boundary face는 `155→0`이 됐다.
- 2,000-cell cylinder 최종 결과는 `cells 1655`, `PASS_WITH_WARNINGS`,
  boundary skew `125.761→3.20865134`, surface area deviation
  `87.09%→0.263700907%`, negative volume `0`, writer drop `0`, boundary
  face-set equal `True`, boundary area `4.68488421` 대 입력 `4.69727095`다.
- native_hex 전체 회귀는 `118 passed`; 직접 반복 builder의 points/cell faces도
  byte-level 비교에서 동일했다. 남은 `3.20865134`와 85 bad-face는
  `HEX-OCT-SCALE-QUALITY-1`로 별도 보류한다.

## 2026-07-27 — measurement — HEX-OCT-SCALE-QUALITY-1

- coverage fix 직후 builder bad-face는 `0`건이었지만 `_wall_fit_snap` 후
  `80`건, 전체 2,000-cell pipeline에서는 `85`건이 생겼다. transition
  owner/vertex-adjacent bad-face는 모두 `0`건이라 transition 결함이 아니라
  일반 boundary vertex wall-fit 품질 효과로 좁혔다.
- wall-fit ON: `1655 cells`, boundary skew `3.20865134`, area deviation
  `0.263700907%`; OFF: skew `0.974373881`, area deviation `15.3787224%`.
- 후보 `496`건 모두 surface distance는 개선됐지만 `376`건이 local quality
  회귀를 동반했고, strict 비회귀 `120`, combined p95 비회귀 `104`였다.
  mean distance `0.0167231→0.0007091`, p95 `0.0490482→0.00376990`.
- 단순 quality rollback은 surface 계약과 충돌하므로 구현하지 않았다. 영구
  skew gate는 유지하고 `HEX-OCT-SCALE-QUALITY-1`을 문헌 근거의
  surface-constrained Pareto repair 카드로 남긴다.

## 2026-07-27 — native_tet TET-CDT-SCALE-PERF-1

- dual_torus fine native-tet는 CDT에서 480초 내 종료되지 않았다. 세 번의
  zero-insert plateau round가 약 102/107/112초씩 걸렸고 plateau exit 뒤에도
  edge-flip/BSP가 진행 중이었다.
- 고정 `/tmp/cdt_state_dump.npz`에서 `check_edge_recovery`는 0.081초,
  one-cycle CDT는 15.15초, 그중 targeted edge flip은 13.35초였다.
- `AUTO_TESSELL_TET_EDGE_FLIP_INDEX=1`에 stable row/vertex/tet/edge index를
  추가했다. legacy와 결과 배열·통계가 byte-identical했고 targeted flip은
  12.72→1.34초, one-cycle CDT는 15.15→3.79초였다. focused 3 tests passed.
- 새 lane은 기본 OFF다. fine end-to-end와 permanent gate를 통과한 뒤에만
  기본 활성화를 재검토한다.

## 2026-07-27 — native_tet BSP performance falsification

- 고정 상태에서 scalar BSP proposal은 59.537초, batch proposal은 1.503초로
  빨랐지만 두 제안 결과는 동일하지 않았다.
- 실제 fine에서 indexed edge flip + batch BSP + 500점 cap을 실행하자
  downstream pass까지 약 246초에 도달했지만 `cdt_face_ratio=0.452`,
  `n_val_flipped=4621`, `n_val_degen=6`, grade B로 품질/정합성 게이트를
  훼손했다. retry 중 timeout도 발생했다.
- 결론: BSP batch는 기본 경로로 승격하지 않는다. scalar 기본 경로를
  보존하고, surface face conformity와 양의 orientation을 먼저 보장하는
  correctness 카드로 재분류했다.

## 2026-07-27 — native_tri TRI-CURV-SIZE1

- 기존 operator-loop에 Frey/Dunyach 스칼라 sizing이 이미 구현되어 있음을
  확인하고 직접 측정했다.
- `epsilon=0.01`: cube target length `0.25/0.25/0.25`, sphere
  `0.1608498/0.1722745/0.1724617` (min/median/max).
- smoothing OFF 한 라운드 후 cube/sphere 모두 edge incidence 2와
  watertight를 유지했고, accepted operation은 각각 55/0이었다.
- `tests/test_native_tri*.py` 21 passed. scalar sizing은 유지하고, 다음은
  anisotropic metric intersection 및 BL metric handoff로 이동한다.

## 2026-07-27 — native_tri metric primitive

- tri 전용 `core/preprocessor/native_tri/metric.py`에 finite/SPD audit,
  tangent/normal BL source metric, endpoint metric edge length, generalized-
  eigenvalue Loewner intersection을 추가했다.
- 기존 operator-loop에는 연결하지 않았다. 동일 metric idempotence, 회전
  covariance, BL 고유값, edge length analytic 검증을 추가했고 full
  `tests/test_native_tri*.py`는 `29 passed`다.
- 다음 카드는 cube/sphere/cylinder/늘어진 BL 합성 fixture에서 isotropic·
  curvature·BL metric을 직접 비교하는 측정이며, 그 전에는 operator-loop
  동작을 바꾸지 않는다.
- 네 fixture 측정에서 cube/sphere/cylinder의 SPD·길이 계산은 유효했지만,
  cube BL proxy의 normal length 0.1을 표면 edge metric에 그대로 넣으면
  sharp corner normal 혼합으로 edge length가 32.8–65.1까지 폭증했다.
  따라서 tangent-only surface metric과 normal BL placement를 분리하는
  다음 카드로 좁혔고, full 3-D BL proxy는 operator-loop에 연결하지 않는다.
- feature-aware audit에서는 sphere가 `0` feature vertex / `480` evaluable
  edge, cube가 `8` feature vertex / `18` edge reject, capped cylinder가
  `64` feature vertex / `192` edge reject로 분류됐다. feature 정점은
  평활화하거나 이동하지 않고 명시적으로 거부한다.

## 2026-07-27 — native_tet BSP correctness guard

- 고정 상태의 BSP/B-W 후보가 점을 추가하면서 누락 면을 `1032→1076`으로
  악화시키는 사례를 확인했다. 따라서 점 추가 자체를 성공으로 간주하지
  않고, 후보 전후 누락 면 수가 줄고 물리적 boundary 면적이 보존될 때만
  채택하도록 했다.
- B-W 경로와 full re-Delaunay fallback 모두 후보 전체(후속 snap 포함)를
  거부 시 원상복구한다. 기본 scalar 경로와 opt-in batch 경로의 분리는
  유지했다.
- 후보 전후 scale-relative non-positive/degenerate tet 수도 비교해 증가하면
  추가로 거부한다. BSP 후보 수락 조건은 missing-face 감소, boundary area
  불변, non-positive tet 비증가의 세 가지다.
- 문법 검사 및 Phase-F/CDT/dual-torus focused 회귀는 `12 passed`.
- 카드 상태: `TET-BSP-RECOVERY-CORRECTNESS-1` 구현 단계지만 fine 재실행·
  영구 게이트·결정론 검증 전에는 닫지 않는다.
- indexed edge flip + batch BSP + 500점 cap의 bounded fine replay는 480초
  제한에서 timeout(러너 정리 포함 504.7초)이었다. 최종 품질 verdict가 없어
default 전환 근거로 사용하지 않는다.

## 2026-07-27 — native_tet BSP fixed-state timing split

- `/tmp/cdt_state_dump.npz`에서 scalar BSP는 `60.1438 s`, batch BSP는
  `1.4736 s`, Bowyer–Watson은 `13.3494 s`였다. batch가 제안한 500점 중
  B-W가 실제 삽입한 점은 139개였다.
- 후보 전후 missing face는 `1032→1076`, boundary area는 동일했고,
  non-positive/degenerate tet는 `8964→8587`이었다. 면 회복이 악화되므로
  correctness guard가 후보 전체를 복원하는 것이 정답이다.
- 따라서 B-W adjacency 재구축 최적화는 아직 production 카드로 열지 않고,
  먼저 실제 missing-face 감소와 결정론을 보이는 후보를 요구한다.

## 2026-07-27 — native_tet TET-CDT-EDGE-FACE-MONOTONE-1 diagnostic

- fixed state의 indexed targeted 2-3 edge flip 200회는 missing edge
  `604→452`, missing face `1032→779`를 만들고 boundary key/area를 보존했다.
- 그러나 scale-relative non-positive/degenerate count는 `8964→9071`로
  증가했다. 후속 검사에서 이는 음수 orientation 107건 증가였고 퇴화체는
  `131→131`로 동일했다. 모든 missing face는 세 surface vertex가 이미 존재했지만,
  `176`개는 input edge 1개, `856`개는 2개만 tet edge로 존재했다.
- face recovery는 edge recovery의 monotone candidate transaction 이후에만
  평가해야 한다. 이번 라운드에는 `AUTO_TESSELL_TET_EDGE_FLIP_GUARD=1`인
  opt-in 국소 guard를 구현했다. valid bipyramid flip은 통과했고 coplanar
  후보는 rollback되었으며, fixed state 200회에서 boundary key/area,
  missing face `1032→779`가 유지되었다. sorted candidate order를 두 번
  반복해 edge `604→455`, guard reject 1건, `17869×4` tetra 배열의
  byte-identical 결과를 얻었고 boundary `1320→1320`, 면적
  `103.399255187455→103.399255187455`였다. fine replay·영구 게이트·전체
  파이프라인 byte identity 전까지 기본값은 OFF다.

## 2026-07-27 — native_hex HEX-WALLFIT-PARETO-1

- mixed-level 수정 뒤 남은 문제는 transition owner가 아니라 `_wall_fit_snap`
  이후의 일반 boundary vertex 품질 trade-off다. 대표 cylinder에서 wall-fit
  ON은 skew `3.20865134`, area deviation `0.263700907%`, bad face `85`이고,
  OFF는 skew `0.974373881`, area deviation `15.3787224%`, bad face `0`이다.
- 문헌 카드를 `docs/references/literature/native_hex/`
  `wallfit_pareto_quality_repair_2026-07-27.md`에 추가했다. HexOpt은 가장
  가까운 FULL_READ 후보지만 corner/edge/face 점의 표면 위 tangential slide를
  허용하므로 현재 frozen surface lane의 drop-in 구현으로 취급하지 않는다.
- 다음은 cylinder/sphere/gear/bracket 후보별 Pareto 측정이다. surface
  face-key·area·signed-volume·wall-dev·skew·결정론 gate는 그대로 유지하며,
  문헌 전문 확인 전에는 코드 수락 규칙을 변경하지 않는다.

- first Pareto run (cylinder, `max_cells=2000`)은 후보 `350`, 비지배 frontier
  `117`, boundary-key 변화 `0`, 음수체 증가 `0`, strict/p95/combined 비회귀
  각 `16`을 기록했다. 표면거리 평균/p95는
  `0.0120959802/0.0380725043→0.0005450396/0.0024877153`으로 줄었지만,
  최종 skew는 `3.20865134`로 여전히 3.0 gate를 넘는다. Pareto 존재는
  확인했지만 생산 수락 규칙으로 승격하지 않는다.

- Pareto 측정을 sphere/gear/bracket까지 확장했다. 결과는 cylinder
  `1655/3.20865/350/117/16·16·16`, sphere
  `1057/14.73845/404/157/36·36·36`, gear
  `1296/27.08143/531/67/117·108·99`, bracket
  `538/19332.7157/342/41/133·118·115` (각각 cells/skew/candidates/
  frontier/strict·p95·combined)이다. 네 형상 모두 final negative volume와
  boundary-key 변화는 0이지만 skew 3.0 gate를 넘고 frontier가 형상마다
  달라, global threshold와 shape-adaptive dispatch 모두 보류한다.

## 2026-07-27 — native_tet BETA2832 multi-body coverage

- component filter가 dual-torus의 두 body를 모두 보존했다: `2 components`,
  `2 kept`, `0 dropped`, `area_ratio=1.0094878`, `vol_ratio=1.0097687`,
  `11071 cells`, `degen=0`, `neg_vol=0`, `129.1 s`.
- cube/cylinder smoke와 solid-volume/dual-torus 회귀는 `7 passed, 1 xfailed`.
  dual-torus `max_skew=2.21e6`와 낮은 CDT 회복률은 BETA2834로 분리했다.

## 2026-07-27 — native_tet BETA2834 edge-recovery diagnostic

- production harness는 `enable_edge_recovery=False`라 indexed env flag만으로는
  실제 결과가 바뀌지 않았다(`cdt_ratio=.005`, `max_skew=2.21e6`).
- direct opt-in edge recovery는 `cdt_ratio .881→.925`, face ratio
  `.707→.800`, mean q `.1482→.1524`를 얻었지만 plane coverage는
  `.897→.880`, runtime은 `6.73→14.24s`였다. surface-conformity/area
  transaction 없이 기본 승격하지 않는다.

- stage snapshot: midpoint/B-W 50점 삽입 후 missing edge는 `682→682`였고,
  flip 포함 전체 edge lane은 boundary face `1352→1352`, area
  `103.399255187455` 동일로 보존됐다. plane coverage 저하는 boundary 파괴가
  아닌 후속 recovery/BSP/quality 상호작용으로 분리했다.

## 2026-07-27 — native_tet edge recovery candidate-order determinism

- canonicalization 전 fixed state의 raw/sorted/reversed 후보 순서는 각각
  `152/452`, `149/455`, `144/460` recovered/missing 결과를 만들었다.
- edge key를 canonicalize하고 후보를 정렬하도록 수정했다. 이후 세 순서가
  모두 `149/455`, guard reject 1건, 동일 SHA-256
  `a4890384ba9752aea224a9f35a255922d475e832c75923591ce16f4b3723156f`로
  수렴했다.
- two-bipyramid 순서 불변 회귀 테스트와 CDT 집중 테스트는 통과했다.
  전체 집중 게이트는 `19 passed, 2 xfailed`이며, full-pipeline fine replay와
  기본값 승격은 남아 있다.

## 2026-07-27 — report-only revalidation

- native_hex의 census/ScoreCHE/β-margin/transition/wall-fit 계열은
  `16 passed`, 핵심 native_hex 회귀 묶음은 `66 passed`였다. cube는
  `100% hex`, `score_che=1.0`, one cluster, volume `1.0`으로 유지됐다.
- 양의 체적을 가진 thin-corner 합성 셀에서 corner Jacobian `0.01`과
  진단 `beta=0.1`을 사용해 β-margin이 실패하는 것을 고정했다. 이는
  report-only 판별력 검증이며, 음수 체적 gate·mesh 생성·기본 flag는
  변경하지 않았다.
- native_tri 전체 테스트도 재확인해 `37 passed`를 얻었다. native_poly의
  fixed-primal sphere 최적화 결과는 앞선 두 반복에서 `669 cells / 5474
  points / invalid 0`과 동일 digest를 유지한다.

## 2026-07-27 — native_poly MMS prerequisite and native_tet fine A/B

- `POLY-FVERR-RANDPERT1` 선행조건으로 report-only cell-centred FV MMS를
  추가했다. 정규 격자는 L2 차수 `2.0, 2.0`, 25% random perturbation의
  uncorrected two-point kernel은 `0.7658, 0.6690`이었다.
- 실제 native_poly 출력에서는 sphere가 `63.8878° / 0.235625 / L2
  0.559198`으로 계산됐고, cube는 non-positive internal coefficient,
  cylinder는 zero-area face로 명시적 REJECT됐다. solver 실패를 숫자로
  위장하지 않았다.
- native_tet full-fine direct A/B(`target_cells=15000`)는 OFF/ON 모두
  final `cdt .80518 / face .46509 / plane .68116 / degen 6`으로 수렴했다.
  ON은 `29.16→36.93s`로 느려졌고, 중간 edge recovery 개선도 downstream에서
  사라졌다. 기본 경로 승격은 보류한다.

## 2026-07-27 — MMS correction falsified on native-poly output

- 합성 Cartesian hex 격자에서 report-only deferred non-orthogonal correction을
  추가했다. 25% 결정론적 내부 섭동에서 L2 수렴 차수는 uncorrected
  `0.7658, 0.6690`에서 corrected `2.0094, 2.1250`으로 회복됐다.
- 그러나 실제 native-poly sphere(`669 cells / 5474 points`)에서는 corrected
  L2가 `0.559198→1707.868144`로 폭증했다. 따라서 보정 레인은 생산 경로로
  승격하지 않고, solver-consistent face-flux 구현과 cube/cylinder mesh
  prerequisite 수리가 선행되어야 한다.
- `tests/test_native_poly_fv_mms.py`: `3 passed`; native_tet edge-recovery/CDT
  집중 게이트: `6 passed`. 두 트랙 모두 기본 동작과 게이트는 변경하지 않았다.

## 2026-07-27 — native-poly FV prerequisite repeatability audit

- 같은 `seed_density=6`의 기본 cylinder 실행 두 번이 서로 달랐다:
  `1619 cells/11053 points` 대 `1618 cells/11110 points`; 0면적 face와 음의
  내부 계수 개수도 달랐다. 기본 환경은 수렴 측정 프로토콜로 부적합하다.
- `AUTO_TESSELL_P4C_PYTETWILD=0`으로 순수 native 경로를 고정하면 두 반복이
  `73 cells/596 points`로 동일해지지만 내부 two-point 계수 20개가 음수였다.
  cube도 `15/78`, 0면적 face 5개, 음의 계수 8개였고 native dual 진단은
  cube/cylinder에서 각각 `7/51`, `71/553` invalid cell/subtet을 보고했다.
- 결론: FV 보정식이나 게이트 변경보다 upstream dual 유효성·경로 결정론을
  먼저 닫아야 한다. 비직교 보정은 계속 report-only로 유지한다.

## 2026-07-27 — native-poly dual invalidity path isolation

- ConvexHull path A와 topology-ring path B를 실행 시 분리해도 fixed-native
  invalidity가 동일했다: cube `7/51`, cylinder `71/541` invalid
  cells/subtets. 따라서 route dispatch와 Garimella point placement가 단독
  원인은 아니다.
- cube boundary cell 0에서 internal 6/5-gon의 음수 star subtet과 zero-area
  boundary cap `[43,67,42]`를 확인했다. 원인은 FV 보정식이 아니라 dual
  face/coplanar-cap construction이다. invalid face를 몰래 삭제하거나
  STAR-VALID gate를 완화하지 않고 transactional repair 카드로 분리한다.
- fixed-native face census에서 cube internal `24/62`가 warped, zero-area
  internal `2`와 boundary cap `3`을 보였다. cylinder는 internal `220/352`가
  warped, boundary warped cap `9`이었다(max relative warpage `0.45028`와
  `0.62611`). 단순 face 삭제가 아닌 owner/neighbour·area·patch·결정론을
  보존하는 transactional face repair가 다음 카드다.

- 관련 문헌을 다시 대조했다. Nishikawa 2022는 non-planar face correction과
  consistent control volume을 요구하고, Bonaventura--Della Rocca 2018은
  corrected two-point scheme의 mesh regularity/coercivity 조건을 둔다.
  Walton--Hassan--Morgan 2017은 Delaunay/Voronoi well-centeredness를 dual
  생성 목표로 둔다. 따라서 solver 보정이 아니라 upstream dual repair가
  다음 우선순위다.

## 2026-07-27 — native_tet BSP bounded replay revalidation

- P4C off·indexed order·boundary guard 조건의 `target_cells=600` 재실행이
  이전 결과를 재현했다. OFF는 `12219/2855`, edge/face `0.89665/0.73291`,
  plane/area `0.93168/0.94605`; ON은 `12616/2903`, `0.93229/0.81763`,
  `0.91149/0.93789`였다.
- wall time은 `26.53→34.15 s`로 ON이 느렸고, full-fine `480 s` replay는
  여전히 timeout이다. 따라서 edge/index/guard lane은 기본 OFF이며, fine
  acceptance 카드는 미종료로 유지한다.

## 2026-07-27 — native-poly dual face candidate wave

- `POLY-DUAL-FACE-REPAIR1`에서 simplex facetization은 sphere invalid를
  `2/14→0/0`으로 보이게 했지만 boundary face가 `3842→26570`으로
  폭증했고, cube/cylinder도 각각 `27→322`, `212→2588` boundary face가
  되어 기각했다. source-triangle cap 후보는 cube `7/51→2/30`, cylinder
  `71/553→70/440`으로 일부 개선했지만 internal face 문제를 남기고
  sphere를 개선하지 못해 제거했다.
- 현재 `dual.py`는 exact `ConvexHull`을 먼저 시도하고, 진짜 Qhull
  퇴화 때만 기존 `QJ` fallback을 쓴다. fixed-native 진단은 cube `2/30`,
  cylinder `70/440`, sphere `0/0`이었고 focused native-poly `22 passed`다.
  이 수정은 QJ로 인한 불필요한 face warpage를 줄이는 최소 안전 변경이지,
  dual face repair 카드의 완료가 아니다.
- cube/cylinder의 internal warped face(`24/62`, `220/352`)와 FV
  prerequisite failure는 남아 있다. 다음 카드는 owner/neighbour pairing과
  boundary area를 보존하는 topology-ring 내부면의 transactional planar
  construction이며, face 삭제나 STAR-VALID 완화는 금지한다.

- topology-ring completeness audit: internal rings complete/closed는 cube
  `42/42`, cylinder `156/156`, sphere `1331/1331`; 누락과 projected
  self-intersection은 0건이었다. 따라서 ring-order가 주범이라는 가설은
  기각됐다. best-fit plane 최대 편차는 `0.07581/0.20622/0.25778`이고,
  projected concavity는 `0/14/38`이었다.
- fixed-native primal circumcenter audit: well-centered tet 비율은 cube
  `20/40`, cylinder `8/212`, sphere `196/1913`이었다. raw circumcenter
  dual은 invalid candidate `14/136`, `68/932`, `449/3782`로 centroid보다
  나빠졌다. 다음 poly 카드 이름은 `POLY-DUAL-WELL-CENTER1`이며, upstream
  weighted/well-centered lane을 transactional fallback과 함께 측정한다.

## 2026-07-27 — native-poly well-centered bounded move

- 문헌 후속은 boundary vertex를 고정하고 interior vertex만 움직이는
  well-centered 최적화(`arXiv:0802.2108`)와 deterministic weighted-Delaunay
  품질 생성(`10.1137/S0097539703418808`) 방향으로 좁혔다.
- standalone local move 진단은 boundary displacement `0`으로 유지하면서
  well-centered 비율을 cube `20/40→20/40`, cylinder `8/212→24/212`, sphere
  `196/1913→228/1913`으로 바꿨다. 그러나 centroid-dual invalidity는
  `2/30`, `70/440`, `0/0`에서 변하지 않았고, clipped-circumcenter 후보는
  star guard가 거부했다(`11/240`, `68/558`, `82/404`). 따라서 단순 local
  move는 불충분으로 기록하고 production에는 연결하지 않았다.

- 추가 hybrid 후보(이미 well-centered인 tet만 circumcenter, 나머지는
  centroid)는 candidate invalid를 cube `11/156`, cylinder `70/457`, sphere
  `10/56`으로 줄였지만 기존 whole-candidate guard가 거부했다. 최종 출력은
  centroid fallback과 같았으며, 공유 dual point를 깨뜨릴 수 있는 per-cell
  silent mixing은 구현하지 않았다.

- `POLY-DUAL-TOPOLOGY-1` valence audit: 3D well-centeredness necessary
  condition인 interior valence 7 미만이 cube `1`(min `6`), cylinder
  `1`(min `6`), sphere `7`(min `0`, unused exported point 포함)이었다. 따라서
  단순 interior relocation이 아니라 low-valence/orphan point와 dual
  internal face의 연결 관계를 먼저 추적한다.

- topology map에서 boundary triangle에 속하지 않으면서 incident tet가
  3개 미만인 edge가 cube `6`, cylinder `46`, sphere `489`개 나왔다. 대표는
  cube `(0,6):(28,29)`, cylinder `(32,64):(9,78)`, sphere
  `(215,267):(13,298)`이다. low-valence 점 주변 ring은 평면이어서, 다음은
  native-tet edge-link completeness cross-check이며 repair는 보류한다.
- 2026-07-27 native_poly topology correction: the preliminary open-link count
  (`6/46/489`) was caused by a diagnostic bug that recorded only the first edge
  of each boundary triangle. After fixing it, incomplete internal links are
  `0/0/0` for cube/cylinder/sphere (`0/42`, `0/156`, `0/1331`), matching the
  native-tet audit. `POLY-DUAL-CONNECTIVITY-REPAIR1` was not opened.

- 2026-07-27 `POLY-DUAL-FACE-WARP1`: boundary-fixed primal relocation reduced
  internal centroid-dual ring warpage only modestly (cylinder `0.029185 ->
  0.028993`, sphere `0.032016 -> 0.029035`; cube unchanged), while invalid
  cells stayed `2/70/0` for cube/cylinder/sphere. Measured insufficient; no
  production wiring.

## 2026-07-27 — native_hex 문헌 gap 및 HEX-TRANS-2 재측정

- `gap_search_transition_sheet_provenance_2026-07-25.md`를 보완했다. 19편을
  P0/P1/P2와 INCLUDE/CONTEXT/EXCLUDE, OPEN/ABSTRACT_ONLY로 정리했고,
  `10.1016/j.advengsoft.2014.05.005`는 octree 사전조건화,
  `10.1016/j.cja.2026.104154`는 hanging-node refinement quality gate로
  분리했다. 두 메커니즘 모두 현재 Phase 1 wall-fit solver로 바로 포팅하지
  않는다.
- 새 fine/pre-BL 출력에서 `HEX-TRANS-2`를 재측정했다. bad face의 직접
  transition-owner 겹침은 cylinder `344/344`, sphere `918/960`, gear
  `68/68`이고, 전체 boundary의 직접 겹침은 `74.2%/94.3%/88.5%`였다.
  enrichment는 `1.348x/1.014x/1.130x`다.
- 세 형상의 bad face는 geometry-only feature proxy상 전부
  `smooth/defaultWall`이었다. 이는 sphere의 전이 집중을 입증하지 못하고,
  현재 writer가 octree level/patch provenance를 보존하지 않는다는 사실을
  확인한다. 다음 카드는 `HEX-PROV-RETENTION-1` report-only 감사다.

## 2026-07-27 — native_tri metric 반복·BL handoff 마감

- 고정 fixture의 SPD metric 진단을 두 번 실행해 출력이 byte-identical임을
  확인했다. cube eigen `16/16`, sphere target `0.160770–0.172150`, cylinder
  target `0.25–2.0`, BL proxy eigen `16–1600`, invalid SPD `0`이다.
- tangent/normal handoff는 `37 passed`로 닫았다. sharp cube/cylinder edge는
  각각 `18/18`, `192/192`를 명시적으로 거부하고, normal-layer placement는
  아직 구현하지 않는다. surface operator는 BL normal eigenvalue를 사용하지
  않는다.
- 다음 tri 카드는 L2 corpus 확장과 normal-layer placement 전제 감사이며,
  anisotropic operator 승격은 bit-identical topology·surface·predicate gate
  전까지 보류한다.

## 2026-07-27 — native_hex writer drop 원인 국소화

- `HEX-PROV-RETENTION-1`을 마감했다. cylinder `6320/6320`, sphere
  `4224/4224`는 raw→written cell/boundary topology가 보존됐지만, 세 writer
  호출 모두 octree level/source patch provenance를 받지 않았다.
- `HEX-GEAR-DEGEN-DROP-1` 진단은 optional `native_polymesh`가 없는 Python
  fallback에서 writer의 six-cell drop을 정확히 재현했다. raw cell
  `329,335,4013,4187,4589,4595`가 탈락했고, 세 paired face key가 모두
  centered rank 1/area 0이었다. 중복 정점 정리가 아니라 post-octree/snap
  zero-thickness hex가 upstream 원인이다.
- writer의 non-strict drop 뒤 gear boundary ID가 `15 removed + 15 added`로
  바뀌므로, 다음 카드는 upstream degeneracy strict-reject/rollback 정책
  감사다. 자동 재팽창·삭제·게이트 완화는 아직 하지 않는다.

## 2026-07-27 — native_hex wall-fit zero-thickness guard

- stage 계측으로 fatal face가 octree/iterative snap에는 없고 `_wall_fit_snap`
  직후 처음 생기는 것을 확정했다. z=`0.2868928114`의 boundary vertex가
  이미 같은 면에 있던 z=`0.3000000119` layer로 투영된 것이 원인이었다.
- `_wall_fit_snap`의 기존 candidate rollback에 영향 셀 face-area 검사를
  추가했다. gear raw/written cells는 `4920/4920`, writer drop `0`, boundary
  ID delta `0+0`, zero-area key `0`으로 회복됐다.
- cylinder/sphere topology·transition proxy와 negative-volume `0/0/0`은
  유지됐다. native_hex suite `97 passed, 9 skipped`, focused wall-fit/snap
  `22 passed`. 다음 카드는 `HEX-WALLFIT-PARETO-1`이다.

## 2026-07-27 — native_hex wall-fit Pareto 재측정

- guard 적용 후 ON/OFF를 cylinder/sphere/gear/bracket에서 다시 비교했다.
  cylinder/sphere area error는 `17.214→0.275%`, `41.070→0.037%`로 좋아졌지만
  boundary skew는 `0.699→9.486`, `0.930→8.779`로 악화됐다.
- gear는 area error `7.331→0.0547%` 대신 skew `1.058→2.775`, warpage
  `0.211→1.000`이 악화됐고, bracket은 skew `0.326→409.288`로 악화됐다.
  negative volume은 모두 0이었다.
- 전역 wall-fit 승격은 기각한다. 다음 native_hex 카드는 문헌 기반
  surface-constrained local Pareto 후보 진단이다.

## 2026-07-27 — native_tri TRI-CORPUS-1 확장 기준선

- 기존 L2 `native_remesh.isotropic`를 10개 형상에 형상별 독립 실행했다.
  9개는 측정됐고 `sharp_features_micro_ridge.stl`은 빈 face 배열을
  `_tangential_relocate`가 인덱싱하는 기존 `IndexError`를 드러냈다.
- cube/sphere만 manifold+watertight였다. cylinder, thin disk, needle,
  perforated plate, multi-scale sphere, dual torus는 topology/geometry 계약을
  위반했고, wing-with-spike는 manifold지만 watertight가 아니었다.
- 이 결과는 L2 경로의 gap baseline으로만 보존한다. 다음은
  `TRI-OPERATOR-CORPUS-1`이며 새 native-tri guarded operator-loop에 같은
  topology/geometry/feature/determinism gate를 적용한다.

## 2026-07-27 — native_tri guarded operator corpus 1차

- cube/sphere/cylinder/thin disk/wing에 split→collapse→flip 한 라운드
  (smoothing OFF)를 적용했다. accepted/rejected는 `16/3`, `0/0`, `204/18`,
  `176/22`, `34/14`였고 모든 출력이 finite·positive-area였다.
- cube/sphere/cylinder/thin disk는 manifold+watertight, wing은 manifold지만
  open 상태를 유지했다. thin disk max angle `168.75°`는 품질 문제로
  분리했고 topology guard는 완화하지 않는다.
- 두 번의 JSON 보고서 SHA-256이 동일했다. 다음은 corpus 확대 및
  thin/feature quality 분리다.

## 2026-07-27 — native_tri operator corpus 확장

- needle은 `61/17` accepted/rejected, manifold+watertight를 유지했지만
  각도 `0.1059–179.787°`, sampled Hausdorff `5.0000008`로 품질 카드가
  필요하다. multi-scale sphere는 `32/68`, manifold+watertight,
  `31.2577–81.7868°`, Hausdorff `0.05000006`이었다.
- high-genus dual-torus는 한 라운드가 `120 s` 안에 반환되지 않아
  `TRI-OPERATOR-PERF-1`로 분리했다. 이는 topology 실패로 판정하지 않으며,
  다음 라운드에서 split/collapse/flip 단계별 시간과 후보 수를 계측한다.

## 2026-07-27 — native_tri 성능 후보 판정

- stable-label/heap worklist는 cube/cylinder/thin disk에서 빠르지만 accepted
  수와 최종 digest가 달라 drop-in 후보로 반증됐다. production에는 연결하지
  않고 진단 lower bound로 남겼다.
- `AUTO_TESSELL_TRI_LOCAL_GUARDS1=1` 국소 guard는 cube/cylinder/thin disk/
  needle/multi-scale sphere에서 OFF와 byte-identical이고 핵심 37개 테스트를
  통과했다. 그러나 dual-torus flip은 300초 내 끝나지 않아 성능 승격은
  보류하고 기본 OFF로 유지한다.

## 2026-07-27 — native_tet BSP current fine-route 재검증

- 현재 worktree의 `target_cells=15000` route는 `_phase_bc_skip`로 진입했다.
  edge OFF는 `14.35 s`, `13,970 cells/3,920 points`, mean q `0.3255`; edge
  ON+batch cap 500은 `134.42 s`, `13,788/3,881`, mean q `0.3237`이었다.
- ON의 edge-recovery snapshot은 boundary `1560` faces와 area
  `103.399255187455`를 정확히 보존했지만 최종 CDT/coverage는 phase skip으로
  `-1`이라 fixed-condition BSP acceptance 근거가 아니다. metric/GAP도
  `_tet_boundary_faces` unbound caller로 skip되어 별도 root-cause 카드로
  분리했다.

## 2026-07-27 — native_tet metric/GAP caller 정합성

- `_tet_boundary_faces`를 JJ3 조건부 import에 의존하던 두 후속 블록에
  각각 local import했다. target 600에서 metric tensor와 GAP-SELF가 실제
  실행됐고, OFF는 `15,353 cells`, mean q `.3448`, 12.02초, ON은 `16,483`,
  `.3672`, 72.45초였다.
- edge ON snapshot은 boundary `1,320` faces와 area `103.399255187455`를
  보존했다. 이 수정은 lock/threshold/surface policy를 바꾸지 않았으며,
  stellar import mismatch는 별도 WIP로 남겼다.

## 2026-07-27 — native_tet fixed-condition BSP 카드 판정

- `AUTO_TESSELL_P4C_PYTETWILD=0`, target 15000 fixed-fine 재현: OFF
  `17458/4453`, `31.40s`, cdt `.80518/.46509`, plane `.68116/.66596`, q
  `.14912`; ON+batch cap 500 `17914/4535`, `151.75s`, 최종 지표 동일, q
  `.15234`. edge/BSP는 기본 OFF 유지한다.
- target 600 full-pipeline digest는 OFF와 ON 각각 2회 반복에서 동일했다.
  따라서 BSP recovery 카드는 fixed-condition 측정 종료로 정리하고,
  `_phase_bc_skip` route와 미완료 stellar WIP mismatch는 별도 카드로
  분리한다. 다음은 TET-LAZY-2/TET-FLOW-3 단독 측정이다.

## 2026-07-27 — native_tet FSL lazy-flip 측정

- FSL wave-1 현재 mesh에서 core flat wedge `61`개 중 `60`개가 guarded
  depth-1 lazy edge removal로 private-copy 개선 가능했고 `1`개는 depth-2와
  exhaustive multi-face fallback 뒤에도 구조적으로 막혔다. tets
  `12219→12159`, boundary faces `4588→4588`, mean q
  `.151544→.152208`, min q 불변이다.
- TET-LAZY-2 bounded diagnostic은 정렬된 interior edge `10497`개 중 앞
  `128`개를 두 라운드 조건으로 검사했으나 승인 `0`건이었다. 모두 기존
  `no_improving_retriangulation` gate에서 거부됐고 angle round만 관측 후
  rollback됐다. 표면 집합/면적과 입력 digest는 불변이다.
- 두 결과 모두 측정/진단으로만 기록했으며 기본 경로, 품질 임계값, 표면
  정책은 변경하지 않았다. 다음 카드는 TET-FLOW-3 단독 측정이다.

## 2026-07-27 — native_tet TET-FLOW-3 진단

- 기존 구현이 없어 default-OFF 진단 모듈을 추가했다. bad tet별 2–3,
  cycle-validated 4–4, general edge-removal 후보를 시뮬레이션하고 boundary
  face-set, signed-volume/tiling, global worst-Q guard를 적용한다. mesher에는
  연결하지 않았다.
- FSL mesh에서 5개 epsilon rung와 rung당 bad tet 8개를 실행한 결과 후보
  364개 중 2개만 private sequence에 들어갔다. boundary `4588→4588`, 입력
  배열 불변이었지만 min q는 `7.3576387e-09`로 그대로라 전체 rollback됐다.
- 8개 예산은 `26.4초`, 32개 예산은 120초를 넘었다. 따라서 현재 naive
  global-array 재계산 구현은 비용 카드로 반증됐고, 다음은 cavity-local
  incidence/quality evaluator를 설계·측정하는 일이다. 임계값 완화나 기본
  활성화는 하지 않는다.

## 2026-07-27 — native_tet SHAPE-1/WDEL-2 진단 종료

- GSM report-only 점수 calibration: 정규 tet `1.000000`, 평탄 tet
  `0.00053598`. 관련 shape/certification 테스트 `3 passed`.
- WDEL-2 GSM-ratio forbidden-interval proxy는 FSL 후보 `152`개에서
  `90` PUMPABLE/`62` LOCKED를 냈다. 그러나 core wedge `61`개와 실제
  wave-1을 대조하면 예측 `4/57`, 실제 `60 unlocked/1 blocked`, 일치율
  `8.2%`로 acceptance `90%`를 크게 밑돌았다.
- 이 분류기는 measured/falsified로 폐기하고 WDEL 라우팅이나 production
  gate에 연결하지 않았다. 정확한 분류에는 Delaunay star와 weight interval
  입력을 먼저 노출해야 한다.

## 2026-07-27 — native_tet TET-DET-P4C 결정론성 격리

- 같은 cylinder 입력을 반복 실행한 결과 Delaunay 단계와 P4C OFF native
  경로는 byte-identical이었다. 따라서 최초 분기점은 Qhull이나 native
  local operator가 아니다.
- P4C ON의 설치 `pytetwild 0.2.3`는 `num_threads=1`, `optimize=False`에서도
  호출마다 점/셀 수와 배열 digest가 달랐다. bundled fTetWild의
  `TriangleInsertion.cpp`에서 `std::random_device`로 입력 면을 섞는 것이
  소스 수준 원인이다.
- 이는 외부 fallback의 결정론 장애이므로 TET-WDEL-3 측정 전에 고정 시드
  재빌드 A/B를 수행했다. `TriangleInsertion.cpp`의 첫 `random_device`를
  `42`로 고정해도 fresh-process 결과가 달라져, unordered-container와
  추가 mutable ordering까지 정규화해야 하는 구조적 문제로 반증됐다. 소스와
  빌드 산출물은 원래 동작으로 복원했고 기존 fallback 기본값은 변경하지 않았다.

## 2026-07-27 — native_tet FLOW-3 cavity-local cache

- 프로파일링에서 `general_edge_removal`이 후보마다 전체 incidence map을
  다시 만드는 비용이 병목으로 확인됐다. round-local map을 재사용하는
  private diagnostic hook을 추가했다.
- 32 bad-tet/5 rung가 `60.3초→1.84초`로 줄었고 후보/수용/평균·최소 품질/
  boundary 결과는 동일했다. 128 bad-tet/2 rounds/rung도 `6.02초`,
  11,859 candidates, 10 private accepts까지 완료됐다.
- candidate mean q는 `.151667`까지 올랐지만 global min q는
  `7.3576e-09`로 변하지 않아 전체 sequence는 rollback됐다. 성능은 닫혔지만
  worst-quality gate는 닫히지 않았고 FLOW-3은 계속 default-OFF다.

## 2026-07-27 — native_tet final-result contract와 boundary root-cause 연쇄

- W3 이후 반환 배열·메타데이터·디스크가 서로 다른 후보를 가리키던 계약
  불일치를 수정하고 cylinder에서 배열/카운트/`polyMesh` 일치를 검증했다.
- naca boundary audit은 NN1 collapse `696→984`를 최초 원인으로 특정했다.
  candidate-level collapse simulation으로 default lane을 보수화해 `696`을
  유지했다.
- post-BSP 4-4는 실제 반대정점 cycle을 복원하고 후보별 경계 검사로
  `984→1008` 위반을 차단했다.
- VVV8 boundary Laplacian은 품질만 단조여도 면적을 바꿀 수 있어 공용
  boundary keys/area guard를 acceptance 조건에 추가했다.
- naca thin-sliver 게이트는 `2 passed, 1 strict xfailed`; 현재 수정은
  아직 커밋하지 않았고 hard-12 및 permanent gate 재검증이 다음 관문이다.
## 2026-07-27 — hard-geometry matrix와 영구 게이트 정리

최종 결과 동기화와 boundary-preservation 연쇄 수정 뒤 13개 native_tet
형상을 다시 측정했다. 7개는 PASS-ish였고, naca는 표면/체적/퇴화가
`1.000/1.001/0`으로 회복됐지만 전체 skew `34.80`으로 품질 gate는 아직
실패한다. dual torus와 perforated plate는 120초 timeout, thin disk와
micro-ridge는 별도 geometry 카드로 분리한다. 영구 테스트 수집을 막던
near-wall/runtime WIP import 계약은 최소 helper로 닫았으나,
`test_native_tet_pass_runtime_contracts.py`의 cylinder `>=600 cells`
기대치는 현재 실제 계약(212 cells)과 충돌하므로 production 결과를
왜곡하지 않고 별도 WIP 계약으로 남겼다.
