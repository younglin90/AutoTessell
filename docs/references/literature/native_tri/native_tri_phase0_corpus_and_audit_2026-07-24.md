# Native Tri Phase 0: Corpus Design and Current-Code Audit

Date: 2026-07-24
Status: design and audit only; no benchmark implementation and no native-tri
engine output
Scope: `native_tri` Phase 0 (`TRI-CORPUS-BENCH1`, `TRI-L2-GAP-AUDIT1`, and
predicate-foundation preparation)

This document fixes the measurement contract for later native-tri work and
records the Phase 0 audit of the nearest existing implementation. It does not
add a corpus generator, benchmark runner, vendor source, or runtime predicate
integration.

## 1. Product contract to measure

Each accepted result must satisfy all applicable hard gates:

1. **Topology:** closed inputs remain watertight and two-manifold, with no
   non-manifold vertex links or duplicate/zero-length edges.
2. **Validity:** zero degenerate triangles and no orientation reversals against
   the input surface correspondence.
3. **Features:** declared corners remain pinned; declared feature polylines
   remain represented and their edge/patch identity is retained. Detection
   thresholds and the detected feature set are report fields, never hidden
   constants.
4. **Geometry:** both input-to-output and output-to-input surface distance are
   measured. A one-sided vertex nearest-neighbour distance is not a contract
   certificate.
5. **Determinism:** the canonical serialized `(vertices, faces, attributes)`
   result is byte-identical across repeated runs with the same inputs,
   configuration, and declared seed.
6. **Rejection:** an input or operation that cannot satisfy the active gates is
   explicitly rejected, and rejection returns byte-identical copies of the
   original surface plus a machine-readable reason.

The later implementation may expose draft/standard/fine error tiers, but each
run must report the active tier and whether its drift evidence is sampled,
accumulated-envelope, or shell-based. No angle result in this corpus is a
theoretical guarantee; angle values are empirical measurements.

## 2. Corpus design

The corpus is intentionally small enough for every development run, while
covering the failure modes that the literature and the product contract make
material. Each fixture must have a deterministic construction recipe, a
canonical input hash, declared feature labels, and a reference bounding-box
diagonal. The fixture files and generator are future work; this table is the
design specification only.

| ID | Geometry family | Required case | Purpose and expected audit signal |
| --- | --- | --- | --- |
| `T01` | Regular cube | Closed, six planar patches, 12 triangles | Baseline for topology, feature corners/edges, valence, and byte determinism |
| `T02` | Perturbed cube | Same cube with deterministic nonuniform face sampling | Exposes T-junctions, split-order sensitivity, and poor local edge handling |
| `T03` | Rectangular box | Three distinct edge scales | Tests scalar sizing, anisotropic demand, and vertex-budget reporting |
| `T04` | Chamfered box | Sharp edges plus small bevel patches | Separates corner pinning from degree-two feature sliding and patch provenance |
| `T05` | Triangular prism | Long protected ridge and two end caps | Tests feature-edge recall and protected-edge identity under split/collapse |
| `T06` | Low-resolution sphere | Analytic genus-zero closed surface | Baseline angle and valence improvement without declared creases |
| `T07` | Ellipsoid | Analytic smooth surface with two curvature scales | Tests curvature/sizing fields without confusing smooth curvature with features |
| `T08` | Torus | Analytic genus-one closed surface | Tests handles, vertex links, drift in concave regions, and topology preservation |
| `T09` | Thin shell | Closed thin box with thickness near the target spacing | Near-degenerate orientation, face-flip, and rejection-path stress |
| `T10` | Translated/scaled cube | T01 translated and uniformly scaled over several powers of ten | Predicate and tolerance portability; report scale-normalized and absolute values |
| `T11` | Near-coplanar valid shell | Closed shell with deliberately small but nonzero face heights | Adaptive-predicate and degenerate-triangle boundary stress |
| `T12` | Uneven shared-edge refinement | Two adjacent patches with one side pre-refined | Direct T-junction audit: every shared edge must be atomic or rejected |
| `R01` | Open shell | Cube with one face removed | Explicit input rejection; original bytes must be preserved |
| `R02` | Non-manifold edge | Three faces incident to one edge | Topology rejection and reason-code coverage |
| `R03` | Degenerate triangle | One zero-area face in an otherwise closed shell | Degeneracy rejection before any remesh operation |
| `R04` | Self-intersecting shell | Two deterministic folded/interpenetrating patches | Explicit rejection; do not silently pass a final edge-count check |
| `R05` | Non-finite input | NaN or infinity in one coordinate | Input contract and safe original preservation |

