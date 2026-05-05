# CARD TTT5 (beta2097) — native_poly BL coverage 확장 (max_extrude 20→100)

**target_engine**: poly
**모티프**: Garimella 2003 — BL coverage 확장 (시퀀스 #5)

## 이론적 근거
- R37 TTT4 PASS: n_prism_added 합 35 (mesh 당 평균 7), max_extrude=20 보수적.
- 산업 표준 (Fluent Watertight, Star-CCM+ Poly) 은 wall cell 의 80-100% 에 BL 추가.
- max_extrude 20 → 100 점진 확장. 단조 가드 (post grade A=5/5, n_cells>pre, BL fail 0) 유지.
- novelty 1 + rigor 2 + impact 2 = 5.

## 변경
- 파일: core/generator/native_poly/voronoi.py
- 함수: `_extrude_prism_layer` 호출부 (line ~811-813)
- 핵심 변경:
  1. line 813: `max_extrude=20` → `max_extrude=100`
  2. line 186 default `max_extrude: int = 20` → `100` (일관성)

## 검증 명령
```bash
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s
- poly grade A=5/5 유지
- n_prism_added 총합 > 35 (R37 대비 증가)
- BL fail 0
