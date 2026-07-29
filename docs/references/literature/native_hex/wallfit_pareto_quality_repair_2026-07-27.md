# Native Hex wall-fit Pareto 품질 복구 문헌 카드

**날짜:** 2026-07-27
**카드:** `HEX-OCT-SCALE-QUALITY-1` / `HEX-WALLFIT-PARETO-1`
**범위:** 문헌 통합 및 측정 계획. 생성 로직과 영구 게이트는 변경하지 않음.

## 1. 현재 문제의 측정 기준

`HEX-OCT-MIXED-LEVEL-COVERAGE-1` 수정 이후 mixed-level builder와 writer의
위상·방향성 문제는 닫혔다. 대표적인 2,000-cell cylinder에서 남은 문제는
일반 boundary vertex의 `_wall_fit_snap` 이후에만 나타난다.

| 조건 | cells | max boundary skew | area deviation | bad boundary faces | 판정 |
|---|---:|---:|---:|---:|---|
| mixed ON + wall-fit ON | 1655 | 3.20865134 | 0.263700907% | 85 | `PASS_WITH_WARNINGS` |
| mixed ON + wall-fit OFF | 1655 | 0.974373881 | 15.3787224% | 0 | `FAIL` |

wall-fit 후보 496건은 모두 입력 표면까지의 거리를 줄였지만, 376건은 국소
quality regression을 동반했다. strict local-quality 비회귀는 120건,
combined p95 비회귀는 104건이었다. boundary face key는 바뀌지 않았다.
평균 표면거리는 `0.0167231→0.0007091`, p95는
`0.0490482→0.00376990`으로 개선됐다. 따라서 품질 하나만 보고 후보를
되돌리면 표면 적합성 이득을 잃으며, 표면거리 하나만 보고 수락하면 skew
영구 게이트를 넘는다.

## 2. 문헌 스크리닝 규칙

- **P0:** octree transition 또는 표면/feature 제약 아래의 직접적인 품질 복구.
- **P1:** local repair, feature provenance, constrained optimization에 직접
  재사용 가능한 방법.
- **P2:** 배경·측정·인접 문제.
- `INCLUDE`는 현재 hard surface 계약과 함께 검토할 후보, `CONTEXT`는
  메커니즘 이해용, `EXCLUDE`는 현재 범위의 생산 경로로 사용하지 않는 항목이다.
- 초록만 확인한 문헌은 `ABSTRACT_ONLY`로 유지한다. 전문을 읽기 전에는
  구현 근거로 승격하지 않는다.

## 3. 직접 후보

| 우선순위 | 판정 | 문헌 | DOI / 접근 상태 | 현재 엔진에 주는 근거 |
|---|---|---|---|---|
| P0 | INCLUDE | Elsheikh et al. (2014), *A consistent octree hanging node elimination algorithm for hexahedral mesh generation* | `10.1016/j.advengsoft.2014.05.005`, ABSTRACT_ONLY | fine/coarse 경계의 hanging-node 제거와 transition template 전처리. 현재 mixed-level coverage는 닫혔지만, 전이 면 품질을 wall-fit 전에 평가하는 순서와 연결된다. |
| P0 | INCLUDE | Chen, Yang, Sun (2026), *Edge-subdivision-based adaptive refinement for unstructured meshes with element quality control* | `10.1016/j.cja.2026.104154`, OPEN record / 전문 확인 필요 | 허용·금지 transition subdivision과 warpage/skew/aspect 품질을 함께 다루는 직접적인 계측 후보. 현재의 face-set·area·skew triple gate와 비교할 가치가 있다. |
| P0 | INCLUDE | Tong & Zhang, *HexOpt: Efficient and robust hexahedral mesh optimization using Rectified Hybrid Quadratic Jacobian and geometry-aware mapping* | `10.1016/j.cad.2026.104073`, arXiv 전문 `https://arxiv.org/abs/2410.11656`, FULL_READ | ReHQJ 품질과 geometry-aware mapping을 augmented-Lagrangian으로 결합한다. corner는 고정하고 edge/face 점은 feature와 표면 위에서 움직인다. 현재 wall-fit의 “표면거리 개선 대 cell quality” 충돌을 전역 constrained objective로 다룰 수 있는 가장 가까운 후보다. |
| P1 | INCLUDE | Shepherd et al. (2006), *Quality Improvement and Feature Capture in Hexahedral Meshes* | UUSCI-2006-029, 기관 PDF OPEN | boundary sheet를 추가해 나쁜 경계 셀에 자유도를 주고 sharp feature를 다룬다. 현재 85개가 넓게 분산된 일반 wall-fit 문제에 적용 가능한지 확인할 후보지만, topology 변경은 별도 카드다. |
| P1 | INCLUDE | Zhang & Zhao (2010), *Quality improvement method for graded hexahedral element meshes* | `10.1016/j.cagd.2010.05.003`, publisher abstract | surface quadrangle condition number, curvature-aware Laplacian smoothing, volume scaled-Jacobian을 결합한다. 표면 특성 보존과 품질을 함께 평가하는 참고선이지만 exact face-set/area 보존 여부는 전문 확인 전 미확정이다. |
| P1 | INCLUDE | Wang et al. (2015), *Hexahedral mesh smoothing via local element regularization and global mesh optimization* | `10.1016/j.cad.2014.09.003`, ABSTRACT_ONLY | local regularization과 global sparse solve를 surface constraint와 결합한다. 후보별 local regression만 보는 현재 진단을 전역 영향량으로 확장할 때 참고한다. |
| P1 | INCLUDE | Zheng et al. (2025), *Feature-aware Singularity Structure Optimization for Hex Mesh* | `10.1016/j.cad.2024.103825`, ABSTRACT_ONLY | feature line에 맞춘 sheet collapse/inflate로 multi-patch 손상을 다룬다. 현재 cylinder의 일반 wall-fit과는 다르지만 bracket형 provenance 문제에 남긴다. |
| P1 | CONTEXT | Xu et al. (2018), *Hexahedral mesh quality improvement via edge-angle optimization* | `10.1016/j.cag.2017.07.002`, author PDF `https://gaoxifeng.github.io/papers/2017/AngleBased_HexOpt.pdf` | local poor-region optimization과 inversion-free rollback의 참고 구현. 입력 표면을 변형했다가 되돌리는 단계가 있어 현재 exact surface 계약에 그대로 포팅하지 않는다. |
| P1 | CONTEXT | Huang et al. (2022), *Untangling all-hex meshes via adaptive boundary optimization* | `10.1016/j.gmod.2022.101136`, publisher abstract | boundary 제약을 일시 완화한 뒤 inversion-free 상태로 복구한다. 현 프로젝트의 surface invariant와 직접 충돌하므로 알고리즘의 단계 분리만 참고하고 생산 경로에서는 제외한다. |

