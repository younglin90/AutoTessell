# TRI-CURV-SIZING-CPP23-1 evidence

Date: 2026-07-31

Promotion target: `L1_PASS / EXPERIMENTAL_KEEP`

Mechanism: exact-result-preserving C++23 port of the existing scalar curvature
sizing transaction.  No routing, geometry, topology, threshold, or dependency
change.

## Primary literature

- Marion Dunyach, David Vanderhaeghe, Loic Barthe, and Mario Botsch,
  *Adaptive Remeshing for Real-Time Mesh Deformation*, Eurographics 2013 Short
  Papers, DOI
  [10.2312/conf/EG2013/short/029-032](https://doi.org/10.2312/conf/EG2013/short/029-032).
  The official Eurographics record and four-page PDF were accessible and read.
  It supplies the existing curvature target
  `L = sqrt(6 epsilon / kappa - 3 epsilon^2)`, conservative endpoint sizing,
  and split/collapse/flip/smooth loop.  It does not provide a Hausdorff,
  topology, or feature-preservation theorem; those remain independent hard
  gates.  This card reimplements only the already-adopted sizing census.
- Charles Dapogny et al., *An open-source platform for the generation of 3D
  meshes of complex domains*, 2014, local full-read note
  [`dapogny2014_mmg.md`](dapogny2014_mmg.md).  Its MMGS curvature sizing and
  staged adaptation support separating sizing from guarded topology edits, but
  its local non-accumulated Hausdorff check is weaker than AutoTessell's source
  preservation contract.  No algorithm or code was copied.

No paper required by this card was inaccessible.

## Active public implementation review

Repository heads were read with `git ls-remote` on 2026-07-31.  These projects
are references only; none is a dependency and no source was copied.

- [geometry-central](https://github.com/nmwsharp/geometry-central), head
  `019669ddabda05e0f71fa3587cfb3c1dadf19cb8`, MIT.  Current remeshing docs
  expose curvature-adaptive target lengths and a mutation manager for guarded
  edits.  Useful independent design evidence: dense element data and mutation
  guards.  Not reused because this card needs only a flat-array census.
- [MmgTools/mmg](https://github.com/MmgTools/mmg), head
  `8ed2259164fa4c90be6301d247ecb1db7bd61228`, LGPL-3.0/GPL-3.0 repository.
  MMGS is an active production surface-adaptation reference.  Its code and
  generated output stay outside the future MIT-native-core boundary.
- [CGAL](https://github.com/CGAL/cgal), head
  `50817efa5a133536fbbd1aa247d5f6b08dc0e9d7`, current official manual 6.2.
  `Meshing and Remeshing of Polygon Meshes` is GPL (or commercial CGAL terms),
  and its documented isotropic loop protects constraints only when explicitly
  configured.  No code or dependency was adopted.

## Frozen baseline and hypothesis

Fixture: deterministic `260 x 260` sinusoidal grid, `67,600` vertices and
`134,162` triangles, Python 3.12, GCC 13.3 release build, one warmup, median of
three runs.

Reproduce after building `native_metrics` in release mode:

```bash
PYTHONPATH=. AUTOTESSELL_EXT_BUILD_DIR=<release-build> \
python3 tests/stl/bench_native_tri_curvature_sizing.py --size 260 --repeats 3
```

- Python oracle median: `5.387563420 s`.
- Hypothesis: contiguous face arrays, one `3F` edge-record buffer, deterministic
  sort/run incidence, compact face-normal/area arrays, and one reserved output
  remove Python dictionaries, lists, scalar NumPy dispatch, and per-edge heap
  objects while preserving the existing operation order.
- Primary acceptance: native kernel at least `3x` faster.
- Rollback: any source mutation, branch-class mismatch, downstream
  connectivity/provenance/hash change, non-finite output, malformed-output
  acceptance, nondeterminism, or strict-build warning.

## Result

- Native median: `0.058511802 s`; speedup `92.08x`.  A post-rebase repeat
  measured `5.427369961 / 0.058733531 s` (`92.41x`) with the same hashes.
- Grid output SHA-256 is identical:
  `124113bd63712c8a6414f5a0d04bb1100bf72f4afb2273f6ebaac332f8077e5b`.
- Icosphere Python/native maximum absolute difference:
  `1.0130785099704553e-15`; min/interior/max branch classifications match.
- Three native repeats have identical output hashes.  Source vertex and face
  hashes remain unchanged.
- Frozen cube operator transaction preserves report sequence, connectivity,
  coordinates, and ordered source arrays exactly.  Output face SHA-256:
  `35f0279bb703ab37558344968699fde685c59e016d8d8614b4166d5cf3159c2f`;
  output vertex SHA-256:
  `95d76c3638af9a972ba7fe272745aa6b108735c913d9f32800daefd0e06b4036`.
- Zero-area and non-manifold-edge oracle semantics are frozen.  This kernel
  reports sizing only; it does not repair, accept, or emit a mesh artifact.

The retained primitive is independent first-party C++23.  Python remains the
oracle and extension-absent fallback.  Direct ABI accepts only exact
C-contiguous `float64 (N,3)` and `int64 (M,3)` arrays; malformed native output
fails closed in the Python wrapper.
