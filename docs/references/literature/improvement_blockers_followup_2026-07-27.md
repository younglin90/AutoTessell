# AutoTessell 개선 정체 구간 후속 문헌 조사 및 방법 카드

조사일: 2026-07-27
범위: 이번 라운드의 native_tet / native_poly / native_hex / native_tri 측정 결과 중 개선이 멈춘 항목에 대한 문헌 재검토와 다음 실험 방법 수립
원칙: 문헌의 메커니즘을 곧바로 제품 경로에 이식하지 않는다. 먼저 같은 primal/route/표면 계약으로 측정하고, 표면·위상·유한성·결정론 불변식을 통과한 작은 카드만 opt-in으로 검증한다.

## 1. 현재 정체 지점

| 엔진 | 현재 측정된 미해결 문제 | 이번 조사에서 필요한 것 |
|---|---|---|
| native_tet | 13개 hard corpus 중 6개 PASS. cylinder skew 7.04, naca whole-cell skew 34.80, thin disk 204.62, needle 559.20, micro-ridge는 입력 비-watertight/품질 실패. dual-torus와 perforated plate는 120 s timeout. | 경계 고정형 sliver/품질 최적화, thin-section 방향 사이징, CDT recovery 병목 분리 |
| native_poly | convex/non-manifold dual에서 invalid cell이 남고, fixed-primal 보정은 boundary를 바꾸지 않지만 invalidity를 충분히 줄이지 못함. 실제 native census는 upstream dual 경로가 느려 통합 측정 보류. | concave dual cell 분할과 star-shaped validity의 구조적 처리, FV 면 비평면성 보정의 분리 |
| native_hex | wall-fit은 표면 거리를 크게 줄이지만 cylinder 3.208651, sphere 14.7384, gear 27.0814, bracket 19332.7로 skew gate를 넘음. bracket의 나쁜 면은 19개 분산 성분의 단일-cell pillow 후보. | 전이 템플릿/quality-gated fallback과 surface-constrained Pareto 선택. 전역 ECR·sheet dispatch는 현재 근거 부족 |
| native_tri | scalar curvature sizing과 opt-in sizing-aware ODT relocation은 합성 corpus에서 개선됐지만 feature line/envelope/anisotropic BL 인계가 남음. | feature-aware 접선 이동, envelope/BL metric의 안전한 결합, 이후에만 parallel lane |

native_tet 중간 영구 게이트 묶음은 184 s에서 출력 없이 시간 제한에 걸렸다. 이를 회귀로 단정하지 않고, 이미 완료된 hard matrix 및 파일별 focused gate를 기준선으로 삼는다. timeout 자체는 별도 프로파일 카드로 열어 둔다.

## 2. 문헌 선별 결과

라벨은 기존 프로젝트 규칙을 따른다.

- P0: 현재 실패를 직접 설명하거나 다음 카드의 acceptance를 설계하는 데 필요한 문헌
- P1: 보조 방법 또는 실패 원인 해석에 유용한 문헌
- P2: 배경·비교용
- FULL_READ: 저장된 PDF와 완독 노트로 본문 검토 완료
- ABSTRACT_ONLY: 공식 초록/서지/공개 검색 결과까지만 검토
- EXCERPT: 공개 저장소의 본문 발췌는 확인했으나 출판본 전체는 미확보

