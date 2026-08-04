# Pitzalis, Livesu, Cherchi, Gobbetti, Scateni — Generalized Adaptive Refinement for Grid-based Hexahedral Meshing (2021)

**DOI:** `10.1145/3478513.3480508` (ACM TOG 40(6), SIGGRAPH Asia 2021)
**Status:** FULL_READ, pages 13/13, 2026-07-23.
**PDF:** `docs/references/papers/source/pdf/34_pitzalis_2021_generalized_adaptive_refinement.pdf`
(SHA-256 `9F36FCC8FE2F7E82019B0E6B4736630A1CA3DE9C6C72EDF9DB81CFE0E67BBC35`)
**Code:** `github.com/cg3hci/Gen-Adapt-Ref-for-Hexmeshing` (C++, CinoLib + **Gurobi**)

## 문제 설정 — 이 논문은 "템플릿 논문"이 아니다

중요 교정: 사전 카드(forward_citation_sweep)에서 "Pitzalis templates"라고 불렀지만,
**전이 템플릿(스킴) 자체는 Livesu et al. 2021/2022 (Optimal Dual Schemes)에 있다.**
이 논문의 기여는 그 스킴을 설치할 수 있게 그리드를 **최소 추가 정제로 준비하는 단계**다.
adaptive grid → conforming all-hex 변환에는 두 위상 조건이 필요:

- **balancing** — 인접 셀 간 정제 레벨 차 ≤ 1 (우리 엔진의 2:1 규칙과 동일). 국소 조건.
- **pairing** — 같은 크기 셀들의 face-adjacent 클러스터가 모든 변에서 **짝수 개**여야 함.
  비국소 조건이며, 기존 방법(Maréchal 2009, Gao 2019, Livesu 2021)은 이를 octree
  형제-분할 규칙(부모의 한 자식이 분할되면 형제도 분할)으로 강제 → 심한 과잉 정제.

핵심 통찰: 정제를 셀이 아니라 **그리드 정점**에 배분하면(정점 = 2×2×2 minor의 중심)
pairing이 선형 제약이 되고, 전체 문제가 **이진 ILP**로 풀린다. octree 규칙 없이
임의 형태/위상의 그리드(폴리큐브 공간 포함)에 적용 가능.

## 방법 요약

1. **정규 이진 그리드 ILP** (§4): 미지수 r(v) ∈ {0,1} per vertex, 셀 정제 = 입사 정점 합.
   목적함수 = 총 추가 정제 최소화. 제약: (a) 입력 정제 보존 Σr(v) ≥ r(c),
   (b) minor 겹침/부분 접촉 금지 — Fig 6의 9개 상호작용 분류 중 6개가 불법,
   정점당 98개의 `r(vi)+r(vj) ≤ 1` 제약, (c) 폭 1의 좁은 다리(버퍼층 부족) 금지 —
   정점당 추가 210개 쌍별 제약. 스킴은 항상 전이의 **coarse 쪽**에 설치되므로 정제
   클러스터 주위에 비정제 버퍼층이 필요하다는 점이 (c)의 근거.
2. **적응 그리드로 확장** (§5): 레벨 쌍 (l_max, l_max−1) → … → (l_min+1, l_min) 순으로
   임시 이진 부분그리드를 만들어 ILP를 반복 적용, 각 solve 후 balancing 재수행(interleave).
   fine→coarse 순서가 수렴 보장. 부분그리드에 구멍/다중 연결요소 있어도 무수정 동작.
3. **weak balancing 지원** (§5.2): weak(면-인접만 제약) 채택 시 부분그리드 경계 정점이
   정제를 받을 수 있음 → 전역 그리드에서 해당 minor를 강제(3D에서 최대 3회 분할, Fig 7).
   레벨 2 차이 클러스터의 정렬 불일치(Fig 9)는 추가 제약 1개로 방지(Livesu 2021 스킴이
   비정렬 케이스를 처리 못하기 때문 — 이론상 balanced+paired면 hexmeshable이어도).
4. hexing 자체는 Livesu 2021 스킴(CinoLib 구현) 적용 후 dualization, 이후 경계 투영.

## 증명/보장 상태

- **all-hex 위상 보장: YES (구성적).** 출력 그리드가 balancing+pairing을 만족하면
  Livesu 2021 dual 스킴이 모든 전이에 설치 가능하고 dualization이 순수 hex를 산출.
  이 보장은 스킴 쪽(Livesu 2022 노트 참조)의 exhaustiveness 증명에 의존.
- **최소성: 부분적.** 각 국소 ILP는 최적이지만 전역 최적은 국소 해가 부분그리드 경계에
  노출되지 않을 때만 보장. 반례 존재(§7 inset): 홀수 폭 closed ring이 불필요하게
  두꺼워짐 — 정점 기반 정식화가 전역 순환 배치를 못 잡음. edge 기반 정식화는 미해결.
- **양의 Jacobian / 기하 품질 보장: NO.** 경계 투영은 명시적으로 "overly simple" 휴리스틱:
  최근접점 이동 + 뒤집힘 시 이진 탐색 되돌림 20회 + Edge-Cone Rectification 1회
  [Livesu 2015]. sharp feature는 이면각 60° 임계 검출 후 Gao 2019 방식으로 매핑.
  조합론(내부 연결성)과 기하 투영은 **직교 문제**로 선언 — 경계는 Gao 2019, Lin 2015
  등 기존 투영법과 결합하라고 명시. (Fig 15 hand 예제: 25K hexa, 평균 SJ 0.65, 최소 0.1.)

## 실험 결과 (202 모델, Gao 2019 데이터셋)

