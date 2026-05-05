# CARD PPP4 (beta2082) — voronoi cell surface clipping (스켈레톤, 시퀀스 #1)

**target_engine**: poly
**모티프**: Yan & Wonka 2014 "Surface-aware Centroidal Voronoi Tessellation" §4 — voronoi cell 을 입력 surface 로 clip (Sutherland-Hodgman variant). Fluent Watertight Poly / Star-CCM+ Poly 의 핵심 단계.

## 이론적 근거
- 현재 native_poly 는 closed-region keep 만 수행 → boundary stair-step.
- voronoi cell 이 surface 와 교차하면 half-space intersection 으로 clip → cell 이 surface 정확 정합 (no stair-step).
- 본 카드는 시퀀스의 **첫 카드 = 스켈레톤만**: clipping helper 함수 정의 + 모듈 상수 default OFF (`_NATIVE_POLY_PPP4_ENABLE = False`). 호출 X.
- 다음 카드 PPP5 에서 활성 + best-of-N candidate 추가.
- 평가: novelty 3 (산업 표준 mesher 핵심), rigor 3 (Yan&Wonka 2014 + Sutherland-Hodgman), impact 3 (poly grade 안정 + tet/hex 영역 확장 가능) → 합 9, paper-worthy.

## 변경
- 파일: core/generator/native_poly/voronoi.py
- 위치 1 (~line 28, import 블록 뒤): 모듈 상수 추가
  - `_NATIVE_POLY_PPP4_ENABLE: bool = False  # PPP4 skeleton — clipping default OFF`
- 위치 2 (모듈 helper 영역): 새 함수
  - `_clip_voronoi_cell_by_surface(cell_verts: np.ndarray, V_surf: np.ndarray, F_surf: np.ndarray) -> np.ndarray`
  - 본문: Sutherland-Hodgman 3D 변형 — 각 surface triangle 의 평면을 half-space 로 보고 cell polygon 을 순차 clip. 정의만, 호출처 X (스켈레톤).
- 총 변경 ≤ 60줄.

## 검증 명령 (unit_tester 가 그대로 실행)
```bash
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준 (validator 가 평가)
- 회귀 PASS (full pytest 합산).
- bench 시간 ≤ 720s (현 57.8s 대비 여유).
- poly grade A=5/5 유지 (clipping 비활성 → 변화 0).
- BL 영향 없음.
- novelty/rigor/impact 합 ≥ 9.
