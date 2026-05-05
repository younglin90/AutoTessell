# CARD TTT8 (beta2111) — poly BL n_layers 1 → 2 (multi-layer extrude)

**target_engine**: poly
**모티프**: Garimella 2003 — multi-layer prism BL (시퀀스 #8)

## 이론적 근거
- 현재 `_extrude_prism_layer` 1회 호출 = 1 layer 만 생성.
- 1st layer 의 extruded wall vertex 는 새 wall surface 를 형성 → 동일 normal 보존 가능.
- 2nd layer 호출: wall 기준을 1st 결과로 갱신, step_2 = step_1 × 1.5 (expansion ratio, 산업 표준).
- 보수적: layer 2 만 추가 (3+ 는 후속 카드).
- 단조 가드: poly grade A=5/5 유지, n_cells > pre.
- novelty 1, rigor 2, impact 2 → 합 5.

## 변경
- 파일: core/generator/native_poly/voronoi.py
- 함수: `_extrude_prism_layer` 호출부 (line ~821)
- 핵심 변경:
  1. 1st layer 호출 후, extruded vertex 를 새 wall vertex 로 하는 `_wall_adj_2` 재구성.
  2. 2nd `_extrude_prism_layer` 호출 (step = bbox_diag * 0.005 * 0.95 * 1.5).
  3. 2nd layer 실패/품질 저하 시 1st 결과로 revert (grade 가드).

## 검증 명령
```bash
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s
- poly grade A=5/5 유지
- n_prism_added ≥ 1st 단독 결과 (대략 2× 또는 동등)
- BL 영향 없음 (BL 합격 분포 동등)
