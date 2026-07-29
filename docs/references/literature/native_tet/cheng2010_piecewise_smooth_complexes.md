# Cheng, Dey, Ramos - Delaunay Refinement for Piecewise Smooth Complexes

- DOI: `10.1007/s00454-008-9109-3`
- Published: *Discrete & Computational Geometry* 43 (2010), 121-166
- Status: `FULL_READ`
- Local PDF: `docs/references/tetrahedral_meshing/cheng_dey_ramos_2010_delaunay_refinement_piecewise_smooth_complexes.pdf`

## 핵심 메커니즘

- 입력은 정점, 곡선 1-face, smooth surface patch 2-face로 구성된 PSC다.
- 새 non-vanishing local feature size와 Lipschitz 성질로 sharp curve/vertex 주변
  protecting ball 크기와 배치를 정한다.
- protecting ball을 weighted point로 바꾸고 restricted weighted Voronoi/Delaunay
  refinement를 수행한다. 이후 삽입점은 protecting ball 내부에 들어가지 않는다.
- 연속 weighted point 사이 curve는 restricted Delaunay edge chain으로 유지된다.
- topological-ball-property 위반, normal variation, triangle shape를 refinement
  사건으로 사용한다.
- 종료 시 입력과 출력의 homeomorphism, weighted-vertex triangle radius-edge bound,
  normal deviation, 일부 dihedral-angle bound를 보장한다.

## AutoTessell 판정

- `CONTEXT`, 즉시 제품 이식 대상 아님. NACA는 이미 triangulated PLC이고 최초
  표면의 정점/edge/facet identity를 보존해야 한다. 논문은 smooth patch를 위상적으로
  근사하며 weighted protection을 전제로 한다.
- 재사용 가능 요소: feature-size 측정, sharp-feature protection, no-insertion zone,
  topological-ball-property 진단.
- 금지: 이 근거만으로 경계점을 이동하거나 원본 facet을 다른 triangulation으로
  바꾸는 것.

## 현재 카드에 미치는 영향

`TET-SURFACE-CONSTRAINED-FLIP-ORACLE-L0`은 geometry/patch 보존만 검사하면 부족하다.
최종 acceptance에 원본 source segment와 source facet identity의 정확 복원을 포함해야 한다.
