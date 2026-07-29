# Si, Gartner - Meshing Piecewise Linear Complexes by Constrained Delaunay Tetrahedralizations

- DOI: `10.1007/3-540-29090-7_9`
- Published: 14th International Meshing Roundtable (2005), 147-163
- Status: `FULL_READ`
- Local PDF: `docs/references/tetrahedral_meshing/si_gaertner_2005_meshing_plc_by_cdt.pdf`

## 핵심 메커니즘

1. 강한 CDT 존재 조건을 만든다: local degeneracy가 없고 모든 PLC segment가
   Delaunay tetrahedralization에 존재하면 CDT가 존재한다.
2. missing segment를 세 가지 adaptive splitting rule로 복구한다. acute vertex
   주변에는 필요할 때만 protecting ball이 형성된다.
3. local degeneracy는 가능한 경우 작은 vertex perturbation으로 제거하고,
   불가능하면 break point를 추가한다.
4. missing facet region과 교차하는 tet을 제거해 양쪽 cavity를 만든다.
5. cavity boundary를 검증/확장한 뒤 각 cavity vertex의 Delaunay tetrahedralization을
   만들고 inside tet만 채운다. 이 단계는 facet Steiner point를 요구하지 않는다.

## AutoTessell 판정

- `INCLUDE` for algorithm decomposition; clean-room 구현만 허용.
- vertex perturbation은 입력 표면 보존 불변식과 충돌하므로 제품 경로에서 금지.
- segment Steiner split도 source child-chain 원장 아래에서만 허용하며, 최종 출력은
  원본 source facet identity를 복구해야 한다.
- 단순 surface diagonal flip만으로 끝내지 말고 cavity transaction의 전후
  boundary/source-face multiset을 검사해야 한다.

## 현재 카드에 미치는 영향

다음 최소 실험은 surface-only 제품 연산이 아니라 test-only oracle이어야 한다.
성공 판정: target source segment 복구, orientation 유지, 정확 source facet 복원,
결정론. 이후 별도 L1 카드에서 검증된 2D 순서를 volume cavity transaction으로 lift한다.