| 분야 | 문헌 | DOI / 상태 | 판정 | 현재 코드에 주는 결론 |
|---|---|---|---|---|
| tet | Leng, Zhang & Xu 2013, Geometric Flow | https://doi.org/10.1016/j.cad.2013.05.004, FULL_READ | P0 INCLUDE | normal fairing은 표면 계약 위반. 대신 interior penalized active-set, tangent-only regularization, local flip ladder만 제한적으로 참고 |
| tet | Ni et al. 2017, Gradient-Based Shape Matching Energy | https://doi.org/10.1016/j.cagd.2017.02.004, FULL_READ | P0 INCLUDE | GSM은 inverse-height를 강하게 벌하지만 inversion barrier가 없다. AMIPS를 대체하지 말고 secondary score/rollback gate로만 시험 |
| tet | Garimella & Shephard 1999, Thin Sections | https://doi.org/10.1007/s003660050013, FULL_READ/local PDF | P0 INCLUDE | thin disk/needle은 isotropic quality 문제가 아니라 thickness 방향 element count 문제. thickness field와 through-thickness count를 먼저 측정 |
| tet | Kuprat et al. 2009, anisotropic scale-invariant tet generation | https://doi.org/10.1016/j.jcp.2008.09.030, FULL_READ/author manuscript | P0 INCLUDE | local feature-size ray와 gradient-limited anisotropic field가 thin geometry 후보. 경계 hash 고정 조건으로만 검증 |
| tet | Wang et al. 2012, feature-sensitive BCC | https://doi.org/10.1016/j.cad.2012.01.002, FULL_READ | P1 CONTEXT | 품질 보장은 있으나 원표면 근사와 sharp feature 손실을 허용하므로 기본 엔진에 직접 적용 금지 |
| tet | Hu et al. 2018, Tetrahedral Meshing in the Wild | https://doi.org/10.1145/3197517.3201353, FULL_READ/author version | P0 CONTEXT | filtered exact predicate와 단계별 validity는 참고할 만하나 fTetWild 외부 fallback의 비결정성 문제를 그대로 도입하지 않음 |
| tet | Diazzi et al., robust constrained Delaunay tetrahedralization | https://arxiv.org/abs/2309.09805, FULL_READ/open preprint | P0 INCLUDE | segment recovery가 평균 74.5%, 최대 86%를 차지한다. dual/perforated timeout은 CDT stage profile과 recovery queue/cavity 원인 분리가 우선 |
| hex | Elsheikh et al. 2014, octree hanging-node elimination | https://doi.org/10.1016/j.advengsoft.2014.05.005, FULL_READ/local PDF | P0 INCLUDE | transition preconditioning과 template 선택을 wall-fit 이후의 전역 최적화와 분리해 측정할 근거 |
| hex | Chen, Yang & Sun 2026, edge-subdivision adaptive refinement | https://doi.org/10.1016/j.cja.2026.104154, FULL_READ/local preprint | P0 INCLUDE | transition 후보를 warpage/skew/aspect로 먼저 gate하고 실패 시 isotropic/safe fallback. 단 octree-from-scratch의 drop-in template로 간주하지 않음 |
| hex | HybridOctree-Hex 2024 | https://arxiv.org/abs/2401.05984, FULL_READ/open | P0 INCLUDE | strong balance + pairing + 5 transition templates + Jacobian optimization 순서가 현재 pairing gap과 직접 연결됨 |
| hex | Qian & Zhang 2010, sharp feature preservation | https://doi.org/10.1007/978-3-642-15414-0_15, FULL_READ/local PDF | P0 INCLUDE | feature/patch provenance를 전이 및 wall-fit 후보의 소유권으로 운반하는 방법을 확인해야 함 |
| hex | Xu 2017, edge-angle optimization | https://doi.org/10.1016/j.cag.2017.07.002, FULL_READ/user PDF | P0 INCLUDE | local region + inversion-free deformation은 유용하지만 boundary relaxation을 허용한다. exact surface lane에는 tangent/feature-constrained 부분만 추출 |
| hex | Wei et al. 2015, local regularization/global optimization | https://doi.org/10.1016/j.cad.2014.09.003, FULL_READ/user PDF | P0 INCLUDE | local element regularization과 feature/normal constraint를 분리한 sparse global solve. fixed target wall-fit의 Pareto 참고용, 직접 default 적용 금지 |
| hex | Zheng et al. 2025, feature-aware singularity structure | https://doi.org/10.1016/j.cad.2024.103825, FULL_READ/user PDF | P1 INCLUDE | sheet collapse/inflation은 feature-aware지만 greedy 구조가 min SJ를 악화시키고 non-manifold에서 실패할 수 있어 bracket MATCH-3의 직접 처방으로는 부적합 |
| poly | Garimella, Kim & Berndt 2013, non-manifold polyhedral domains | https://doi.org/10.1007/978-3-319-02335-9_18, FULL_READ/excerpt | P0 INCLUDE | concave boundary에서 남는 invalid dual cell은 point relocation이 아니라 convex decomposition/다중 cell 구성이 필요 |
| poly | Kim & Chung 2015, polyhedral untangling | https://doi.org/10.1007/s00366-014-0379-5, FULL_READ/user PDF | P1 INCLUDE | local condition-number untangling은 보조 수단. topology-invalid/concave star failure를 geometry optimizer 하나로 숨기면 안 됨 |
| poly | Nishikawa 2022, FV flux correction on non-planar polyhedra | https://doi.org/10.1016/j.jcp.2022.111481, FULL_READ/author manuscript | P0 INCLUDE | 비평면 face의 FV 오차 보정은 solver adapter 카드로 분리. invalid poly cell이나 face-pairing 실패를 통과시키는 근거가 아님 |

사용자 제공 PDF인 Xu 2017, Wei 2015, Zheng 2025는 Windows Downloads에서 확인했고, 프로젝트의 docs/references/papers/source/pdf/52_*, 53_*, 54_*로 문헌 보관 체계에도 복사되어 있다. 본문·수식·제한점을 읽은 뒤, 세 논문 모두 surface movement와 품질 trade-off를 명시적으로 기록했다.

