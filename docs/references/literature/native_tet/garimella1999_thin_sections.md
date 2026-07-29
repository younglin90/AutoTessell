# Garimella & Shephard 1999 - Generation of Tetrahedral Meshes with Multiple Elements through Thin Sections

## 서지 및 검증

- R. V. Garimella, M. S. Shephard, *Generation of Tetrahedral Meshes with Multiple Elements through Thin Sections*, Engineering with Computers 15 (1999), 181-197.
- DOI: `10.1007/s003660050013`.
- 상태: `FULL_READ` (17/17쪽, 2026-07-27). 사용자 제공 출판본을 `papers/pdf/57_garimella_shephard_1999_thin_sections.pdf`로 보관했다.
- 시각 검증: 첫 페이지를 렌더링해 제목, 저자, 권호, 초록과 thin-section 예시를 확인했다.

## 논문의 실제 문제 정의

목표는 "얇아 보이는 형상"을 분류하는 것이 아니라, **요청한 개수 `Nt`보다 적은 요소만 존재하는 국소 thickness path**를 찾아 고치는 것이다. 시작 isotropic tet mesh에서 반대 벽까지의 edge path가 `Nt`보다 짧으면 deficient path로 취급한다. 따라서 같은 기하라도 이미 충분히 세분된 곳은 손대지 않고, 등방 refinement가 만들어 내는 접선 방향 과세분화를 피한다.

## 알고리즘에서 확인한 사실

1. 각 boundary vertex의 반대 vertex는 세 단계로 찾는다. 실제 CAD face normal 방향으로 forward search해 후보를 찾고, 반대 model face 위에서 boundary search로 가장 가까운 점을 고른 뒤, reverse search로 start-to-opposite shortest edge path를 복원한다. 저자는 이 탐색이 최적 반대점을 항상 보장하지는 않지만, 국소 후보를 효율적으로 찾도록 설계했음을 명시한다.
2. 부족한 path의 긴 edge부터 이분 split한다. boundary edge를 split한 점은 경계에 snap하되, snap 후 새 region이 invalid하면 그 split 전체를 하지 않는다.
3. split만으로는 새 deficient path, 고차 valence, 큰 face/dihedral angle이 생긴다. 그래서 opposite faces 사이를 wedge(삼각 prism)와 lateral triangulated quad로 추상화하고, diagonal triangulation을 zigzag로 바꾸는 순차 edge swap을 수행한다.
4. 이 국소 재구성에는 강한 조합적 제약이 있다. 두-layer wedge에서 세 quad의 triangulation 방향이 모두 같으면 tetrahedralization할 수 없고, 두 diagonal은 반대 방향이어야 한다. thickness 방향을 한 번에 여러 번 split하면 불가능한 wedge가 생길 수 있으므로, 저자는 **한 layer씩 split -> realign**을 반복한다.
5. wedge/quad 구조가 없거나, 유효한 중간 상태를 거쳐 diagonal->zigzag 전환을 할 수 없는 영역은 local remeshing 또는 surface-triangulation refinement가 필요하다. 논문은 어떤 국소 swap 순서도 항상 충분하지 않다는 반례를 제시한다.

## 결과와 한계

- plate 예에서는 96 -> 384 tet, worst dihedral 150 -> 96 deg가 보고되지만, ring 예에서는 144 -> 146 deg로 약간 악화됐다. 즉 through-thickness count 달성과 품질 개선은 동치가 아니다.
- pre-processing에서 반대 face의 node를 thickness 방향으로 더 정렬시키기 위해 재배치할 수 있다. 이는 AutoTessell의 pre-meshing surface hash/경계 정점 불변식과 양립하지 않으므로 그대로 이식할 수 없다.
- 일반 topological thin region, constrained surface triangulation, 다층 wedge에는 추가 remesh가 필요하다. 본문은 boundary surface를 절대 고정하는 계약이나 modern exact-predicate transaction을 제공하지 않는다.

## AutoTessell 적용 판정

`thin_disk`/`needle`은 단순 sliver-quality 카드가 아니라 coverage 문제로 진단해야 한다. 다음 후보는 구현이 아니라 report-only 측정이다.

- `TET-THIN-COUNT-1`: 입력 surface vertex/face provenance를 보존한 채, 반대 벽 후보와 shortest thickness path count의 분포를 측정한다. `Nt` 미달 영역, 탐색 실패, 비-manifold/ambiguous opposite-face를 각각 분리 보고한다.
- `TET-THIN-ALIGN-1`: 위 측정에서 명확한 wedge corridor만 대상으로, interior-only split/flip transaction이 count를 높일 수 있는지 시험한다. 각 transaction은 signed-volume, boundary face key/area, surface hash, deterministic replay를 모두 통과해야 한다.

경계 재배치, 무검증 swap, 또는 "얇음"만으로 전역 isotropic refinement를 실행하는 것은 이 근거로 승인되지 않는다.
