# CARD TTT2b (beta2094) — voronoi BL prism wall-adjacent 활성 (시그니처 일관 재시도)

**target_engine**: poly
**모티프**: Garimella 2003 — voronoi BL prism 재시도 #1 (시그니처 일관)

## 이론적 근거 (≤5줄)
- R34 TTT2 FAIL: 호출부에서 4 인자 사용 → 정의는 3 매개변수 → TypeError.
- 본 카드는 **정의 시그니처 동일 유지**, 호출부에서 정확히 3 인자 전달.
- 활성화 효과 측정: `_TTT1_POLY_BL_ENABLE = True` 후 wall-adjacent set 크기 로깅.
- 추후 TTT3 에서 prism 삽입 → 본 카드는 helper 호출 + 로깅까지만.
- `vor.ridge_dict`, `seeds (==points)`, `F (surface_faces)` 모두 호출 시점에 in-scope.

## 변경
- 파일: `core/generator/native_poly/voronoi.py`
- 위치 1 (line 35):
  ```python
  _TTT1_POLY_BL_ENABLE: bool = False  →  True
  ```
- 위치 2 (line ~657, `keep_region_indices` 확정 직후, PPP5 clip block 진입 직전):
  호출 + 로그 1줄 추가.

### 검증된 시그니처 (raw, line 38–42)
```python
def _find_wall_adjacent_cells(
    points: "np.ndarray",
    ridge_dict: dict,
    surface_faces: "np.ndarray",
) -> set:
```

### 호출부 (정확히 3 위치 인자)
```python
# 삽입 위치: keep_region_indices 확정 후, "if clip_boundary and ..." 직전
_wall_adj = _find_wall_adjacent_cells(seeds, vor.ridge_dict, F)
log.info("ttt2b_poly_bl_wall_adj", n_wall_adj=len(_wall_adj))
```
- arg1 = `seeds` (이미 함수 내부에 있는 (N,3) 배열, points 역할)
- arg2 = `vor.ridge_dict` (scipy Voronoi 결과 attribute)
- arg3 = `F` (surface_faces, line 527 에서 정의됨)
- **인자 개수 정확히 3 — 추가 인자 금지**.

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_poly.voronoi import _find_wall_adjacent_cells, _TTT1_POLY_BL_ENABLE; print('OK', _TTT1_POLY_BL_ENABLE)"
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- import smoke OK + `_TTT1_POLY_BL_ENABLE == True` 출력.
- 회귀 PASS (tests/test_native_poly.py).
- bench ≤ 720s.
- poly grade A=5/5 유지.
- 로그 `ttt2b_poly_bl_wall_adj` 1회 이상 + `n_wall_adj > 0` (active 증거).
- BL prism 수 변화 없음 OK (실 prism 삽입은 TTT3 카드).
