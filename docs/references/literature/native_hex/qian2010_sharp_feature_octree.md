# Qian & Zhang 2010 - Sharp Feature Preservation in Octree-Based Hexahedral Mesh Generation for CAD Assembly Models

## 서지 및 검증

- Jin Qian, Yongjie Zhang, *Sharp Feature Preservation in Octree-Based Hexahedral Mesh Generation for CAD Assembly Models*, International Meshing Roundtable 19 (2010).
- DOI: `10.1007/978-3-642-15414-0_15`.
- 상태: `FULL_READ` (18/18쪽, 2026-07-27). 사용자 제공 출판본을 `docs/references/papers/source/pdf/56_qian_zhang_2010_sharp_feature_octree_hex.pdf`로 보관했다.
- 시각 검증: 첫 페이지를 렌더링해 제목, 저자, sharp curve/patch 및 two-step pillowing 초록을 확인했다.

## 파이프라인

논문은 CAD B-rep의 NURBS curve/surface를 triangulate하고, component-aware binary grid 위에서 octree isocontouring base mesh를 만든다. cell별 QEF minimizer 8개로 hex를 구성한 뒤, sharp curve와 NURBS patch를 식별하고, 마지막에 two-step pillowing 및 Jacobian optimization을 적용한다. 이는 octree transition 품질을 사후에 일반 untangler 하나로 해결한 방법이 아니라, **feature ownership을 먼저 복구한 뒤 topology를 고치는** 경로다.

## 보존 규칙

1. 정점은 critical point, curve vertex, surface vertex, interior vertex의 네 클래스로 나눈다. critical point는 고정하고, curve/surface vertex는 각각 원래 NURBS curve/patch에 투영하며, interior만 volume smoothing한다.
2. curve path를 추적할 때 두 curve가 edge segment를 공유하지 않게 한다. 세 curve가 만나는 경우에는 non-manifold point를 옮겨 분리할 수 있지만, 네 개 이상이 만나는 경우에는 기존 point를 유지하고 한 curve의 mesh path를 우회시킨다.
3. boundary quad의 patch는 non-curve vertex의 closest NURBS triangle 또는 전부 curve 위일 때 quad center로 귀속한다. assembly에서는 shared patch를 분리해 component 간 실제 공통 부분과 일치시킨다.

## Two-step pillowing의 실제 전제와 효과

- 목표는 각 hex가 boundary quad를 최대 하나만, 각 boundary quad가 sharp curve edge를 최대 하나만 갖게 하는 것이다. 이 조건을 만족하지 못하면 triangle-shaped boundary quad와 doublet가 남아 smoothing/optimization만으로 positive Jacobian을 얻기 어렵다고 보고한다.
- 1단계는 각 surface patch를 shrink set으로 pillow해 sharp curve 근처 triangle-shaped quad를 없앤다. 2단계는 전체 boundary를 pillow해 한 patch에 여러 boundary face를 가진 hex를 없앤다.
- 작은 sharp angle에서는 1단계 shrink set에서 해당 quad를 제외한다. angle을 두 번 나누면 오히려 품질이 나빠질 수 있기 때문이다.
- multi-component assembly의 common patch에서는 1단계에 한 layer가 아니라 두 layer를 동시에 넣어 shared curve의 conformity를 유지한다. 2단계에서는 새 boundary node는 표면에 두고 이전 node를 안쪽으로 옮겨 component matching을 유지한다.

## 한계와 AutoTessell 판정

- 저자도 전체 boundary 두 layer는 cell 수와 메모리를 급격히 늘린다고 보고하며, 결론에서 local refinement로의 대체를 향후 과제로 남긴다. 오래된 하드웨어에서 10,000 hex 후 pillowing 약 90초라는 수치는 현재 엔진의 성능 기준이 아니다.
- 이 방법은 NURBS/B-rep ownership과 surface sliding을 전제로 한다. AutoTessell의 frozen pre-meshing surface 계약에서는 기존 boundary vertex 이동을 그대로 허용할 수 없다.
- 따라서 `native_hex`에는 전역 two-step pillow를 이식하지 않는다. `HEX-TRANSITION-TEMPLATE1` 이전에 patch/curve/corner provenance census를 report-only로 만들고, 이후 국소 pillow 후보만 surface hash, boundary face set/area, wall_dev, positive Jacobian, cell-budget gate 아래에서 transaction으로 시험한다.
- bracket의 multi-patch 손상은 본문의 shared-patch 전략과 직접 비교할 수 있지만, paper의 quality 지표는 OpenFOAM skew가 아니다. 후보 선택은 반드시 현재 skew/wall_dev로 재측정한다.
