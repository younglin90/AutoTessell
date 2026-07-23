# Livesu, Pitzalis, Cherchi — Optimal Dual Schemes for Adaptive Grid Based Hexmeshing (2022)

**DOI:** `10.1145/3494456` (ACM TOG 41(2))
**Status:** FULL_READ, pages 13/13, 2026-07-23 — **arXiv v1 (2103.07745v1, 2021-03) 기준.**
저널판(TOG 2022)과 세부 편집 차이가 있을 수 있음(내용 골격은 동일 계열 후속 논문
Pitzalis 2021이 "Livesu et al. 2021"로 인용하는 바로 그 스킴 세트).
**PDF:** `papers/pdf/35_livesu_2022_optimal_dual_schemes.pdf`
(SHA-256 `06028227D40DE3FA08AC122C39A80A410F929D96EB7108793F04EE6994A09E15`)
**Code:** CinoLib (MIT, `github.com/mlivesu/cinolib`)에 스킴+설치+dualization 수록.

## 핵심 정리 — 이것이 실제 "템플릿(스킴) 논문"

adaptive grid의 hanging node를 dual 접근으로 제거하는 스킴 세트를 **완전 열거·증명·공개**.
primal 접근(hanging node를 hex로 직접 흡수)은 오목 구성에서 홀수 개 quad면 때문에
불가능함이 증명되어 있음(Mitchell 1996) → dual 접근이 필연.

**Dual 원리:** primal 다면체 복합체에서 정점가수 6 + 변가수 4를 모두 만족시키면
dualization 결과가 순수 hex (dual 셀 면수 = primal 정점가수, dual 면 변수 = primal
변가수). 스킴 = 정제 클러스터 둘레를 감는 삼각 단면 프리즘 체인 네트워크로,
가수를 정규화하는 일반 다면체 셀 집합.

## 4대 기여

1. **완전 열거:** 큐브 8분면을 coarse(2³)/fine(4³)로 채우는 2⁸ 조합 → 대칭 제거 후
   **20개 고유 전이** (Marching Cubes / dual MC [Nielson 2004]와 동형 조합 공간).
   Maréchal 2009는 기본 전이 3종만, Gao 2019는 논문 기재 스킴만으로 7/20만 커버 —
   기존 문헌은 exhaustive가 아니었음을 지적.
2. **모호성 규명:** 프리즘 체인 교차는 한쪽이 아래로 지나가야 함(아니면 가수 8 정점 발생).
   flat 교차 2가지, 오목 변 2²(고유 3종: 오각/육각/칠각 면), 오목 코너 2³(고유 2종) —
   선택에 따라 특이 구조가 달라짐. 기존 논문은 이 선택을 명시하지 않아 재현 불가였음.
3. **최적 선택:** 오각면 옵션(가수 5 변) + 대칭 코너 구성 채택 →
   **강균형 그리드: 특이 변 가수 3, 5, 6만 발생 (상한 6 보장).**
   비교: Maréchal 상용 구현 가수 최대 8–9, Gao 2019 최대 8–10 (표면 패딩 변 제외 시
   둘 다 [3,8]); Gao 2019는 가수 7 변을 181/202 모델에서 사용, Maréchal은 23/202.
   변 가수는 국소 달성가능 최대 SJ를 직접 제한(Fig 2)하므로 품질에 직결.
4. **weak balancing 확장 (최초):** strong = 면/변/정점 인접 셀 모두 레벨차 ≤1,
   weak = **면-인접만** ≤1. weak 그리드는 한 변에 3개 레벨, 한 정점에 4개 레벨까지 허용.
   정점 케이스는 무처리 OK(항상 8셀/6변 → dual hex). 변 케이스(3레벨 공유)가 새 hanging
   node를 만들며 4가지 구성(열린 오목 변 / 오목 코너에서 1·2·3변 관여) → 볼록+오목
   블렌드 스킴 5종 추가. 이때 오각→육각, 육각→칠각으로 승격되어
   **약균형 그리드: 특이 변 가수 3, 5, 6, 7 (상한 7).**

## 스킴 세트 (구현 표면)

- **8 atomic 스킴(강균형):** F(flat), F+C, C1/C2/C3(볼록, 체인 1·2·3개), E(오목 변),
  VC(오목 정점 중앙), VS(오목 정점 측면). **+5 스킴(약균형):** E-MR, VC1/2/3-MR, VS-MR.
- 각 스킴은 **하드코딩된 일반 다면체 메시**이며 설치 코드는 평행이동/회전/반사/스케일만
  수행. 원자 블록은 서로 충돌하지 않아 설치 순서 무관, 20개 전이 전부를 8(+5)개 조합으로
  재현. 이후 표준 dualization 1회 → 순수 hex. Table 1에 스킴별 면 다각형 수(F3–F7) 명세
  → 출력 특이 변 가수의 정확한 회계 가능("declared valence 외 불가능".)
