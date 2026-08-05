# CARD WWW6 (beta2113) — octree templating 활성 (type 식별 + log only)

**target_engine**: hex
**모티프**: Marechal 2009 §4 — templating 활성 (시퀀스 #6)

## 이론적 근거
- WWW5 의 templating helper(`_classify_cell_type`, `_TEMPLATE_PATTERNS`) 활성.
- `_WWW5_TEMPLATING = True` 토글 + hex cell 추출 경로에서 cell type 식별 + log only.
- 보수적 접근: 실제 패턴 적용은 다음 카드, 이번엔 type 분포 관측 + 단조 가드.
- 단조 가드: hex grade A=5/5 유지, bench ≤ 720s.
- novelty 3, rigor 3, impact 2 → 합 8.

## 변경
- 파일: core/generator/native_hex/octree.py
- 위치 1 (line 38): `_WWW5_TEMPLATING: bool = False` → `True`.
- 위치 2 (`_build_nlevel_cells` 내 hex 생성 루프, line ~357 부근):
  `_WWW5_TEMPLATING` 가드 하에 `_classify_cell_type(node, neighbors)` 호출 →
  type counter 누적 + structlog debug log only (default 패턴 적용 X).
- 변경 ≤ 30줄, 부수효과 없음 (log only).

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_hex.octree import _classify_cell_type, _WWW5_TEMPLATING; print('OK', _WWW5_TEMPLATING)"
timeout 90 python3 -m pytest tests/test_native_hex.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s
- hex grade A=5/5 유지 (단조 가드)
- BL 영향 없음
