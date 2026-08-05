# CARD TTT1 (beta2093) — native_poly BL 통합 시퀀스 #1 (스켈레톤)

**target_engine**: poly
**모티프**: Garimella 2003 + 자체 — voronoi cell 의 wall-adjacent 식별 helper (BL prism 층 사전 준비)

## 이론적 근거
- 현 native_poly 수치 100% 는 hex_fallback 의존도 높음 — 순수 voronoi BL 미검증.
- TTT 시퀀스: (#1) wall-adjacent helper 스켈레톤 → (#2) prism 층 삽입 → (#3) stitch.
- 본 카드는 default OFF helper 만 추가 — 회귀 영향 0.
- Rule 2 escape: SSS envelope relocation (R31/R32 -0.027) abandon, poly 우선순위로 rotate.
- novelty 2, rigor 2, impact 3 → 합 7.

## 변경
- 파일: core/generator/native_poly/voronoi.py
- 핵심 변경:
  1. 모듈 상수 `_TTT1_POLY_BL_ENABLE = False` 추가 (top-level, import 직후).
  2. helper `_find_wall_adjacent_cells(points, ridge_dict, surface_faces)` 정의 — wall 면을 공유하는 voronoi cell 인덱스 set 반환. 호출처 없음.
  3. docstring 에 시퀀스 계획 명시 (TTT1 → TTT2 prism → TTT3 stitch).

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_poly.voronoi import _find_wall_adjacent_cells, _TTT1_POLY_BL_ENABLE; assert _TTT1_POLY_BL_ENABLE is False; print('OK')"
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS (poly grade A 5 유지)
- bench 시간 ≤ 720s
- helper import 성공, default OFF
- 영향 없음 (스켈레톤이므로 mq/grade 동등)
