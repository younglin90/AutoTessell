# CARD TTT3 (beta2095) — native_poly wall-adjacent prism extrude (helper + 호출 스켈레톤)

**target_engine**: poly
**모티프**: Garimella 2003 — voronoi BL prism extrude (시퀀스 #3)

## 이론적 근거

- TTT2b 가 식별한 wall-adjacent cell 의 boundary face 위에 inward normal × bbox_diag×0.005 step 으로 prism 1 층 삽입.
- 새 vertex = wall vertex + inward_normal × step (매우 보수적).
- prism cell = N wall vertex + N extruded vertex; faces = 1 wall face + 1 top face + N side quad.
- polyMesh `final_cells: list[list[list[int]]]` 구조에 prism cell append + `final_vertices` 확장.
- 단조 가드: max_wall_cells_to_extrude=20, n_layers=1, default flag OFF — helper + 호출 스켈레톤만 본 카드.
- 실패 시 grade 강등 → raw 채택 revert (Y2 best-of-three 가 자동 보호).
- novelty 2, rigor 3, impact 3 → 합 8.

## 변경

- 파일: `core/generator/native_poly/voronoi.py` (단일)

### 1) helper 신규 정의 (line ~170, `_ccw_sort_face_vertices` 직전)

```python
_TTT3_POLY_BL_EXTRUDE_ENABLE = False  # 본 카드: 스켈레톤만, default OFF.

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
    """wall-adj cell 의 boundary face 1 개당 prism 1 셀 추가.

    Returns: (new_vertices, new_cells) — 기존 + 신규 prism append.
    """
```

### 2) 호출 스켈레톤 (line ~741, `final_cells.append(remapped_cell)` 루프 직후, Y2 블록 진입 전)

```python
if _TTT3_POLY_BL_EXTRUDE_ENABLE and _wall_adj:
    bbox_diag = float(np.linalg.norm(V.max(0) - V.min(0)))
    final_vertices, final_cells = _extrude_prism_layer(
        _wall_adj, final_vertices, final_cells, cell_owner_seed,
        V, F, step=bbox_diag * 0.005, max_extrude=20,
    )
```

### polyMesh cells list 형식 (정확)

- `final_cells: list[list[list[int]]]`
- `final_cells[i]` = i-번째 cell 의 face list.
- 각 face = vertex index list (CCW, `_ccw_sort_face_vertices` 적용 후).
- prism cell append 형태: `[wall_face_vidx, top_face_vidx, side_quad_0, ..., side_quad_{N-1}]`.

## 검증 명령

```bash
timeout 60 python3 -c "from core.generator.native_poly.voronoi import _extrude_prism_layer; print('OK')"
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준

- 회귀 PASS
- bench ≤ 720s
- poly grade A=5/5 유지
- poly+BL fail 0
- BL 영향 없음 (flag OFF default)
