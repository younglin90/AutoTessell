# Si, Gartner - 3D Boundary Recovery by Constrained Delaunay Tetrahedralization

- DOI: `10.1002/nme.3016`
- Published: *International Journal for Numerical Methods in Engineering* 85 (2011), 1341-1364
- Status: `FULL_READ`
- Local PDF: `docs/references/tetrahedral_meshing/si_gaertner_2011_3d_boundary_recovery_cdt.pdf`

## 핵심 메커니즘

- PLS segment를 먼저 복구한다. missing segment의 diametric ball을 침범한 reference
  point와 acute/non-acute endpoint 분류를 사용해 세 가지 adaptive split rule 중
  하나로 Steiner point를 선택한다.
- 기존 segment까지 무조건 사전분할하지 않는다. 실제 missing subsegment만 split해
  Shewchuk식 고정 protecting sphere보다 불필요한 점을 줄인다.
- 모든 segment가 복구되고 general position 조건이 만족되면 facet은 boundary
  Steiner point 없이 cavity retetrahedralization으로 복구 가능하다.
- facet recovery는 missing subface region을 양쪽 cavity로 만들고, cavity 검증/확장,
  local Delaunay retetrahedralization, queue ordering으로 진행한다.
- 별도 후처리로 boundary Steiner point를 interior로 relocation하거나 제거할 수 있다.
- 실험상 segment recovery가 Steiner 수와 실행시간의 주 병목이며 facet recovery는
  상대적으로 작았다. 최악 complexity와 불필요한 split 억제는 열린 문제다.

## AutoTessell 판정

- `P0 INCLUDE`. 현재 NACA source-edge recovery와 직접 맞닿는다.
- 순서 고정: `segment recovery -> facet cavity recovery -> boundary Steiner cleanup`.
- input surface 불변식 때문에 boundary Steiner는 중간 transaction에서만 허용 가능하다.
  카드 종료 시 원본 source vertex/edge/facet identity와 면적을 모두 복구해야 한다.
- midpoint 일괄분할은 논문 취지와 반대이며, 앞선 NACA 측정의 10,953-point 폭증과도
  일치한다. reference-point 기반 adaptive split 또는 no-split cavity 경로가 필요하다.

## 다음 카드 수정

기존 `TET-SURFACE-CONSTRAINED-FLIP-ORACLE-L0` 범위를 다음처럼 좁힌다.

1. test-only planar PLC patch.
2. 원본 source segment/facet을 target constraint로 고정.
3. exact orientation/incircle 기반 crossing-edge 순서만 인증.
4. 임시 triangulation 변경 허용, 최종 source facet multiset 불일치 시 전체 rollback.
5. 제품 연결 금지. L1 cavity-lift와 boundary cleanup이 모두 통과한 뒤에만 승격.
