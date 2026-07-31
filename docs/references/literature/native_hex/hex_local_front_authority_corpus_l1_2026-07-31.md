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

## L2 corpus-metadata authority preflight

`LocalFrontCorpusAuthorityMetadataL2` now owns only three declarative fields:
an authority key, an explicit manifest order, and a source path label.  It
does not read the path, parse a sidecar, run numeric clearance, or construct a
candidate.  Its one hypothesis is narrower than the L1 geometry-adjacent
checks: one authority key and one manifest-order position must each have one
owner before downstream evidence is even eligible to run.

The canonical cube, cylinder, and sphere fixture labels establish the L2
baseline.  Reordering their caller-supplied tuple gives the same canonical
order because the audit sorts by the declared manifest order.  Duplicating the
cube key rejects `reject_duplicate_authority_key`; tying sphere's order to
cylinder rejects `reject_manifest_order_ambiguity`.  Both cases are checked
with the sidecar and numeric-preflight functions replaced by forbidden test
sentinels, so no sidecar/numeric/candidate path can be reached accidentally.
Runtime-invalid metadata is also fail-closed before any field operation:
non-string key/path and non-integral or boolean manifest-order payloads return
`reject_invalid_authority_corpus_metadata`, with every downstream flag false.

This remains `L2_TARGET_PASS / CORRECTNESS_KEEP`: metadata ambiguity is the
target-hard condition, not a geometry or target-cell claim.  Roll back if any
duplicate reaches sidecar/preflight, a caller iteration order selects an
authority, an artifact/candidate exists, production mesh state changes, or
the card enters routing/default behavior.  `third_party/` remains unchanged.

## L3 immutable source-digest preflight

`LocalFrontCorpusSourceDigestL3` binds every already-unambiguous L2 metadata
row to the canonical lowercase SHA-256 of the bytes at its declared source
path.  It streams exact bytes in fixed 1 MiB binary chunks: no STL/STEP reader,
source-geometry parse, sidecar, numeric clearance preflight, or candidate is
involved.  Thus a path
retargeted to different bytes rejects `reject_source_digest_mismatch`; a
missing path rejects `reject_source_digest_file_not_found`; malformed digest
metadata rejects before file access.  An unreadable existing path also returns
an explicit rejection rather than raising.

The canonical cube fixture is measured three times with an identical digest
report.  An altered 64-hex digest and an absent cube path are explicit
fail-closed cases.  All L3 cases use forbidden sidecar/numeric sentinels and
assert candidate, production mesh, and artifact values remain false/zero.

This is L3 report-only evidence retained as `CORRECTNESS_KEEP`; it does not
claim `L3_REGRESSION_PASS`, a local-front, topology, target-cell, routing, or
packaging result.  Roll back if byte identity can be bypassed, if source
geometry is parsed here, or if any downstream path runs.
