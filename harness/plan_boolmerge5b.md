# BOOLMERGE5b: native tet intersection and difference

## Scope

- Add ordered per-surface GWN masks for union, intersection, and difference.
- Preserve union wrappers and single-input behavior.
- Pass JSON-safe source paths and operation through orchestrator tier parameters.
- Fail closed for non-union classification errors.

## Acceptance

- Point-mask unit tests cover OR, AND, ordered subtraction, and validation.
- Overlapping unit cubes produce native tet intersection near 0.125 and A minus B
  near 0.875, with zero negative volumes and a passing evaluator verdict.
- Existing union E2E remains passing.
- Caller-owned tier parameters remain unchanged.

## Result

- Intersection: 58 cells, volume 0.125521003458, zero negative volumes, PASS.
- Difference: 3076 cells, volume 0.881876841268, zero negative volumes, PASS.
- Deterministic bands: intersection [0.12, 0.13], difference [0.86, 0.90].
