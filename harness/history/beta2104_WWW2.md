# CARD WWW2 (beta2104) — native_hex octree 2:1 balance 활성

**target_engine**: hex
**모티프**: Marechal 2009 §3 — octree 2:1 balance 활성 (시퀀스 #2)

## 이론적 근거
- WWW1 에서 `_balance_octree_2to1_nodes(levels)` helper 도입했으나
  `_WWW1_OCTREE_BALANCE = False` 로 호출 차단 상태.
- 본 카드: 플래그 True + `build_octree_hex_cells` 의 기존
  `_apply_2to1_balance` (grid 6-이웃) 결과를 dict 변환 → node helper 로
  한 번 더 통과시켜 26-이웃 (face+edge+corner) 2:1 보장.
- 기존 grid balance 는 6-이웃만 처리 → corner/edge 인접 비균형 누락 가능.
  node helper 가 보강.
- 매우 보수적: 이미 6-이웃 balance 입력 → 추가 split 은 코너 케이스만.
- 단조 가드: hex grade A=5/5 유지, fail 0, bench ≤ 720s.
- novelty 3, rigor 3, impact 2 → 합 8.

## 변경
- 파일: `core/generator/native_hex/octree.py`
- 위치 1 (line 32): `_WWW1_OCTREE_BALANCE: bool = False` → `True`.
- 위치 2 (line 515 다음, `_apply_2to1_balance` 호출 직후):
  ```python
  if _WWW1_OCTREE_BALANCE and n_lev > 1:
      _levels_dict = {
          (int(i), int(j), int(k)): int(level_3d[i, j, k])
          for i in range(nfx) for j in range(nfy) for k in range(nfz)
          if fine_inside_3d[i, j, k] and level_3d[i, j, k] > 0
      }
      _balanced = _balance_octree_2to1_nodes(_levels_dict)
      for (i, j, k), lv in _balanced.items():
          if lv > level_3d[i, j, k]:
              level_3d[i, j, k] = np.int8(min(lv, n_lev))
  ```

## Raw 시그니처 발췌 + 변수 매핑
- helper (line 554):
  `def _balance_octree_2to1_nodes(levels: dict[tuple[int,int,int], int]) -> dict[tuple[int,int,int], int]`
- 호출 context (`build_octree_hex_cells`):
  - `nfx, nfy, nfz: int` = fine grid 셀 수
  - `fine_inside_3d: np.ndarray (bool, shape=(nfx,nfy,nfz))`
  - `level_3d: np.ndarray (np.int8, shape=(nfx,nfy,nfz))`
  - `n_lev: int` = finest level cap
- cap `min(lv, n_lev)` 으로 finest 초과 방지.

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_hex.octree import _balance_octree_2to1_nodes, _WWW1_OCTREE_BALANCE; print('OK', _WWW1_OCTREE_BALANCE)"
timeout 90 python3 -m pytest tests/test_native_hex.py -q
```

## 합격 기준
- 회귀 PASS (전체 pytest)
- bench 시간 ≤ 720s
- hex grade A = 5/5 유지
- hex+BL fail 0
- import check 출력 `OK True`