- 파이프라인 검증: 202 모델(Gao 2019 데이터셋), octree 깊이 ≤7, SDF 두께 기준 분할,
  balancing/pairing 정제 → 스킴 설치 → dualization → 형상 밖 hex 제거 → 경계 투영
  (+ 필요 시 Edge-Cone Rectification 언탱글).

## 증명/보장 상태

- **all-hex 변환 보장: YES** — 20 전이 완전 열거 + 8(+5) 스킴의 커버리지로 구성적 증명.
  strong/weak balanced + paired 그리드에 대해 항상 순수 hex 산출.
- **특이 변 가수 상한: 강균형 6 / 약균형 7 — 구성적으로 보장.**
- **양의 Jacobian / 기하 품질: NO** — 위상만 보장. 투영 아티팩트는 외부 언탱글러
  [Livesu 2015]로 사후 처리. 경계·피처는 명시적으로 범위 밖(임의 투영법과 결합 가능).
- **약균형 절감 수치:** 강균형 대비 셀 수 평균 **~15% 절감**, 피크 **30%+**,
  202 모델 중 **75%+에서 감소** (Fig 17; 성장률 1−|H|_W/|H|_S 기준).

## 한계

1. arXiv v1 기준 pairing 요건 서술이 암묵적 — 그리드 준비(최소 정제)는 후속작
   Pitzalis 2021이 담당. 스킴 세트만으로는 임의 2:1 그리드에 설치 불가(paired 필요).
2. 약균형에서 가수 7 특이 변 재도입(5개 MR 스킴 중 4개) — 셀 수와 특이 구조의 트레이드오프.
3. 기하 품질/투영/피처 보존은 전부 외부 위임.
4. frame-field 등 회전 전이가 있는 격자에는 미적용.

## HEX-OCT-2 (Option A/B) 적용 판단

- 우리 엔진의 "conforming polyhedral transitions NOT proven all-hex" gap의 **직접 해답.**
  현재 우리 전이 셀은 사실상 이 논문의 primal 다면체 스킴에 해당하는 것을 비체계적으로
  만들고 dualize하지 않는 상태 — 스킴 세트 + dualization을 포팅하면 전이부가 증명된
  all-hex가 된다.
- **포팅 단위 추천:** (1) 20-전이 lookup(octant 마스크 → 스킴 배치), (2) 8+5 하드코딩
  다면체 블록(CinoLib에서 좌표/위상 추출 가능, MIT), (3) 설치(강체변환+반사) 루틴,
  (4) polyhedral→dual hex 변환기. 우리 `core/utils`의 polyMesh 다면체 표현과 궁합 좋음.
- **주의:** dualization은 그리드 경계에서 반(半)셀 문제가 생기므로 경계 한 층은 표면
  패딩(pillowing)과 결합하는 것이 통례(Maréchal/Gao 모두 1층 패딩 적용) — 우리 BL 패스
  (`core/layers/native_bl.py`)와의 접속 설계 필요. Maréchal 2016(all-hex boundary layers)이
  이 접점의 전용 문헌.
- Zhang 2013 델타: Zhang은 primal 2-refinement 템플릿(+pillowing/스무딩)으로 가수 회계와
  완전성 증명이 없음. 본 논문은 완전 열거 + 가수 상한 증명 + MIT 코드 — 템플릿 기준을
  이 논문으로 교체하는 것이 타당.

## 기존 카드 확인/수정

- sweep P1 항목 "enumerates all transitions … proves which adaptive grids admit pure-hex
  conversion" — 확정. 정확한 수치: 20 전이 / 8+5 스킴 / 가수 상한 SB 6, WB 7.
- "all-hex transition honesty" falsification 규칙에 사용할 판정문: **balanced(strong 또는
  weak) + paired 그리드가 아니면 dual 스킴 적용을 주장할 수 없다.** 우리 엔진이 pairing을
  검사하지 않는 한 all-hex 클레임 금지 유지.

## Snowball (≤5)

1. Maréchal 2016, "All hexahedral boundary layers generation", Procedia Eng. 163 — dual 접근과 경계층 결합; 우리 Tier-4 BL 패스와 직접 접점. **우선 확보 권장.**
2. Mitchell 1996 — 홀수 quad 경계의 hexmeshing 불가 특성화; primal 접근 포기의 이론 근거.
3. Nielson 2004, "Dual Marching Cubes" — 20 전이 lookup의 구조적 원형; 구현 시 참조 테이블 설계에 유용.
4. Tautges, Knoop 2003 — atomic dual-based hex 위상 편집 연산; 스킴-후 국소 수리와 연결.
5. Weiler, Schindler, Schneiders 1996 — 28→20 구성 축약 최초 보고(기술보고서).
