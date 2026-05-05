# CARD PPP3 (beta2081) — voronoi algorithmic preference (hex_fallback 의존 ↓)

**target_engine**: poly
**모티프**: Lévy 2010 §5 + 자체 — Lp CVT 의 algorithmic preference (voronoi > hex_fallback hybrid)

## 이론적 근거

- 산업 polyhedral mesher (Fluent Watertight Poly, Star-CCM+ Poly) 는 순수 voronoi 기반.
  hex_fallback hybrid 는 알고리즘적으로 권장되지 않음.
- 현 best-of-N score 는 grade letter 만 사용 → grade A 끼리 동등 → tie-break 시 cell 수 많은
  hex 선호 경향.
- voronoi candidate 가 grade A 인 경우 hex_fallback 보다 우선 채택해야 알고리즘 정통성 유지.
- Δ score: voronoi 류 +0.5 bonus (grade letter score 외 추가).
- tie-break 우선순위: voronoi(p=4) > voronoi(p=2) > hex_fallback.
- novelty 1, rigor 2, impact 2 → 합 5.

## 변경

- 파일: core/generator/native_poly/voronoi.py
- 함수: best-of-N candidate 채택 로직 (line ~196, ~210, ~222, ~249)
- 핵심 변경:
  1. candidate tuple 에 type_priority (p4=2, p2=1, hex=0) 추가.
  2. voronoi 류 score 에 +0.5 bonus 가산 (grade A 동률 시 voronoi 우선).
  3. sort key: (score+bonus, type_priority, n_cells) 내림차순.

## 검증 명령

```bash
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준

- 회귀 PASS
- bench 시간 ≤ 720s
- poly grade A=5/5 유지
- voronoi 채택률 ↑ (chosen=voronoi(p=4) or voronoi(p=2) ≥ 1 케이스)
- BL 영향 없음
