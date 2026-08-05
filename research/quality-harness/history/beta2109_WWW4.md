# CARD WWW4 (beta2109) — native_hex surface-adjacent refine 활성

**target_engine**: hex
**모티프**: snappy castellated 활성 (시퀀스 #4 / Marechal 2009 §3 후속)

## 이론적 근거
- WWW3 helper `_refine_surface_adjacent_nodes` 활성화. balance 직후 surface 근접 cell level +1.
- `_balance_octree_2to1_nodes(_levels_dict)` 결과에 surface refine 적용 → 한 번 더 balance.
- `max_refine=20` 보수적 한도, level cap = `n_lev`, cell level 단조 증가.
- 단조 가드: hex grade A=5/5 유지, bench ≤ 720s, hex+BL fail 0.
- novelty 3 (snappy 모티프 활성), rigor 3 (이중 balance 안정), impact 3 (refine 구조화).
- 합 9 / 9.

## 변경
- 파일: `core/generator/native_hex/octree.py`
- 위치 1 (line 35): `_WWW3_SURFACE_REFINE: bool = False` → `True`.
- 위치 2 (line 525~528): balance 결과 `_balanced` 에 `_refine_surface_adjacent_nodes(_balanced, surface_V, surface_F, max_refine=20)` 호출 후, 결과를 다시 `_balance_octree_2to1_nodes` 로 balance → `level_3d` 갱신 (cap = `n_lev`).

### raw 시그니처 발췌 (octree.py:638-668)
```python
def _refine_surface_adjacent_nodes(
    nodes: dict,
    V: np.ndarray,
    F: np.ndarray,
    max_refine: int = 20,
) -> dict:
    if not _WWW3_SURFACE_REFINE:
        return nodes
    ...
```

### 호출부 인자 (line ~525 직후)
```python
_balanced = _balance_octree_2to1_nodes(_levels_dict)
_refined = _refine_surface_adjacent_nodes(_balanced, surface_V, surface_F, max_refine=20)
_balanced = _balance_octree_2to1_nodes(_refined)
for (i, j, k), lv in _balanced.items():
    if lv > level_3d[i, j, k]:
        level_3d[i, j, k] = np.int8(min(lv, n_lev))
```

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_hex.octree import _refine_surface_adjacent_nodes, _WWW3_SURFACE_REFINE; print('OK', _WWW3_SURFACE_REFINE)"
timeout 90 python3 -m pytest tests/test_native_hex.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s
- hex grade A=5/5 유지
- hex+BL fail 0
- import smoke `_WWW3_SURFACE_REFINE == True`
