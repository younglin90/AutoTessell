# CARD PPP1 (beta2079) — native_poly Lp CVT 스켈레톤 (p=2 default)

**target_engine**: poly
**모티프**: Lévy & Liu 2010 "Lp Centroidal Voronoi Tessellation" — 진정한 voronoi grade A 도달 위한 Lp CVT 통합 (시퀀스 #1, 스켈레톤)

## 이론적 근거

- 현 native_poly grade A=5/5 는 hex_fallback 채택 결과 — 진짜 voronoi 후보는 grade D 수준.
- 현 `_lloyd_3d_iteration` 은 L2 (균일 평균) isotropic Lloyd. 산업 poly mesher (Fluent/Star-CCM+) 는
  Lp CVT (p>2) 로 anisotropic energy 최소화 → cell 형상 균질화 + worst quality 향상.
- 시퀀스 계획:
  - **PPP1 (이 카드, 스켈레톤)**: `lp_p` 파라미터 추가, p=2 면 기존 동작 (회귀 0). 분기 로직만 삽입.
  - PPP2: p=4 또는 metric weighting 활성. voronoi 후보 grade C→B 목표.
  - PPP3: anisotropy tensor 도입. grade B→A 목표.
- novelty 2, rigor 3, impact 3 → 합 8.
- native_tet saturation (worst mq 0.055 stable) 으로 엔진 회전 — round 14 는 poly 시퀀스 시작.

## 변경

- 파일: `core/generator/native_poly/voronoi.py`
- 함수: `_lloyd_3d_iteration` (line ~87) + 호출부 (line ~401)
- 핵심 변경:
  1. signature 에 `lp_p: float = 2.0` 추가 (default 기존 동작 보장).
  2. centroid 계산부 (line ~133) 분기 추가: `if lp_p == 2.0: centroid = vor.vertices[region].mean(axis=0)` (기존) else: placeholder — 현재는 fallback to mean 으로 회귀 0 보장. 다음 카드 (PPP2) 에서 Lp weighted centroid 활성.
  3. 호출부 `_generate_native_poly_voronoi_inner` (line ~401) 에서 `_lloyd_3d_iteration(seeds, V, F, n_lloyd, lp_p=2.0)` 명시 전달 (스켈레톤 hookup).
  4. structlog `native_poly_lloyd_done` log 에 `lp_p=lp_p` 키 추가 (관측성).

## 검증 명령

```bash
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준

- 회귀 PASS (test_native_poly 전부 동등).
- bench 시간 ≤ 720s (현 57s 충분 여유).
- poly grade A=5/5 유지 (lp_p=2.0 default → 기존 동작).
- voronoi 후보 mq 분포 동등 (스켈레톤이므로 변화 없음 검증).
- BL 영향 없음.
