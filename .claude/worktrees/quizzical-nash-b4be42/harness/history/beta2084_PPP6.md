# CARD PPP6 (beta2084) — voronoi clipping 한계 확장 + degenerate guard

**target_engine**: poly
**모티프**: Yan & Wonka 2014 §4 robustness — Sutherland-Hodgman clipping 한계 확장

## 이론적 근거
- 현재 max_cells_clip=50 으로 boundary cell 50개 초과 mesh 는 clipping skip → 1/5 mesh 가 hex_fallback 의존.
- max_cells_clip 50 → 200 확장으로 mid-size mesh (50-200 boundary cells) 에서도 voronoi_clipped 채택.
- Sutherland-Hodgman degenerate plane (normal ~0, area ~0) 회피 가드 추가 → robustness ↑.
- 단조 가드: clipping 후 n_cells < 3 또는 grade 악화 시 해당 mesh 만 hex_fallback.
- novelty 1 + rigor 2 + impact 2 = 5.

## 변경
- 파일: core/generator/native_poly/voronoi.py
- 함수: `_generate_native_poly_voronoi_inner` (line ~615), `_clip_voronoi_cell_by_surface` (line ~34)
- 핵심 변경:
  1. max_cells_clip 50 → 200.
  2. `_clip_voronoi_cell_by_surface`: face normal norm < 1e-12 또는 area < 1e-14 plane skip (degenerate guard).
  3. clip 후 vertex 수 < 4 시 원본 cell 유지 (기존 동작 강화 + 로그).

## 검증 명령
```bash
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 864s
- poly grade A=5/5 유지
- voronoi_clipped 채택 4/5 유지 또는 5/5 (목표), hex_fallback 의존 ≤ 1/5
- BL 영향 없음