## 4. 문헌 해석과 현재 계약의 차이

HexOpt은 점을 고정된 snap 위치에 묶지 않고 corner/edge/face entity에 따라
입력 표면 위에서 재투영한다. 이는 point-to-surface wall deviation은 작게
유지하지만, 현재 AutoTessell의 boundary face key, boundary area, feature
provenance 계약을 자동으로 보장하지 않는다. 그러므로 다음 두 레인을 분리한다.

1. **Frozen lane (기본):** 현재 `_wall_fit_snap`을 유지한다. 후보 수락은
   boundary face key 불변, 음수/퇴화체 증가 없음, 입력 표면거리 개선,
   기존 wall-dev와 area gate 유지, 그리고 최종 skew gate를 모두 만족해야
   한다. 후보가 하나의 지표만 개선하면 수락하지 않는다.
2. **Surface-sliding lane (opt-in 연구):** HexOpt식 entity 분류를 먼저
   적용한다. corner는 고정, feature edge는 edge 위, smooth face는 삼각
   표면 위에서만 움직인다. 매 outer iteration 후 wall-dev뿐 아니라
   boundary face key, physical area, signed-volume, determinism을 다시
   검사한다. 현재 frozen 결과보다 모든 영구 지표가 엄격히 좋아질 때만
   이후 승격을 검토한다.

현재 데이터만으로는 어느 레인도 production acceptance rule을 확정할 수
없다. 496 후보의 104건 p95 비회귀는 참고값이지, max skew·area·전역 위상
불변을 보장하는 충분조건이 아니다.

## 5. 다음 측정 카드

`HEX-WALLFIT-PARETO-1`은 구현 전 report-only로 다음을 계산한다.

1. 후보 하나씩 적용한 local 영향 셀과 전역 boundary 셀의 `Δmax_skew`,
   `Δp95_skew`, `Δwarpage`, `Δarea`, `Δwall_dev`, `Δnegative_volume`.
2. 후보를 greedy로 누적했을 때와 개별 수락했을 때의 Pareto frontier.
3. cylinder·sphere·gear·bracket에서 frontier의 형상 의존성.
4. face key와 physical area가 한 번이라도 변하면 후보를 frontier에서
   제외하는 hard invariant audit.

합격 기준은 기존 permanent gate를 완화하지 않는다. frontier가 없다면
wall-fit 수술을 강행하지 않고, transition preconditioning 또는
provenance-aware sheet 자유도 카드를 재개한다.

## 6. inaccessible DOI queue

다음 문헌은 사용자가 PDF를 제공하면 전문을 읽고 구현 근거를 재판정한다.

| 문헌 | DOI | 읽어야 할 질문 |
|---|---|---|
| Elsheikh et al. 2014 | `10.1016/j.advengsoft.2014.05.005` | transition template preconditioning이 post-snap 품질 gate로 재사용 가능한가? |
| Chen et al. 2026 | `10.1016/j.cja.2026.104154` | transition subdivision의 허용성·warpage 기준이 현재 face-set 계약과 양립하는가? |
| Wang et al. 2015 | `10.1016/j.cad.2014.09.003` | local regularization을 boundary vertex 이동 없이 적용할 수 있는가? |
| Zheng et al. 2025 | `10.1016/j.cad.2024.103825` | feature-aware sheet 조작이 patch provenance와 결정론을 보존하는가? |
| Xu et al. 2018 | `10.1016/j.cag.2017.07.002` | boundary deformation을 제거해도 local rejection objective가 남는가? |
| Qian & Zhang 2010 | `10.1007/978-3-642-15414-0_15` | multi-patch/non-manifold feature provenance 불변식은 무엇인가? |
| Ledoux & Shepherd 2010 | `10.1007/s00366-009-0145-2` | sheet insertion/extraction의 위상·결정론 안전 조건은 무엇인가? |

## 7. 포화 판정

transition template/preconditioning, constrained optimization, local smoothing,
feature-aware sheet 조작의 네 메커니즘군까지 확보되어 이 범위의 snowball은
포화로 본다. 이후는 일반 untangler를 더 찾는 단계가 아니라, 위 문헌의
전문을 확인하고 `HEX-WALLFIT-PARETO-1` 측정 결과와 대조하는 단계다.

**결론:** 현재 구현은 그대로 둔다. mixed-level은 default-OFF, wall-fit의
영구 skew `3.0` gate는 유지한다. 다음 코드 카드는 Pareto report-only
측정이며, surface invariant를 만족하는 후보가 관측될 때만 opt-in
transaction으로 승격한다.