공정 비교를 위해 동일 octree(SDF 두께 기반 분할)를 세 방법의 공통 입력으로 사용.
OP = octree pairing, GP = generalized pairing(본 논문), SB/WB = strong/weak balancing.

| 지표 (평균, 입력 12K셀) | OP+SB (Maréchal/Gao) | OP+WB (Livesu 2021) | GP+WB (ours) |
|---|---|---|---|
| 추가 셀 Δabs | 24.4K | 19.9K | 13.6K |
| 상대 성장 Δrel | 231% | 186% | **116%** |
| 증가 배율 | 3.3× | 2.9× | **2.1×** |
| 최대(입력 128K) | 802% / 9.0× | 589% / 6.9× | 451% / 5.5× |

- 194/202 모델에서 승리, 8/202 동률(거의 큐브 형상), **패배 0** — 절대 더 나빠지지 않음.
- 2배 이상 성장 비율: SB 88% / WB 86% / ours 63%. 3배 이상: 58% / 43% / 6%.
- 결론 수치: **SB 대비 추가 셀 약 절반 이하, WB(octree) 대비도 거의 절반** (13.6K vs 19.9K ≈ 32% 감소).
- 스케일링: 입력 셀 수에 대략 선형, 중앙값 710 입력셀/s (i9 2.9GHz). pairing이 90%+,
  그중 절반이 Gurobi solve. warm start 미적용(개선 여지 명시).
- 폴리큐브 응용(§6.2): 단순 큐브 폴리큐브 + 왜곡 맵에서도 적응 샘플링으로 손가락 등
  피처 복원 — 폴리큐브 파이프라인의 강한 가정(무왜곡 맵)을 완화하는 부수 효과.

## 한계

1. 전역 최적 아님(closed-ring 반례); 혼합 레벨에서 폭 1 링이 생길 수 있음.
2. ILP 솔버 의존 — 레퍼런스 구현은 **Gurobi(상용)**. 제약이 전부 쌍별 `x_i+x_j ≤ 1`
   (독립집합형) + 커버 제약이므로 오픈 솔버(HiGHS/CBC/CP-SAT)나 휴리스틱 대체 여지 있음.
3. octree 방식보다 느리고 구현 복잡(저자 자인). 단 meshing은 1회성 오프라인 작업이라는 논리.
4. 경계/피처 처리는 범위 밖 — 투영 실패 가능성 명시.
5. frame-field 격자로의 확장은 비자명(회전 전이 미지원).

## HEX-OCT-2 (Option A/B) 적용 판단

우리 엔진 현황: adaptive grid + 2:1(=balancing은 이미 있음) + **pairing 없음** →
전이가 일반 다면체 셀로 남고 all-hex 미증명. 이 논문 기준으로 정확히 진단하면
**우리의 gap은 (1) pairing 단계 부재, (2) 증명된 dual 스킴 세트 부재** 두 가지다.

- **권고: Option A(포팅) 채택하되 2-단 구성으로.**
  - 필수 코어 = **Livesu 2022의 8+5 atomic 스킴 + dualization** (CinoLib, MIT — 포팅 부담
    작음, 하드코딩된 다면체 블록 + 강체변환 설치). 이것만으로 all-hex 증명 확보.
  - pairing은 1단계로 **octree 규칙(OP+WB)** 으로 시작해도 스킴 적용엔 충분(성장 2.9×),
    2단계 최적화로 본 논문의 ILP(GP+WB)를 도입해 2.1×로 축소. ILP는 성능 최적화이지
    정당성 요건이 아님 — 도입 순서를 분리할 수 있다는 것이 이 논문의 실용적 가치.
- Zhang 2013 대비 델타: Zhang은 primal 2-refinement 템플릿 + tree 규칙(사실상 OP+SB
  계열, hanging node를 primal로 흡수). 본 계열은 dual 접근 + weak balancing + ILP로
  (a) 셀 수 대폭 감소, (b) exhaustiveness 증명, (c) 공개 코드 3박자에서 우위.
  Zhang 2013 템플릿 포팅 계획은 **철회 권고** — 비교 실험 대상으로만 유지.
- 경계 파이프는 현행 유지(wall-fit snap + 검사): 본 계열도 경계는 외부 위임이므로
  우리 표면 보존 invariant와 충돌 없음.

## 기존 카드 확인/수정

- forward_citation_sweep의 P0 Pitzalis 항목: "installs conforming all-hex templates" →
  **부정확**. 템플릿은 Livesu 2022; Pitzalis는 ILP 기반 최소 정제(GP). 카드 문구 수정 필요.
- "fewer refinement propagations → smaller meshes" 정량 확정: 평균 성장 116% vs 231%(SB).
- weak balancing 정의 확정: **면-인접 셀만** 레벨차 ≤1 (strong은 면/변/정점 인접 전부).

## Snowball (≤5)

1. Weiler, Schindler, Schneiders 1996 — 20개 전이 구성 최초 열거(기술보고서). 스킴 완전성 논거의 뿌리.
2. Hu, Qian, Zhang 2013 — hybrid octree + bubble packing, 전이 스킴을 안쪽으로 시프트. OP 계열 변형.
3. Hu, Zhang 2016 (CMAME 305) — CVT 폴리큐브 + Maréchal 스킴 적응 all-hex; §6.2 폴리큐브 결합의 선행.
4. Xu, Gao, Deng, Chen 2017 (CGF 36(8)) — 폴리큐브 변형으로 가변 셀 크기; 본 논문이 우월성 주장한 비교 대상.
5. Bawin, Henrotte, Remacle 2020 (arXiv:2009.03984) — feature-preserving size field 자동 생성; 우리 octree 분할 기준 설계에 참고.
