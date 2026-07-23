# Si, Gaertner, Fuhrmann — Boundary Conforming Delaunay Mesh Generation (2010)

**DOI:** `10.1134/S0965542510010069`  
**Pages:** 38–53 (2010)  
**Status:** FULL_READ (user-provided PDF: `C:/Users/user/Downloads/si2010.pdf`).

## 핵심 정리

이 논문은 3D 다면체 도메인에 대한 **boundary-conforming Delaunay mesh**를 대상으로 한다.

- 경계 세그먼트/패치의 인코리지와 보호 처리 후 refinement를 수행한다.
- local feature size 기반의 segment 보호 조건이 있어 작은 각도에서 비율 제약을 완화하는 경로를 제안한다.
- finite-volume 기반의 Voronoi box 품질 동기를 사용해, 경계 정합성과 요소 품질(최소 각도/크기)을 함께 다룬다.
- 실시간 보장 자체는 입력 각도 제약(약 70.53° bound) 위주라, 실무 입력은 사전 진단이 필요하다.

## Native Tet 적용 포인트

- **PLC 경로 게이트 조건**: 최소 각도/feature bound와 경계 각도 제한을 API 계약으로 노출.
- **경계 우선 recovery**: 세그먼트/면 복원 루프에 이 논문의 인코리지+보호 아이디어를 정량적으로 반영.
- **Quality-aware refinement**: 단순 크기만 아니라 셰입/곡률 제약을 결합한 정책으로 튜닝.

## 적용/비적용 경계

- 장점: 경계 conforming에 대해 구현 가능한 출발점.
- 한계: 임의의 soup/비-PLC 입력에는 직접 적용 불가 → Wild 경로와 혼동 금지.

