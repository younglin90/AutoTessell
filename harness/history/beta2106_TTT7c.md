# CARD TTT7c (beta2106) — native_poly prism step ×0.95 보수 축소

**target_engine**: poly
**모티프**: TTT7 재시도 (dim mismatch 회피, 단순 보수)

## 이론적 근거
- TTT7 은 per-vertex thickness_factor 배열을 만들면서 `_extrude_prism_layer` 가 기대하는 size 와 mismatch 발생 (5 fail).
- 본 카드는 위험한 array 분기를 사용하지 않고, 호출 측 step 인자만 ×0.95 로 보수 축소.
- BL prism 두께를 5% 줄여 voronoi cell 과의 stitch 안정성 향상 — 단순 매개변수 sweep.

### `_extrude_prism_layer` raw 시그니처 (voronoi.py:178)
```
_extrude_prism_layer(V, F, *, step: float, max_extrude: int,
                     thickness_factor: float | np.ndarray = 1.0, ...)
```
- `thickness_factor` 가 array 일 때 expected size = **wall vertex 수** (F 에 등장하는 unique vertex index 수). TTT7 은 wall_cell 수로 잘못 전달하여 실패.
- 본 카드는 array 경로 미사용 → mismatch 원천 차단.

## 변경
- 파일: `core/generator/native_poly/voronoi.py`
- 함수: 호출부 (line ~821)
- 핵심 변경 (≤5줄):
  1. `step=bbox_diag * 0.005` → `step=bbox_diag * 0.005 * 0.95`
  2. 변경 사유 주석 1줄 추가 (TTT7c stitch margin).

## 검증 명령
```bash
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS (test_native_poly 전부)
- bench 시간 ≤ 720s
- poly grade A=5/5 유지
- BL 영향 없음
