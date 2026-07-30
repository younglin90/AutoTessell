# POLY-STAR-FAIL-CLOSED1 Evidence

Date: 2026-07-31

Pre-card baseline: `764cb4bc748a99ae8dc48e81428a3e3da28469d0`

Integration base after rebase: `364d0b68cf671227394f86f627680f311294cb1f`

Scope: residual star-validity refusal only; no geometry, topology, tolerance,
target-cell, primal-floor, routing, or `third_party/` change.

## Hypothesis and acceptance

Hypothesis: `tet_to_poly_dual` can return success and write a complete `polyMesh`
after both the Garimella candidate and centroid fallback fail the existing
signed-subtet star-validity gate.

Primary metric: false-success runs on the frozen 15-point/40-tet cube primal.

- Baseline: 3/3 false successes.
- Acceptance: 0/3 false successes.
- Rollback: any previously star-valid L0/L1 fixture changes output bytes, patch
  provenance, input arrays, or success status.

The gate threshold remains `1e-12`. The frozen failure is not threshold noise:
recorded normalized signed volumes range from about `-2.69e-5` to `-2.05e-4`.

## Baseline and result

Before the change, three identical runs each returned `success=true`, reported
`invalid_star_cells=5` and `invalid_star_subtets=25`, then wrote `points`,
`faces`, `owner`, `neighbour`, and `boundary`. All five file hashes were
identical across the three runs.

After the change, all three runs return the same explicit failure with the same
5/25 counts and identical examples/message. None of the five `polyMesh` files
exists. The primal point/connectivity digest remains unchanged.

The valid classified bipyramid still succeeds through its valid centroid
fallback. Its source patch sequence remains `source_high:wall`,
`source_low:patch`, and the permanent byte hashes remain:

- `points`: `fdab8bddd008ad6fc003427a6a153c4ae4898ddb540dee684cc2be2134a25957`
- `faces`: `e34a8b7e92d198a658ef33227d71ecbba55dba2c9c8ebd66c9db16fa297c854c`
- `owner`: `2f3f3f3e97e28db3e2c4ad74ec0b55690bb399ab97098b15d97172ae488873ca`
- `neighbour`: `8d80df3c7b13898717eb271b3913d3e577179c3f85e9441418159002f9374873`
- `boundary`: `d29e59ca7dede8b5d1b3ecd5e7858923ab3e5ca459dafcf1d8b2ebd0281d88c0`

## Primary sources and license boundary

- Garimella, Kim, and Berndt, *Polyhedral Mesh Generation and Optimization
  for Non-manifold Domains* (2013), DOI
  `10.1007/978-3-319-02335-9_18`: the generalized-dual validity test requires
  positive signed face-edge-region subtetrahedra. This is the direct algorithmic
  basis for the existing gate.
- Sorgente et al., *Polyhedral Mesh Quality Indicator for the Virtual Element
  Method* (2022), DOI `10.1016/j.camwa.2022.03.042`: star validity is a
  non-compensable factor; later quality terms cannot make a non-star cell valid.
- Sorgente et al., *A Survey of Indicators for Mesh Quality Assessment* (2023),
  DOI `10.1111/cgf.14779`: topology, geometric validity, and downstream quality
  are separate acceptance stages.
- `TommasoSorgente/vem-3D-quality-dataset` is GPL-3.0 and remains dataset/reference
  evidence only.
- `gaoxifeng/robust_hex_dominant_meshing` is MIT and supports the transactional
  topology pattern, but its published results still distinguish topology from
  geometric invalidity. It remains reference-only here.

No external source or generated artifact was copied. The control-flow fix and
fixture are independently authored.

## Verification

Fresh isolated native extension build (the pre-existing main-tree binary is not
used):

```bash
cmake -S auto_tessell_core \
  -B /tmp/autotessell-poly-star-native-5f0fe022 \
  -DCMAKE_BUILD_TYPE=Release \
  -Dpybind11_DIR=/home/younglin90/work/claude_code/AutoTessell/.venv/lib/python3.12/site-packages/pybind11/share/cmake/pybind11 \
  -DPython_EXECUTABLE=/home/younglin90/work/claude_code/AutoTessell/.venv/bin/python \
  -DBUILD_CINOLIB_HEX=OFF -DBUILD_ROBUSTHEX=OFF \
  -DBUILD_FTETWILD=OFF -DBUILD_CFMESH=OFF \
  -DBUILD_NATIVE_METRICS=OFF -DBUILD_NATIVE_BL=OFF \
  -DBUILD_NATIVE_POLYMESH=ON -DBUILD_NATIVE_SNAP=OFF \
  -DBUILD_NATIVE_SURFACE_PADDING=OFF \
  -DBUILD_NATIVE_HEX_QUALITY=OFF \
  -DBUILD_NATIVE_TET_PREDICATES=OFF \
  -DBUILD_NATIVE_TET_QOPT=OFF -Wno-dev
cmake --build /tmp/autotessell-poly-star-native-5f0fe022 \
  --target native_polymesh -j2
```

Result: fresh Release `native_polymesh` built with GCC 13.3.0. Focused command
covering the new fixture, classified boundary semantics, dual
preflight/validity, and native/Python star-validator parity:

```bash
AUTOTESSELL_EXT_BUILD_DIR=/tmp/autotessell-poly-star-native-5f0fe022 \
PYTHONPATH=. /home/younglin90/work/claude_code/AutoTessell/.venv/bin/python \
  -m pytest -q -p no:cacheprovider \
  tests/test_native_poly_star_fail_closed.py \
  tests/test_native_poly_boundary_semantics_l0.py \
  tests/test_native_poly_dual.py::test_tet_to_poly_dual_preserves_classified_multi_patch_caps \
  tests/test_native_poly_dual.py::test_tet_to_poly_dual_rejects_partial_boundary_entity_mapping \
  tests/test_native_poly_dual.py::test_tet_to_poly_dual_preserves_a_valid_integer_tet_input \
  tests/test_native_poly_dual.py::test_tet_to_poly_dual_rejects_invalid_raw_tet_input_before_writing \
  tests/test_native_poly_dual.py::test_tet_to_poly_dual_star_validity_convex_and_nonmanifold \
  tests/test_native_polymesh_extension.py::test_native_star_validity_matches_python_fallback \
  tests/test_native_polymesh_extension.py::test_native_star_validity_rejects_invalid_connectivity
```

Result: `20 passed in 2.58s`.

`black --check`, `ruff check`, focused-test `mypy --strict
--follow-imports=skip`, and `git diff --check` pass. Strict mypy on the complete
pre-existing `dual.py` reports 12 unrelated existing errors; this card adds no
new mypy diagnostic.

The full `tests/test_native_poly*.py tests/test_tier_native_poly*.py` command was
CPU-active but produced no result before the 1,204-second command timeout. A
nine-file bounded regression was likewise CPU-active until its 604-second
timeout. Both timeout wrappers left child pytest processes; each exact command
line/PID was checked before sending `TERM`. The focused result above is the
verified scope; the long sphere/cylinder/Voronoi range remains unverified by this
card.

The current main-tree `native_polymesh` binary lacks the newer
`compute_tet_dual_points` symbol even though source declares it. That stale
binary was observed only and was not used for final native parity. This card
does not delete or replace it.
