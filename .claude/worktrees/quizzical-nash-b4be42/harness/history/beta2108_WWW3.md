# CARD WWW3 (beta2108) — octree surface-adjacent cell refinement (스켈레톤)

**target_engine**: hex
**모티프**: snappyHexMesh castellated step (Greenshields 2014) — 시퀀스 #3, 스켈레톤

## 이론적 근거
- WWW1 (R: balance) → WWW2 → **WWW3**: balance 후 surface 와 가까운 cell 식별 → 1 level 더 subdivide.
- snappy castellated 단계와 동일 모티프: surface 근접 cell 만 추가 refine, feature 보존.
- 본 카드는 **스켈레톤만** — 상수 `_WWW3_SURFACE_REFINE=False` + helper 정의, 호출 경로 없음.
- 다음 카드 (WWW4) 에서 `build_octree_hex_cells` 안에 통합 활성, 활성 시 후속 2:1 balance 재호출.
- novelty 3 (snappy 카피·이식), rigor 3 (level diff ≤1 보장 후 재 balance), impact 3 (feature 보존). 합 9.

## 변경
- 파일: `core/generator/native_hex/octree.py`
- 위치 1 (~line 33, `_WWW1_OCTREE_BALANCE` 인근): 상수 `_WWW3_SURFACE_REFINE: bool = False` 추가.
- 위치 2 (모듈 하단, `_balance_octree_2to1_nodes` 뒤): helper 신규 정의
  ```python
  def _refine_surface_adjacent_nodes(
      nodes: dict,
      V: np.ndarray,
      F: np.ndarray,
      max_refine: int = 20,
  ) -> dict:
      """WWW3 (beta2108) — surface 근접 cell level +1 (스켈레톤, default OFF).
      snappy castellated 모티프: cell center 와 face centroid 거리 < cell_size 인 경우 refine.
      활성 시 후속 _balance_octree_2to1_nodes 호출 필요. 호출 경로 없음 — 영향 없음.
      """
      ...
  ```

핵심 변경:
1. 상수 추가 (1 줄).
2. helper: surface triangle centroid 와 cell center 거리 비교 → level +1, max_refine 캡, level diff 보장 위해 후속 balance 호출 가정 (docstring 명시).
3. 호출 X — 스켈레톤 전용. 총 ≤30줄.

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_hex.octree import _refine_surface_adjacent_nodes, _WWW3_SURFACE_REFINE; print('OK', _WWW3_SURFACE_REFINE)"
timeout 90 python3 -m pytest tests/test_native_hex.py -q
```

## 합격 기준
- 회귀 PASS (`tests/test_native_hex.py`).
- bench 시간 ≤ 720s.
- hex grade A=5/5 유지 (스켈레톤, 호출 경로 없음 → 영향 없음).
- import 검증 OK 출력, `_WWW3_SURFACE_REFINE` False.
- BL 영향 없음, tet/poly grade 동등.