## 3. 다음 방법 카드

### 3.1 native_tet

#### TET-THIN-SECTION-1 — thickness-field census (진단부터)

Garimella–Shephard와 Kuprat의 공통 핵심을 제품 계약에 맞게 축소한다.

1. 입력 표면에서 local thickness 후보를 양방향 normal ray/closest opposing surface로 측정한다. 교차가 불안정한 곳은 unknown으로 남긴다.
2. 현재 tet primal에서 thickness 방향의 edge path와 실제 through-thickness cell count를 계산한다.
3. thin_disk, needle, naca trailing-edge에 대해 target layer 수 Nt와 현재 수를 report-only로 비교한다.
4. 이 단계에서는 점 이동·edge split·anisotropic metric 적용을 하지 않는다.

합격 기준은 surface_hash 동일, boundary face key/area 동일, 양의 signed volume, 재실행 byte-identical이다. Nt가 부족한 경우에만 다음 카드에서 thickness metric을 켠다. 단순히 skew만 낮추는 smoothing 카드는 이 진단에서 열지 않는다.

#### TET-GSM-CAVITY1 — boundary-pinned local GSM (opt-in 후보)

Ni의 GSM을 전체 mesh에 적용하지 않고, worst-quality tet 주변의 bounded cavity에만 적용한다. AMIPS와 signed-volume을 주 게이트로 유지하고 GSM은 secondary score로만 사용한다.

- 후보: interior vertex relocation 또는 이미 허용된 connectivity candidate
- reject: incident tet 중 하나라도 orientation/sign/degeneracy/boundary key/area를 위반
- accept: cavity 내 minimum quality가 악화하지 않고 GSM inverse-height score가 감소
- 비교: naca와 cylinder에서 AMIPS only / AMIPS+GSM score를 같은 후보 순서로 재생

GSM이 수치 개선을 못 보이거나 비용이 급증하면 즉시 KILL한다. GSM의 boundary resampling과 surface projection은 사용하지 않는다.

#### TET-CDT-PROFILE1 — recovery stage timing

Diazzi 결과에 맞춰 Delaunay, segment recovery, face recovery, exterior classification, Steiner insertion, cavity expansion/rollback을 각각 계측한다. dual-torus와 perforated plate는 같은 입력·같은 seed 조건에서 coarse/fine만 바꿔 측정한다. 목표는 O(n²) 추측을 하지 않고, 실제로 segment/face queue가 반복되는지 확인하는 것이다. 이 카드는 알고리즘 변경이 아니라 stage profile만 허용한다.

### 3.2 native_poly

#### POLY-CONCAVE-SPLIT1 — point relocation이 아닌 구조 분할

Garimella가 명시한 실패 클래스에만 적용한다.

1. POLY-STAR-VALID1의 signed-subtet 최소값이 음수인 cell을 수집한다.
2. invalidity가 concave boundary cap/face ring에서 생긴 것인지 분류한다.
3. concave boundary와 무관한 cell에는 split을 시도하지 않는다.
4. split 후보는 classification-consistent face를 따라 parent를 두 개 이상의 convex child로 나누고, child union volume/외부 face set/neighbor face identity를 transaction 안에서 검사한다.

invalid cell이 0이 되지 않으면 parent를 억지로 writer에 넣지 않고 원인을 STRUCTURAL_UNRESOLVED로 보고한다. surface vertex 이동은 금지한다.

#### POLY-FV-FLUX-CORR1 — solver adapter only

Nishikawa 계열의 correction은 face warpage가 존재하는 유효 poly cell에서만 측정한다. face_pairing_residual, planarity, normal spread, h, sphericity와 함께 raw flux와 corrected flux의 차수를 비교하고, dual validity gate의 결과를 바꾸지 않는다. 이것은 geometry repair가 아니라 FV truncation-error 카드다.

### 3.3 native_hex

#### HEX-TRANSITION-TEMPLATE1 — transition provenance + safe fallback

Elsheikh/Chen/HybridOctree-Hex를 합쳐도 현재 코드에 바로 template을 이식할 수는 없다. 먼저 각 전이 셀에 다음 provenance를 붙이는 진단부터 한다.

- coarse/fine level, hanging-node pattern, pairing 여부
- transition template ID와 source patch/feature/curve/corner ID
- candidate 전후 min scaled Jacobian, warpage, skew, wall deviation
- 영향을 받은 이웃 셀 수와 boundary face-set/area delta

candidate가 warpage/skew/aspect 또는 Jacobian margin을 넘으면 safe fallback을 선택하는 모의 결과를 report-only로 계산한다. fallback의 실제 mesh mutation은 별도 승인 전까지 금지한다. Chen의 tau_w=0.6, tau_s=0.75, tau_a=15는 제품 임계값으로 채택하지 않고 calibration 시작점으로만 기록한다.

