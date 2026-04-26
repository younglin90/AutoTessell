# CARD TTT6 (beta2105) — poly BL prism thickness adaptive 스켈레톤

**target_engine**: poly
**모티프**: Loseille 2013 §4 — BL prism thickness adaptive (시퀀스 #6, 스켈레톤)

## 이론적 근거
- 현 `_extrude_prism_layer` 의 thickness (`step`) 가 글로벌 fixed.
- 산업 mesher (cfMesh, snappy addLayers) 는 collision/curvature 기반 local thinning 적용.
- 본 카드: per-prism `thickness_factor` kwarg 추가, default 1.0 (기존 동작 보존).
- 다음 카드 TTT7 에서 collision-based local thinning 활성.
- novelty 2, rigor 3, impact 2 → 합 7.

## 변경
- 파일: core/generator/native_poly/voronoi.py
- 함수: `_extrude_prism_layer` (line ~178)
- 핵심 변경:
  1. 시그니처에 `thickness_factor: float | "np.ndarray" = 1.0` kwarg 추가 (max_extrude 다음).
  2. 내부 extrude offset 계산 시 `step` → `step * factor_i` (factor_i = scalar 또는 per-face 배열 lookup).
  3. docstring 에 thickness_factor 의미 1줄 추가, 호출부 (line 811) 변경 없음 (default).

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_poly.voronoi import _extrude_prism_layer; import inspect; assert 'thickness_factor' in inspect.signature(_extrude_prism_layer).parameters; print('OK')"
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s
- poly grade A=5/5 유지
- n_prism_added 동등 (스켈레톤 — 동작 변화 없음)
- BL 합격 분포 동등
