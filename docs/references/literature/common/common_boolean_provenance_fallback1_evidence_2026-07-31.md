# COMMON-BOOLEAN-PROVENANCE-FALLBACK-1 Evidence

Date: 2026-07-31

Baseline: `68c3bfd184852d26fe9308617511ca4a9bd2a852`

Scope: generator tier-order policy for multi-input Boolean strategies only. No
meshing algorithm, geometry, tolerance, target-cell, boundary-layer,
orchestrator, dependency, or `third_party/` change.

## Hypothesis and acceptance

Hypothesis: after the selected native Boolean tier fails, the generic fallback
chain can report success even though those tiers do not implement the active
multi-input source/patch provenance contract. The same route has also reached
unsafe MeshPy and Netgen failure modes.

Primary metric: provenance-incompatible fallback attempts after a forced
`tier_native_tet` Boolean failure.

- Baseline: 2/2 configured generic fallbacks attempted per run; the first can
  declare the pipeline successful.
- Acceptance: 0/2 generic fallbacks attempted; the selected native failure is
  returned truthfully; output artifacts remain zero.
- Rollback: any single-input fallback-order change, successful selected native
  Boolean result change, provenance loss, generic fallback invocation, or
  `third_party/` change.

## Result

When `tier_specific_params.boolean_input_paths` is truthy, the generator now
uses exactly one explicit selected tier. `union`, `intersection`, and
`difference` each attempt only `tier_native_tet` in the forced-failure fixture.
Neither MeshPy nor Netgen is invoked, and `constant/polyMesh` is absent.

An invalid direct Boolean strategy with `selected_tier=auto` makes zero tier
attempts rather than constructing a provenance-incapable generic chain. The
normal single-input explicit strategy retains its exact selected tier plus two
fallbacks. A successful selected native Boolean attempt retains the same
`TierAttempt`, route, selected tier, and one-attempt execution summary.

The focused route suite passed three consecutive runs with the same six test
outcomes. No new inaccessible DOI was found.

## Primary sources and license boundary

- Zhang et al., *Interface preserving mesh optimization method for
  multi-material simulations* (Journal of Computational Physics, 2025), DOI
  `10.1016/j.jcp.2025.114389`: material interfaces and region constraints are
  part of the physical model; losing them can create mixed or inconsistent
  cells. Publisher/author manuscript read.
- Chen et al., *MIND: Material Interface Generation from UDFs for Non-Manifold
  Surface Reconstruction* (NeurIPS, 2025), DOI
  `10.48550/arXiv.2506.02938`: multi-label region partition and topology are
  explicit extraction contracts. The official `jjjkkyz/MIND` repository is
  MIT-licensed and was used as reference only.
- Garimella, Kim, and Berndt, *Polyhedral Mesh Generation and Optimization for
  Non-manifold Domains* (2013), DOI `10.1007/978-3-319-02335-9_18`: exterior
  boundaries and material interfaces require exact entity classification.
- `elalish/manifold` is an Apache-2.0 C++ reference. Its documented input IDs,
  material mapping, and surface properties illustrate that robust Boolean
  output and provenance are coupled contracts. It was not added as a
  dependency.
- Gmsh and OpenFOAM are GPL references only. CGAL `Labeled_mesh_domain_3` is
  GPL/commercial reference only. Their code was not copied.

The policy and tests are independently authored. No external code, generated
mesh, or dependency was copied into the native-core candidate.

## Verification

Environment for all commands:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=.
```

Focused command:

```bash
python -m pytest -q -p no:cacheprovider tests/test_generator.py \
  -k 'boolean_contract or boolean_selected_tier or explicit_tier_follows_fallback_chain'
```

Result: `6 passed, 131 deselected`; repeated three times with identical test
outcomes.

Complete generator-file regression:

```bash
python -m pytest -q -p no:cacheprovider tests/test_generator.py
```

Result: `127 passed, 8 skipped, 2 failed` after this card's additional tests.
Both failures are pre-existing, untouched WildMesh expectations: the draft
quality fixture expects `stop_quality=20` while implementation returns `10`,
and the axis-section hole fixture reports `usable_count=0` instead of `3`.

Boolean-family bounded regression excluding the three expensive volume E2E
cases produced `11 passed, 5 failed, 3 deselected`. The five failures are
pre-existing cross-lane contract mismatches in untouched files:
`SourceSurfacePatchClassifier` signature, native-hex source patch naming, and
native-poly Boolean keyword support.

Focused strict mypy for `core/generator/pipeline.py` passes. The complete files
have pre-existing Black/Ruff debt; the Black diff for this card's changed
regions was applied manually without mass-formatting unrelated code.