### 2.1 Fixture metadata

Every future fixture record must include:

- `fixture_id`, construction recipe/version, and input SHA-256;
- vertices/faces plus stable patch IDs and feature-polyline IDs where present;
- closed/manifold expectation, analytic surface parameters when available, and
  a declared absolute/relative drift tolerance;
- target edge lengths for `draft`, `standard`, and `fine` runs;
- a deterministic seed (or `null` for seed-free cases);
- expected disposition: `accepted`, `rejected_input`, or `rejected_budget`.

No fixture may rely on an undocumented external mesh library or an unstated
random seed. Analytic fixtures should retain their analytic surface solely as
an audit oracle; the engine input remains the triangulated surface.

## 3. Canonical measurements

The future canonical measurement script must emit one record per
`fixture × configuration × repeat`, then a summary record. Field names are
fixed here so later implementations cannot change the metric definition to
improve a result.

### 3.1 Required quality and contract fields

- `worst_min_angle_deg`: minimum of all three interior angles over all output
  triangles.
- `mean_min_angle_deg`: arithmetic mean of each triangle's minimum interior
  angle. Also report `p05_min_angle_deg` to expose the tail.
- `drift_output_to_input_max`: maximum measured output-to-input distance.
- `drift_input_to_output_max`: maximum measured input-to-output distance.
- `drift_method` and `drift_tier`: sampling schedule, accumulated envelope, or
  shell certificate; include sample count and tolerance when sampled.
- `feature_edge_recall` and `feature_edge_precision`: matching must use the
  declared feature/polyline identity, not only proximity of unlabelled edges.
- `valence_mean`, `valence_p05`, `valence_p95`, and a stable interior/boundary
  valence histogram. For closed fixtures, boundary counts must be zero.
- `input_vertices`, `output_vertices`, `input_faces`, `output_faces`, and
  `vertex_ratio`.
- `watertight`, `two_manifold`, `zero_degenerate_faces`, `zero_flipped_faces`,
  `no_self_intersections`, and `protected_features_preserved`.
- `accepted`, `rejection_reason`, and `original_preserved_sha256`.

### 3.2 Determinism and performance fields

- `result_sha256` over canonical little-endian float64 vertex bytes, int64 face
  bytes, stable face ordering, and attributes;
- `repeat_count`, `repeat_hashes`, and `byte_identical_repeats`;
- wall-clock duration after one warm-up, with median and p95 over fixed repeats;
- Python/compiler/runtime versions, CPU architecture, and WSL/Linux identity;
- peak memory only when measured by the same harness across all cases.

The benchmark budget is a report constraint, not a reason to remove a hard
gate. If a gate is too expensive, the report must name the gate and record the
degradation rather than silently replacing it with a cheaper proxy.

## 4. Proposed benchmark protocol (no implementation in Phase 0)

1. Load the canonical fixture and verify its input hash before invoking an
   engine.
2. Run a fixed configuration order and fixed traversal order. Record the
   configuration, target metric, error tier, feature threshold, and seed.
3. Preserve the input arrays before the first operation. On rejection, compare
   both arrays and their canonical hashes with the preserved copies.
4. Measure output validity, angle statistics, drift in both directions,
   features, valence, budget, and wall clock using the fields in §3.
5. Repeat the exact run at least three times in one process and once in a fresh
   process. A determinism failure is a contract failure even if quality passes.
6. Store machine-readable records beside a short human-readable summary. A
   later baseline report must identify the engine revision and must not be
   backfilled from unrecorded runs.

The Phase 0 deliverable is this design and audit document. There is no
benchmark implementation or baseline result in this change.

## 5. L2 remesh gap audit: `isotropic.py`

Audit target: [core/preprocessor/native_remesh/isotropic.py](../../../../core/preprocessor/native_remesh/isotropic.py)
and its caller-side final checks in `face.py`. The audit is read-only; no L2
code was changed.

### 5.1 What is already useful

- `isotropic_remesh` uses the literature's scalar hysteresis thresholds:
  split when `edge > 4h/3` and collapse when `edge < 4h/5`
  ([isotropic.py:443-447](../../../../core/preprocessor/native_remesh/isotropic.py:443)).
