# CARD WWW5 (beta2110) — octree cell templating 스켈레톤

**target_engine**: hex
**모티프**: Marechal 2009 §4 — octree cell templating (시퀀스 #5, 스켈레톤)

## 이론적 근거
- 2:1 balanced octree 의 leaf cell 은 face/edge 에서 인접 cell 의 분할 차이에 따라
  서로 다른 transition pattern 을 요구 (8-hex, pyramid+hex, 2-hex split 등).
- Marechal templating 은 26 cell type 패턴 dict 으로 분류 후 각 type 별
  pre-defined hex subdivision 적용.
- 본 카드는 스켈레톤만: cell type 분류 helper + 빈 패턴 dict 정의, 호출 경로 없음.
- WWW6+ 에서 실제 templating 활성화. novelty 3, rigor 3, impact 2 → 합 8.

## 변경
- 파일: core/generator/native_hex/octree.py
- 핵심 변경:
  1. 모듈 상수 `_WWW5_TEMPLATING: bool = False` 추가.
  2. helper `_classify_cell_type(node, neighbors) -> str` 정의 (face neighbor level
     diff 기반 26 type 분류, default 'uniform').
  3. `_TEMPLATE_PATTERNS: dict[str, list] = {}` 빈 dict 정의 (WWW6 채울 자리).

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_hex.octree import _classify_cell_type, _WWW5_TEMPLATING, _TEMPLATE_PATTERNS; print('OK', _WWW5_TEMPLATING, len(_TEMPLATE_PATTERNS))"
timeout 90 python3 -m pytest tests/test_native_hex.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s (스켈레톤, 호출 없음)
- hex grade 동등 (A=5 유지), BL 영향 없음
