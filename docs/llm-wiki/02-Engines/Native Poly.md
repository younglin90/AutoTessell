---
type: engine
status: active
updated: 2026-07-26
stability: working-tree
source_paths: [core/generator/native_poly/dual.py, core/generator/native_poly/harness.py, core/generator/native_poly/voronoi.py, core/generator/native_poly/patch_roles.py]
tags: [native-poly, dual, polyhedral]
---

# Native Poly

Primary native-poly harness는 다음 합성 파이프라인이다.

1. native tet mesh 생성
2. primal tet complex를 polyhedral dual로 변환
3. 선택적 dual smoothing
4. `polyMesh` 작성과 평가
5. `max_iter` 안에서 density를 조정해 재시도

## Tet-to-dual 구성

`dual.py`는 각 primal vertex fan을 dual cell로 바꾼다. Internal dual point는 tet centroid 또는 guarded Garimella placement다. Boundary component에는 source vertex, boundary-edge midpoint, boundary-face centroid가 추가된다. 공유면은 cell별 ConvexHull이 아니라 tet-edge ring으로 조립해 이웃 cell이 서로 다른 interface를 만드는 문제를 막는다.

Entity-classified 경로는 source patch/type label이나 classifier를 받아 output boundary를 source entity별로 묶는다. 좌표를 바꾸지 않고 topology/provenance를 보강한다. Non-manifold vertex fan은 connected component로 나눠 서로 끊긴 primal fan이 하나의 invalid dual cell이 되지 않게 한다.

`_star_validity()`는 dual cell의 signed subtet을 검사한다. Garimella placement가 invalid면 centroid placement로 transaction fallback할 수 있지만, placement만으로 해결되지 않는 구조적 non-manifold 사례도 evidence에 기록돼 있다.

`voronoi.py`의 SciPy Voronoi/hex-backed 경로는 legacy fallback·연구 구현이다. `smooth.py`는 interior vertex만 움직인다. 공유 checker는 planarity, normal spread, Juretić skew, characteristic length, circle ratio, sphericity, uniformity 등 FV metric을 보고한다. 현재 repair 연구는 point-placement 문제와 concave/non-manifold topology 문제를 분리하며 surface vertex 이동은 금지한다.