- The optional valence pass targets 6 for interior vertices and 4 for boundary
  vertices ([isotropic.py:256-306](../../../../core/preprocessor/native_remesh/isotropic.py:256)).
- Feature vertices can be locked, and explicit protected edges are carried
  through the local helpers ([isotropic.py:449-457](../../../../core/preprocessor/native_remesh/isotropic.py:449)).
- The higher-level face engine performs useful final checks and returns the
  original arrays on rejection ([face.py:251-329](../../../../core/preprocessor/native_remesh/face.py:251)).

These are useful L2 baselines, not evidence that the native-tri contract is
met.

### 5.2 Contract gaps and exact mechanisms

| Contract area | Finding |
| --- | --- |
| Transactional operators | Split, collapse, flip, and relocation are direct mutations between passes. There is no simulate-check-commit/rollback wrapper or per-operation topology, orientation, feature, or drift gate. |
| Shared-edge conformity | `_split_edges_above` chooses only the longest edge of each face from a one-pass snapshot ([isotropic.py:100-132](../../../../core/preprocessor/native_remesh/isotropic.py:100)). The midpoint cache makes a shared edge conforming only when both incident faces select it; when only one selects it, the neighboring face is left unsplit and a T-junction can result. The shared edge is not an atomic two-face transaction. |
| Collapse legality | `_collapse_edges_below` orders short edges and averages endpoints, but has no link condition, one-ring validity test, self-intersection test, normal/fold-over guard, or boundary policy ([isotropic.py:141-218](../../../../core/preprocessor/native_remesh/isotropic.py:141). It removes repeated-index faces after the merge, which is a cleanup step rather than a topology certificate. |
| Flip legality | `_flip_edges_to_improve_valence` accepts a flip solely when the four-vertex valence deviation decreases ([isotropic.py:270-306](../../../../core/preprocessor/native_remesh/isotropic.py:270)). It does not test the new diagonal, duplicate edges, link condition, orientation, fold-over, or local envelope. Protected-edge exclusion is not a general feature-patch transaction. |
| Relocation safety | `_tangential_relocate` moves vertices toward a face-neighbour centroid ([isotropic.py:309-361](../../../../core/preprocessor/native_remesh/isotropic.py:309). The direct path can run with `project_to_surface=False`; the optional projection snaps to the nearest original vertex rather than a certified closest point. Exceptions in the projection path are swallowed. Neither path has a pre-commit gate. |
| Sizing | The engine accepts one scalar `target_edge_length` ([isotropic.py:415-447](../../../../core/preprocessor/native_remesh/isotropic.py:415). `face.py` adjusts that scalar using feature-vertex fraction and an optional predictor ([face.py:224-246](../../../../core/preprocessor/native_remesh/face.py:224)); it does not implement the shared per-vertex metric algebra, curvature source metric, or metric intersection contract. |
| Feature semantics | `_detect_feature_verts` uses a scalar dihedral threshold and locks every endpoint of a sharp edge ([isotropic.py:364-412](../../../../core/preprocessor/native_remesh/isotropic.py:364). There is no provenance-owning skeleton, corner-versus-degree-two distinction, protected feature polyline, or exact on-polyline sliding. |
| Predicates | Geometry decisions use float64 norms, crosses, dot products, and equality/threshold tests. No Shewchuk or indirect predicate is used by this module. |
| Drift/provenance | The final face audit estimates distances by projecting output vertices and triangle centers to a candidate set of original triangles ([face.py:287-295](../../../../core/preprocessor/native_remesh/face.py:287)). It is a final sampled/proxy check, not a two-sided accumulated envelope or static shell, and it carries no source-face/barycentric provenance. |
| Final topology checks | `face.py` derives watertight/manifold status from edge incidence only ([face.py:271-275](../../../../core/preprocessor/native_remesh/face.py:271). This does not certify vertex links or self-intersection freedom. Flips and degeneracy are checked only after the whole operator loop ([face.py:297-323](../../../../core/preprocessor/native_remesh/face.py:297), not per operation. |
| Determinism | No byte-identical repeat-run test or stable result hash exists for this path. Edge collection uses a set before sorting by length ([isotropic.py:170-183](../../../../core/preprocessor/native_remesh/isotropic.py:170); projection candidate ties use `argpartition` ([face.py:123-145](../../../../core/preprocessor/native_remesh/face.py:123)). These choices require an explicit determinism audit rather than an assumption. |
| Rejection behavior | `native_face_remesh` does preserve original arrays when its final gates fail, but the lower-level `isotropic_remesh` returns whatever arrays the loop produced and has no explicit rejection result or reason. |

Conclusion: `isotropic.py` is a useful scalar, preprocessing-grade L2 baseline
for `TRI-L2-GAP-AUDIT1`. It is not the native-tri product engine and must not
be used as evidence for the Phase 1 transactional or Phase 3 provenance
contracts.

## 6. Predicate build hygiene and existing verification

The local Shewchuk bundle is the public-domain reference implementation in
`core/utils/_shewchuk/predicates.c`, wrapped by `wrapper.c`. Its lazy compile
command in
[`core/utils/_shewchuk/__init__.py:47-55`](../../../../core/utils/_shewchuk/__init__.py:47)
now includes `-ffp-contract=off`; this was absent before Phase 0. No indirect
predicate source was added and no runtime path was connected.

Checks run in WSL Ubuntu:

```text
python3 -m py_compile core/utils/_shewchuk/__init__.py \
  core/utils/predicates.py core/utils/predicates_exact.py \
  core/utils/predicates_staged.py \
  core/preprocessor/native_remesh/isotropic.py
pytest -q tests/test_shewchuk_predicates.py tests/test_predicates.py \
  tests/test_predicates_insphere.py tests/test_predicates_staged.py
```

Result: `38 passed in 3.59s`.

The existing tests exercise the bundled direct predicates and staged fallback;
they do not prove the full compiler/rounding-mode contract, the exponent-range
precondition, indirect predicates, or native-tri operator gates.

## 7. Attene 2020 `Indirect_Predicates` availability and license audit

### Local finding

No `Indirect_Predicates` source tree, license file, submodule, package, or
runtime reference is present in this workspace. The local
`Feature-Preserving-Octree-Hex-Meshing/extern/geogram/src/bin/fpg` and related
FPG paths are Geogram code, not the Attene repository. The only local Attene
artifacts found are the paper note and PDF:

- [`attene2020_indirect_predicates.md`](attene2020_indirect_predicates.md)
- `papers/pdf/39_attene_2020_indirect_predicates.pdf`

### Upstream availability

The upstream public repository is
`https://github.com/MarcoAttene/Indirect_Predicates`. It is a header-only C++
library with a test program and CMake build; the README documents Linux/g++,
Windows/MSVC, and macOS/Clang testing. It has no published release, so any
future vendor operation must pin a commit and record a source hash.

The repository README requires strict floating-point handling: GCC/Clang
`-frounding-math -O2` plus an explicit SSE2/AVX2/ARMNEON target. Its CMake file
uses C++20, `-O3`, `-frounding-math`, and by default AVX2 plus FMA. A future
native integration must separately audit contraction, fast-math, rounding-mode
restoration, architecture dispatch, and the repository's SIMDE fetch behavior.

### License finding and disposition

The repository identifies its license as **GNU LGPL 2.1 or later** and credits
Marco Attene / IMATI-GE / CNR (copyright 2019). This is compatible with a
reference-only investigation, but it is not a no-obligations public-domain
drop-in: bundling or modifying the header-only library requires preserving
notices/license and satisfying the applicable LGPL source/relink requirements.
Legal packaging and a pinned commit are prerequisites to vendoring.

Disposition for Phase 0: **availability confirmed; license recorded; do not
vendor or connect to runtime in this task**. The paper's class-2 implicit
point scope and its snap-rounding limitation remain design inputs for a later
predicate card, not current implementation claims.

Sources:

- Paper DOI: <https://doi.org/10.1016/j.cad.2020.102856>
- Author post-print: <https://arxiv.org/abs/2105.09772>
- Upstream repository and README: <https://github.com/MarcoAttene/Indirect_Predicates>
- Upstream license: <https://raw.githubusercontent.com/MarcoAttene/Indirect_Predicates/master/LICENSE>
- Upstream build settings: <https://raw.githubusercontent.com/MarcoAttene/Indirect_Predicates/master/CMakeLists.txt>
- Shewchuk predicate source page: <https://www.cs.cmu.edu/~quake/robust.html>

## 8. Explicit non-scope and change boundary

- No benchmark implementation, fixture generator, benchmark output, or
  baseline numbers were added.
- No Attene source was downloaded, copied, built, or connected to runtime.
- `core/preprocessor/native_remesh/isotropic.py` and all native_hex/native_poly
  files were left untouched.
- No commit was created.
