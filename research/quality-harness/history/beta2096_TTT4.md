# CARD TTT4 (beta2096) — native_poly BL prism extrude 활성

**target_engine**: poly
**모티프**: Garimella 2003 — voronoi BL prism extrude 활성 (시퀀스 #4)

## 이론적 근거 (≤8줄)
- TTT3 의 `_TTT3_POLY_BL_EXTRUDE_ENABLE` flag 를 True 로 전환하고 TTT2b 가 산출한
  `_wall_adj` (set[int]) 를 입력으로 `_extrude_prism_layer` 호출.
- 기존 호출부(line 762-767) 는 이미 정확한 인자 시퀀스로 작성됨 — flag 만 켜면 활성.
- max_extrude=20 으로 보수적 prism 추가 (셀 폭증 방지).
- 단조 가드: post poly grade A=5/5 유지 + n_cells_post > n_cells_pre.
- novelty 2 (BL extrude 활성), rigor 2 (재사용 helper), impact 3 (BL 통합) → 합 7.

## 변경
- 파일: `core/generator/native_poly/voronoi.py` (단일)
- 위치 1 (line 176): `_TTT3_POLY_BL_EXTRUDE_ENABLE = False` → `True`.
- 위치 2 (line 178-192): `_extrude_prism_layer` body 를 skeleton (return 그대로)
  에서 최소 동작으로 교체 — wall_cells 중 최대 `max_extrude` 개에 대해 첫 face 를
  outward normal 방향 `step` 만큼 extrude 한 prism cell append.

### 정확한 helper 시그니처 (raw, line 178-192)
```
def _extrude_prism_layer(
    wall_cells: set[int],
    vertices: "np.ndarray",         # (V,3) kept voronoi vertices (final_vertices)
    cells: list[list[list[int]]],   # cells[i] = list of faces; face = list[int vidx]
    cell_owner_seed: list[int],     # cells[i] 의 seed point index (== keep_region_indices[i])
    surface_V: "np.ndarray",        # (Vs,3)
    surface_F: "np.ndarray",        # (Fs,3) wall 삼각형
    step: float,
    max_extrude: int = 20,
) -> tuple["np.ndarray", list[list[list[int]]]]:
```

### 호출부 (line 762-767, 변경 없이 그대로 활성됨)
```
if _TTT3_POLY_BL_EXTRUDE_ENABLE and _wall_adj:
    bbox_diag = float(np.linalg.norm(V.max(0) - V.min(0)))
    final_vertices, final_cells = _extrude_prism_layer(
        _wall_adj, final_vertices, final_cells, cell_owner_seed,
        V, F, step=bbox_diag * 0.005, max_extrude=20,
    )
```

### 호출부 인자 list
1. `_wall_adj` (set[int], TTT2b line 678 산출, seed index)
2. `final_vertices` (np.ndarray (V,3), line 752 압축 vertex)
3. `final_cells` (list[list[list[int]]], line 753-760 face list)
4. `cell_owner_seed` (list[int], line 729 / 747 — kept region 의 seed idx)
5. `V` (surface_V, np.ndarray (Vs,3))
6. `F` (surface_F, np.ndarray (Fs,3))
7. `step=bbox_diag * 0.005` (float)
8. `max_extrude=20` (int)

### 핵심 변경 (≤80줄)
1. Line 176 flag → True.
2. `_extrude_prism_layer` 본체 구현:
   - `wall_seed_to_cell = {cell_owner_seed[i]: i for i in range(len(cells))}`
   - `n_added = 0`; `new_verts = [v for v in vertices]`; `new_cells = list(cells)`
   - 각 wall seed 에 대해 첫 face 를 SVD outward normal 방향으로 `step` 만큼 평행이동
     → top vertex 추가 → side quad faces + bottom + top 의 prism cell append.
   - try/except 로 감싸 실패 시 `(vertices, cells)` 원본 반환.
   - `log.info("ttt4_poly_bl_extruded", n_added=n_added)` (caller 에서)
3. caller 직후 (line 768) `n_prism_added` 변수로 길이 차이 logging 추가.

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_poly.voronoi import _extrude_prism_layer; print('OK')"
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS (tests/test_native_poly.py 전부)
- bench ≤ 720s
- poly grade A=5/5 유지
- poly+BL fail 0
- `n_prism_added > 0` (로그 `ttt4_poly_bl_extruded`)
- BL 영향 없음 (tet/hex BL 합격 분포 동등)
