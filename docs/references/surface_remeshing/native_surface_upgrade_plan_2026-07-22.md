# Native Surface Meshing Upgrade Plan

Date: 2026-07-22

Scope: `core/preprocessor/native_remesh`, surface-only dispatch, 3D surface export,
wall-edge boundary-layer support, and focused surface remesh tests.

Status note: the current root worktree is dirty and root `autoresearch-results/` contains
legacy state. Do not initialize surface autoresearch in root. Create a clean common
scaffold branch, commit metric drivers there, then create one isolated worktree per lane.

## Decision

Split the surface product into two native engines:

- `native_tri`: feature-preserving triangular remesh for CFD/FEA-ready surface quality.
- `native_quad_dom`: field-aligned quad-dominant remesh for wall-edge-aligned layers and
  future hex-dominant volume seeding.

Both are 3D surface mesh engines. They do not generate volume cells. A separate export
adapter may pad an axis-aligned planar surface into a thin OpenFOAM volume case.

## Hard Contracts

1. Surface-only output: no volume mesh creation or volume-engine fallback.
2. Closed input remains watertight and manifold unless explicitly rejected.
3. Open or non-manifold input is either repaired with recorded topology changes or rejected
   with byte-preserved input.
4. Degenerate faces, flipped faces, duplicate faces, and zero-length edges are forbidden.
5. Feature edges are detected from dihedral angle, boundary/patch edges, and user wall-edge
   selections. Feature constraints survive split, collapse, flip, smoothing, and projection.
6. Geometry drift is bounded by a scale-normalized surface envelope.
7. Wall-edge boundary layers are applied only to semantic wall edges, not by name alone.
8. AI predictors are advisory only. Native deterministic gates decide acceptance.
9. All copied code must pass a license check. MIT/BSD-compatible code can be ported with
   attribution; GPL or unclear-license code is algorithm reference only unless the whole
   distribution policy changes.

## Literature And Source Choices

### Native Tri

Adopt a PMP/Botsch-Kobbelt style local-operator loop:

- split long edges,
- collapse short edges,
- flip for valence and angle quality,
- tangential smoothing,
- projection to the original surface envelope.

PMP documents this exact remeshing structure and sharp-feature preservation through
feature edge/vertex properties. PMP is MIT licensed, so small C++ ports are acceptable
with attribution.

Feature constraints must be propagated through topology edits:

- feature/wall/boundary edge flip forbidden,
- feature-edge split allowed only along the same feature chain,
- collapse allowed only inside compatible feature classes,
- new vertex provenance and feature tags copied deterministically,
- feature vertices projected back to the original segment or curve.

Use Geogram concepts for sizing-field quality rather than direct dependency first:

- Local Feature Size driven density,
- CVT/RVD smoothing for later high-quality isotropic remesh,
- normal-lift anisotropic remesh only after native tri gates are stable.

Geogram is BSD-3-Clause, compatible for reference/porting with attribution.

### Native Quad Dom

Use Instant Field-Aligned Meshes as first practical architecture:

- orientation field,
- position field,
- feature snapping,
- local smoothing operator,
- quad-dominant extraction.

Instant Meshes is BSD-style licensed. Port only the minimal field/solver structure needed
for a headless native engine.

Use QuadriFlow as algorithm reference for scalable robust quadrangulation, especially
global singularity cleanup. Verify license before any code copy; if incompatible or unclear,
do not copy.

Use libigl/MIQ ideas for cross-field and seamless parametrization references. libigl is
MPL2, so direct source inclusion has file-level obligations; prefer clean-room port of
small algorithms or isolated optional adapter.

Use Cinolib for mesh data-structure patterns and validity utilities. Cinolib is MIT
licensed and supports triangle, quad, polygon, tet, hex, and poly meshes.

### AI Layer

MeshCNN is useful for edge-level classification and feature/wall-edge prediction, not as
the primary mesher. The first AI target is:

- predict protected feature/wall-edge probabilities,
- feed probabilities into deterministic sizing/feature constraints,
- never bypass native validity gates.

MeshCNN code is MIT licensed, but it is Python/PyTorch. For this C++-preferred product,
keep it optional and advisory until a native inference path exists.

## Common Scaffold

Create this as one committed bootstrap before lane initialization:

- `core/surface_mesh/model.py`: ragged polygon connectivity with `face_offsets` and
  `face_vertices`, face type, provenance, and semantic edge roles.
- `core/surface_mesh/quality.py`: shared tri/quad surface gates and canonical hash.
- `core/surface_mesh/boundary_band.py`: wall-edge advancing strip model.
- `core/surface_mesh/native_tri/`: feature-preserving tri local-operator engine.
- `core/surface_mesh/native_quad_dom/`: quad-dominant recombination and later field path.
- `core/evaluator/surface_checker.py`: surface-only checker.
- `auto_tessell_core/native_tri_surface_bind.cpp`: C++ core candidate target.
- `auto_tessell_core/native_quad_dom_surface_bind.cpp`: C++ core candidate target.
- `scripts/bench_native_surface.py`: deterministic JSON metric driver.
- `tests/surface_mesh/corpus/`: fixed no-BL and edge-BL fixtures.

STL cannot preserve quads. `native_quad_dom` canonical artifacts must use OBJ or PLY.

## Engine Metrics

### `native_tri` metric

