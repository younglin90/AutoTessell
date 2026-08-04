# Literature review — native-all-production-gate-062

## Question

Implement

## Sources read

-

## Equations or mechanisms adopted

-

## Rejected assumptions

-

## 062 source and public-code review

- Repository plan `docs/plans/native_quality_first_boundary_layer_plan_2026-08-01.md` read: topology/shape/source/provenance and quality precede count; BL=0 identity and BL>=1 atomic all-or-rollback; wall-edge co-normal evidence; separate family gates.
- `auto_tessell_core/native_quality_witness/native_quality_witness_bind.cpp` read: current internal non-orthogonality uses `abs(dot(d, normal_vector))`, masking reversed orientation.
- `auto_tessell_core/native_tet_polymesh_quality_bind_v2.cpp` read: separate disk oracle/narrow policy; not one candidate-disk kernel.
- `core/evaluator/native_canonical_quality_witness.py` and `core/evaluator/native_quality_witness_admission.py` read: IDs derive from sorted coordinates and admission is v2/Python policy, not writer-stable complete-policy authority.
- OpenFOAM `cellQuality.C` v8 read: https://cpp.openfoam.org/v8/cellQuality_8C_source.html . Signed non-orthogonality lines 62-67/87-92 and face-intersection skewness lines 124-140/160-171. Equations only; GPL code is not copied/linked.
- OpenFOAM-dev `snappyLayerDriver.C` master read: https://raw.githubusercontent.com/OpenFOAM/OpenFOAM-dev/master/src/mesh/snappyHexMesh/snappyHexMeshDriver/snappyLayerDriver.C . GPL-3.0-or-later method reference only: transfer explicit non-manifold/feature evidence, not local silent suppression/code.
- Gmsh `BoundaryLayers.cpp` master inspected: https://raw.githubusercontent.com/live-clones/gmsh/master/src/mesh/BoundaryLayers.cpp . GPL-2.0-or-later discovery-only: source face/edge separation informs independent lineage, no code/dependency adopted.
- Fidkowski 2024 PDF read: https://websites.umich.edu/~kfid/MYPUBS/Fidkowski_2024_AIAAJ.pdf . Metric surface data, inversion control and quality precede count; it does not define all-engine provenance.
- CGAL Mesh_3 criteria docs read: https://doc.cgal.org/latest/Mesh_3/classCGAL_1_1Mesh__criteria__3.html . Explicit size/shape/features are useful but no CGAL dependency is adopted.

## Equations or mechanisms adopted

- Independently implement signed OpenFOAM-style equations with fail-closed orientation/denominator checks.
- One C++ receipt retains all entity values, partition distribution and stable worst UID; scalar summary is insufficient.
- Canonical complete policy bytes bind every UI/native value; target count remains secondary.

## Rejected assumptions

- Fixing only Tet disk `abs(dot)` is insufficient; all products need one kernel and identity contract.
- Coordinate identity, schema without common kernel, and caller summaries are not authority evidence.
- GPL OpenFOAM/Gmsh source is not copied, linked, or used as a dependency.

## Planner availability record

Requested Terra/high/priority planner was not launched: no multi-agent creation/wait API is exposed and direct spawn failed before creation. Fast-off remains lifecycle policy; no API fast field exists. No planner output is claimed and lifecycle planning is not advanced.

## Actual planner and review correction

Curie planner `019fcd34-0bb1-7f43-8b4a-e0dff6ada1cc` completed after one 900000 ms wait with `gpt-5.6-terra`, high reasoning, priority service. The planner card was to add a default-off C++23 `NativeQualityWitness/v3` using signed owner-neighbour orientation, face-centre skewness, writer-stable IDs, complete policy sealing, and candidate/disk parity. The API has no explicit `fast` field; fast-off was retained as a lifecycle policy.

The adopted mechanisms are therefore: signed `acos(clamp(dot/(norms), -1, 1))`, face-centre intersection skewness, full writer lineage rows, SHA-256 policy/authority binding, and fail-closed named refusals. The two DOI-only sources remain unreadable and are not used to set curved positive-BL release thresholds.
