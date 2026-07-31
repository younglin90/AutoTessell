# HEX-LOCAL-FRONT-AUTHORITY-CORPUS-L1-1

State: `L1_PASS / CORRECTNESS_KEEP`; report-only, default OFF.

## Purpose

`local_front_admission_l0` binds a caller-provided manifest to source-file
bytes and the reader-visible ordered triangle stream.  That is necessary but
not enough to prove how a caller acquired its labels.  This L1 corpus gate
adds an explicit, immutable classification for evidence only:

- `checked_in_fixture`: reviewable canonical test authority;
- `cad_brep`: OCP-provided face ordinal, orientation, and seam authority;
- `unknown` and `synthetic`: never authoritative, even when their byte hashes
  and entity payloads are internally consistent.

Any runtime value outside this closed authority-kind set is rejected before
sidecar parsing or preflight.  Type annotations alone are not treated as a
runtime authorization boundary.

The module only invokes existing local-front preflight after the first two
classes pass their identity checks and physical-group authority is present.
It imports no mesher, shell builder, writer, router, or output path.  It never
constructs a candidate or artifact.

## Corpus contract

| Row | Input | Sidecar result | Preflight | Claim |
|---|---|---|---|---|
| Cube | `tests/benchmarks/cube.stl` | checked-in fixture; exact file/order hash | PASS at step `0.1` | 12 source triangles, 18 manifold edges, 36 exact rows; source unchanged |
| CAD T-junction | `tests/benchmarks/t_junction.step` | B-Rep face/orientation/seam authority passes | explicit reject: physical groups unknown | 12 CAD faces, 18 CAD edges, 3,392 source triangles, 5,088 manifold edges, 1,696 entity boundaries; no BL/core-fill claim |
| Bracket | `tests/stl/03_hard_bracket.stl` | missing or fabricated synthetic sidecar | reject before preflight | no inferred feature/patch meaning; no artifact |

The T-junction STEP has no authoritative XDE physical-group names.  Its face,
orientation, and seam metadata are useful evidence, but not permission to
choose a wall patch or create a local front.  The rejection is expected and is
not a geometry or performance failure.

## Acceptance and rollback

Acceptance requires three identical reports per row, exact sidecar identity,
zero source-byte drift, zero writer/mesher calls, zero candidate construction,
and zero files below the case artifact sentinel.  Unknown/synthetic
false-admission count is zero.

Kill or roll back this card if it infers authority from geometry, lets an
unknown/synthetic sidecar reach preflight, fabricates physical groups, mutates
source arrays, writes an artifact, invokes a mesher/writer/shell, becomes a
route/default, changes target-cell behavior, or touches `third_party/`.

## Provenance

This is independent AutoTessell metadata policy.  It uses existing installed
OCP runtime APIs and local source contracts only.  No external implementation,
generated mesh, or third-party source is copied.  Ledoux and Shepherd (2010),
DOI `10.1016/j.cagd.2010.05.003`, remains conceptual support for explicit CAD
topological classification; it does not supply implementation code.

## Reproduction

```bash
/home/younglin90/work/claude_code/AutoTessell/.venv/bin/python -m pytest -q \
  tests/test_native_hex_local_front_authority_corpus_l1.py \
  tests/test_native_hex_local_front_admission_cpp23.py \
  tests/test_native_hex_cad_front_contract.py
git diff --check
```

This card establishes only L1 report correctness.  It does not claim a valid
boundary layer, local-front shell, all-hex core, physical-group preservation,
target-cell behavior, routing integration, or release readiness.