Metric: `passing_cases`. Higher is better. Target: `16`.

Corpus:

- triangulated sphere,
- distorted closed cylinder or duct,
- sharp-feature box/bracket,
- open/non-manifold reject fixture,
- mixed wall/non-wall edge fixture.

Case pass gates:

- non-manifold output,
- degenerate/flipped triangle,
- feature-edge drift beyond envelope,
- min angle below threshold,
- edge-length dispersion above threshold,
- unexpected accept/reject behavior,
- nondeterministic output over two runs,
- wall-edge BL applied to non-wall edge.

First experiment:

`TRI-OPLOOP1`: add deterministic feature-preserving split/collapse/flip/smooth order and
strict rollback when a move violates topology, envelope, or feature constraints.

Guard:

```bash
python3 -m pytest -q tests/test_native_face_remesh.py tests/test_surface_mesh_contract.py
```

### `native_quad_dom` metric

Metric: `passing_cases`. Higher is better. Target: `16`.

Corpus:

- smooth genus-0 closed surface,
- CAD-like bracket with sharp feature edges,
- duct/cylinder with wall-edge BL request,
- noisy scan-like mesh,
- open/non-manifold reject fixture.

Case pass gates:

- no quad-dominant evidence,
- invalid/non-manifold output,
- feature edge not represented,
- excessive geometry drift,
- wall-edge BL semantic violation,
- poor quad valence/singularity report missing,
- nondeterministic output over two runs.

First experiment:

`QUAD-FIELD1`: implement headless field-aligned extraction scaffold: feature edge graph,
orientation/position field placeholders with deterministic smoothing, and a guarded
quad-dominant extraction path that rejects instead of emitting bad quads.

Guard:

```bash
python3 -m pytest -q tests/test_native_face_remesh.py tests/test_surface_mesh_contract.py
```

## Autoresearch Commands

Run only after the scaffold commit exists and the baseline is measured twice.

Native tri:

```bash
python3 /mnt/c/Users/user/.codex/skills/codex-autoresearch/scripts/autoresearch.py init \
  --repo /home/younglin90/work/claude_code/AutoTessell-native-tri \
  --goal "Make native_tri pass all fixed 3D surface and wall-edge BL cases" \
  --scope core/surface_mesh/native_tri \
  --scope auto_tessell_core/native_tri_surface_bind.cpp \
  --metric-name passing_cases --direction higher \
  --verify "python3 scripts/bench_native_surface.py --engine native_tri --json-stdout" \
  --metric-key passing_cases --target 16 \
  --guard "python3 -m pytest -q tests/test_native_face_remesh.py tests/test_surface_mesh_contract.py" \
  --max-iterations 40
```

Native quad dom:

```bash
python3 /mnt/c/Users/user/.codex/skills/codex-autoresearch/scripts/autoresearch.py init \
  --repo /home/younglin90/work/claude_code/AutoTessell-native-quad-dom \
  --goal "Make native_quad_dom pass all fixed quad-dominant and wall-edge BL cases" \
  --scope core/surface_mesh/native_quad_dom \
  --scope auto_tessell_core/native_quad_dom_surface_bind.cpp \
  --metric-name passing_cases --direction higher \
  --verify "python3 scripts/bench_native_surface.py --engine native_quad_dom --json-stdout" \
  --metric-key passing_cases --target 16 \
  --guard "python3 -m pytest -q tests/test_native_face_remesh.py tests/test_surface_mesh_contract.py" \
  --max-iterations 40
```

## Worker Rules

- Work in isolated clean worktrees only.
- Do not edit root worktree during autoresearch.
- `gpt-5.6-sol` planner writes cards first.
- `gpt-5.6-terra` medium workers run one focused hypothesis per iteration.
- Each `finish` uses the `codex-autoresearch` controller; failed trials are reverted by it.
- Validator checks raw metric logs, diffs, guard logs, and output artifacts.

## Sources

- PMP remeshing: https://www.pmp-library.org/remeshing.html
- PMP repository/license: https://github.com/pmp-library/pmp-library
- Geogram remeshing: https://github.com/BrunoLevy/geogram/wiki/Remeshing
- Geogram license: https://raw.githubusercontent.com/BrunoLevy/geogram/main/LICENSE
- Instant Meshes: https://github.com/wjakob/instant-meshes
- Instant Meshes license: https://raw.githubusercontent.com/wjakob/instant-meshes/master/LICENSE.txt
- QuadriFlow: https://github.com/hjwdzh/QuadriFlow
- MeshCNN: https://github.com/ranahanocka/MeshCNN
- Cinolib license: https://raw.githubusercontent.com/mlivesu/cinolib/master/LICENSE
- Botsch-Kobbelt remeshing DOI: https://doi.org/10.2312/SGP/SGP04/189-196
- Dunyach curvature remeshing DOI: https://doi.org/10.2312/conf/EG2013/short/029-032
- Instant Meshes DOI: https://doi.org/10.1145/2816795.2818078
- QuadriFlow DOI: https://doi.org/10.1111/cgf.13498
- Blossom-Quad DOI: https://doi.org/10.1002/nme.3279
- MeshCNN DOI: https://doi.org/10.1145/3306346.3322959
- Surface advancing-layer paper needing download if deeper detail is required:
  https://doi.org/10.1016/j.compfluid.2026.107032
  and https://doi.org/10.2514/6.2020-0902
