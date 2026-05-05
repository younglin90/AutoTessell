# CARD PPP5 (beta2083) — native_poly surface clipping 활성 + clipped candidate

**target_engine**: poly
**모티프**: Yan & Wonka 2014 §4 — Restricted Voronoi via surface clipping (시퀀스 #2)

## 이론적 근거

PPP4 에서 정의된 `_clip_voronoi_cell_by_surface` (Sutherland-Hodgman 변형) 를
default OFF → ON 전환. 위험 통제 위해 **boundary cell 만** clipping 시도하고
`max_cells_clip=50` 가드. clipping 결과는 **별도 candidate** `voronoi_clipped(p=2)` 로
best-of-N 에 추가하여 기존 voronoi(p=2)/voronoi(p=4)/hex_fallback 와 score 경쟁.
기대: boundary 근처 cell 손실률 ↓ → n_cells ↑, grade 동등 또는 우세.
실패해도 voronoi(p=4) 후보가 우세 채택 → 회귀 없음.

novelty 3 / rigor 3 / impact 3 = 합 9.

## 변경
- 파일: core/generator/native_poly/voronoi.py (단일, ≤80줄)
- 변경 1 (line 31): `_NATIVE_POLY_PPP4_ENABLE: bool = False` → `True`.
- 변경 2 (`_generate_native_poly_voronoi_inner`, region 추출 ~line 575~590):
  신규 kwarg `clip_boundary: bool = False` 추가. True 일 때 boundary 후보 region
  (vertex 일부가 bbox padding 밖) 만 골라 `_clip_voronoi_cell_by_surface` 호출.
  - 가드: `max_cells_clip=50`, try/except 로 무한 loop/예외 차단,
    빈/degenerate 결과 시 원본 cell_verts 유지.
- 변경 3 (best-of-N, line ~279 부근, voronoi(p=4) 블록 다음):
  `voronoi_clipped(sd=cur_seed)` 후보 추가 — `lp_p=2.0, clip_boundary=True`.
  - type_priority=3 (highest), `_VORONOI_BONUS` 적용.
  - 실패 시 silent skip + log.warning("native_poly_ppp5_skipped", ...).
- sort key 는 기존 (score, prio, n_cells) 유지 — prio=3 자동 우선.

## 검증 명령
```bash
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS (test_native_poly.py 전수 통과).
- bench 시간 ≤ 864s (기존 720s × 1.20, clipping overhead 허용).
- poly grade A=5/5 유지 또는 우세 (퇴보 시 FAIL).
- best-of-N 채택 로그에 `voronoi_clipped` 출현 ≥ 1 케이스 (활성 증거) 또는
  voronoi(p=4) chosen 동률 시 회귀 없음.
- BL 영향 없음 (BL 합격 분포 동등).