현재 57개 bracket bad face가 19개 분산 성분으로 나뉜다는 측정만으로 surgery를 시작하지 않는다.

#### wall-fit Pareto 재판정

Xu/Wei 논문은 표면 거리와 품질을 단일 스칼라로 섞지 않고 local regularization, surface/feature constraint, global solve를 분리한다. 따라서 현재 496/496 거리 개선 후보를 하나의 global threshold로 자르지 않는다. 다음 실험은 feature/patch provenance별 frontier를 분리해 Δwall_dev, Δskew, Δwarpage, Δarea를 비교한다. bracket에서 provenance가 없으면 후보를 수술하지 않는다.

### 3.4 native_tri

현재 opt-in sizing-aware ODT가 세 형상에서 최소각을 개선했고 36개 focused test와 byte-identical replay를 통과했으므로, 다음은 기능 추가가 아니라 feature boundary 검증이다. Dunyach/Frey metric은 그대로 두고 feature-line 정점은 polyline 접선 성분만 허용하며, surface tangent move 뒤 exact envelope 재투영, BL proxy에서는 normal spacing 보존, 기존 rollback과 metric SPD/finite gate를 유지한다. 이 조건을 합성 fixture에서 측정한 후에만 default-on을 검토한다.

## 4. 구현 우선순위와 중단 조건

1. 먼저 TET-CDT-PROFILE1와 TET-THIN-SECTION-1: timeout/geometry 실패의 원인을 계측으로 분리한다.
2. 그 다음 POLY-CONCAVE-SPLIT1 진단: 현재 invalid cell 사례가 정말 concave boundary split 대상인지 확인한다.
3. HEX-TRANSITION-TEMPLATE1는 provenance census가 선행되어야 한다. 현재 bracket에 대해 19개 분산 성분의 57 pillow 후보만으로 surgery를 시작하지 않는다.
4. native_tri는 feature/envelope fixture를 추가하되, sizing 수식 자체는 다시 바꾸지 않는다.
5. 모든 카드의 기본값은 OFF/report-only다. 하나라도 boundary key/area, signed volume, topology, determinism을 깨면 즉시 해당 카드 전체를 롤백한다.
6. parallelization은 correctness 카드가 모두 닫힌 후 마지막에만 시작한다.

## 5. 전문 미확보 / DOI 요청 대기열

이번 라운드의 DOI 대기열은 비어 있다. Qian & Zhang 2010, Garimella & Shephard 1999, Nishikawa 2022는 2026-07-27 사용자 제공 PDF로 보관·완독했다.

참고로 아래 논문은 프로젝트 내부 PDF와 완독 노트가 있으므로 다시 받을 필요가 없다.

- 10.1007/s00366-009-0145-2 — Ledoux & Shepherd 2010, `docs/references/papers/source/pdf/28_ledoux_2010_pillowing_sheet.pdf` (15/15 `FULL_READ`)
- 10.1016/j.advengsoft.2014.05.005 — Elsheikh et al. 2014, `docs/references/papers/source/pdf/45_elsheikh_2014_octree_transition_preconditioning.pdf` (15/15 `FULL_READ`)
- 10.1016/j.cad.2013.05.004 — Leng 2013
- 10.1016/j.cagd.2017.02.004 — Ni 2017
- 10.1016/j.cad.2014.09.003 — Wei 2015
- 10.1016/j.cag.2017.07.002 — Xu 2017
- 10.1016/j.cad.2024.103825 — Zheng 2025
- 10.1007/978-3-642-15414-0_15 — Qian & Zhang 2010
- 10.1007/s003660050013 — Garimella & Shephard 1999
- 10.1016/j.jcp.2022.111481 — Nishikawa 2022

## 6. 이번 라운드의 결론

현재 개선이 멈춘 문제들은 하나의 더 강한 smoothing으로 묶이지 않는다.

- naca/cylinder는 경계 고정형 local quality/cavity 문제다.
- thin disk/needle은 thickness-aware anisotropic generation 문제다.
- dual/perforated timeout은 CDT recovery stage complexity 문제다.
- poly invalidity는 concave/star topology 문제다.
- hex wall-fit은 surface fidelity–quality Pareto 문제이며 bracket은 transition/feature provenance 부재 문제다.
- tri는 현재 scalar sizing 자체보다 feature/envelope contract가 다음 병목이다.

따라서 다음 구현 라운드의 첫 카드는 TET-CDT-PROFILE1 또는 TET-THIN-SECTION-1의 report-only 계측이어야 한다. 논문 근거가 부족한 global threshold 완화, surface movement, unguarded smoothing, sheet/ECR 전역 dispatch는 열지 않는다.
