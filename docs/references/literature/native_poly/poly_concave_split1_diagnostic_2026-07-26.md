# POLY-CONCAVE-SPLIT1 진단 — 2026-07-26

## 범위

Lee 2015의 concave-edge conical decomposition을 참고한 report-only 진단이다. dual point placement, geometry, solid gate, production route는 변경하지 않았다.

## 재현 결과

| 항목 | 결과 |
|---|---|
| fixture | `tests/test_native_poly_dual.py`의 inline non-manifold fan |
| historical invalidity | `2 invalid cells / 18 invalid subtets` |
| witness | `cell=2`, `edge=(4,0)` |
| normalized signed volume | `-5.2618125539e-05` |
| concave faces | `0`, `5` |
| non-manifold primal edge | `(0,1)`, tet `0,1,2`의 3-owner fan |
| patch provenance | synthetic `fixture_wall`만 있음; source CAD/entity map 없음 |
| geometric conical candidate | `true` |
| transactional split feasibility | `blocked` |
| surface vertex change | 없음 |

## 해석

문헌의 기하 후보 조건은 만족한다. 그러나 non-manifold primal fan과 synthetic-only provenance 때문에 child topology와 patch ownership을 승인할 수 없다. 따라서 이번 카드는 concave split 구현으로 승격하지 않는다. 실제 source patch/entity provenance를 가진 fixture와 transactional neighbor-topology 계약이 먼저 필요하다.

근거: [Polyhedral Mesh Generation and A Treatise on Concave Geometrical Edges](https://doi.org/10.1016/j.proeng.2015.10.131).

## 검증 상태

- Fixture level: **L0_PASS**. The inline fixture is deliberately synthetic and
  non-manifold; it is a regression witness, not a supported CAD geometry.
- Promotion state: **CORRECTNESS_KEEP**. The script only reads/reconstructs
  candidates in memory. It does not alter routing, acceptance, point placement,
  the solid gate, or any produced mesh.
- Determinism: `test_native_poly_concave_split.py` builds the census twice and
  requires byte-equivalent JSON after normalization. It also pins the historical
  `2 / 18` invalid count, the current fan-component `0 / 0` reference result,
  and the conservative `blocked_pending_provenance_and_transactional_topology`
  decision.
- Next decision: retain `STRUCTURAL_UNRESOLVED` for this class. Open a split
  implementation card only after a manifold concave-boundary fixture carries
  source entity provenance and supplies a transactional child-union,
  exterior-face-set, and neighbour-face-identity contract.

## 재현

```text
python3 scripts/diagnose_native_poly_concave_split.py --json
```

bounded assertion은 통과했다. 이 카드는 진단 전용이며 production 변경과 커밋은 별도 승인 후 진행한다.
