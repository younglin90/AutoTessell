# CARD WWW1 (beta2102) — native_hex octree 2:1 balance 시퀀스 스켈레톤

**target_engine**: hex
**모티프**: Marechal 2009 §3 — octree 2:1 balance (시퀀스 #1, 스켈레톤, default OFF)

## 이론적 근거
- 현 native_hex `octree.py` 에 `_apply_2to1_balance` 가 이미 존재하나 hex 셀 출력 직전 단계에 한정.
- snappy castellated / cfMesh 는 **node-level octree** (refinement level dict) 자료구조에서 2:1 balance 후 templating.
- 본 카드 (스켈레톤): node-level helper `_balance_octree_2to1_nodes(levels: dict) -> dict` 신규 정의 + 모듈 상수 `_WWW1_OCTREE_BALANCE = False` 추가. 호출 경로 미연결 → 영향 없음.
- 다음 카드 (WWW2) 에서 build_octree_hex_cells 내부 활성화.
- novelty 3, rigor 3, impact 2 → 합 8.

## 변경
- 파일: core/generator/native_hex/octree.py
- 함수: 모듈 최상단 + 새 helper (파일 하단)
- 핵심 변경:
  1. 모듈 상수 `_WWW1_OCTREE_BALANCE: bool = False` 추가 (모듈 헤더 영역).
  2. 신규 helper `_balance_octree_2to1_nodes(levels: dict[tuple[int,int,int], int]) -> dict[tuple[int,int,int], int]` 정의 — BFS 큐로 26-이웃 leaf level diff > 1 인 셀 split (level += 1) 까지 반복; default OFF 이므로 호출처 없음.
  3. private 유지 (export 갱신 없음, import 가능만 확인).

## 검증 명령 (unit_tester 가 그대로 실행)
```bash
timeout 60 python3 -c "from core.generator.native_hex.octree import _balance_octree_2to1_nodes, _WWW1_OCTREE_BALANCE; print('OK', _WWW1_OCTREE_BALANCE, _balance_octree_2to1_nodes({(0,0,0):0}))"
timeout 90 python3 -m pytest tests/test_native_hex.py -q
```

## 합격 기준 (validator 가 평가)
- 회귀 PASS (1328+ tests).
- bench 시간 ≤ 720s (스켈레톤, default OFF → 변동 없음).
- hex grade A=5/5 유지.
- BL 영향 없음.
- import 성공 + helper 가 단일 노드 입력에 대해 동일 dict 반환.
