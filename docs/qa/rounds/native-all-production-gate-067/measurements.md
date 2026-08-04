# Measurements — native-all-production-gate-067

## Build

- Built `native_surface_bl_strip_writer`, `native_tet_bl_writer`, `native_tet_bl_authoritative_graph`, and the existing AQTE targets with CMake C++23.
- Tet build completed with two pre-existing signed/unsigned comparison warnings in `generate_authoritative` (source-face size checks); no new warning was introduced by the artifact contract.

## Actual-writer transaction matrix

| Writer path | BL | Actual writer | AQTE staged validation | writer rerun/hash parity | disk reread | publish |
| --- | ---: | --- | --- | --- | --- | --- |
| Surface wall-edge identity | 0 | PASS | PASS | PASS | PASS | PASS |
| Surface wall-edge strip | 1 | PASS | PASS | PASS | PASS | PASS |
| Tet authoritative graph bridge | 1 | PASS | PASS | PASS | PASS | PASS |

## Witnesses

- All passing rows expose a non-empty artifact schema, artifact bytes/size, writer artifact SHA-256, entity UIDs, one lineage row per UID, family quality witness, strict topology counters `duplicate=0`, `non_manifold=0`, `inverted=0`, and a positive-measure witness.
- Surface BL=1 emits `actual_layers=1`, positive `layer_work`, and roles `wall/front/side`. Surface BL=0 emits `actual_layers=0`, `layer_work=0`, and empty BL rows while retaining source-face identity and quality.
- Tet BL=1 emits three cells for the one-triangle fixture, positive signed volumes, `tet_dihedral` quality, and graph serializer/tree hashes. The same artifact hash is obtained from the independent writer rerun.
- Existing focused regression set: **27 passed** in 3.05 s. Actual-writer binding subset: **5 passed**; surface writer/bridge subset: **8 passed**; Tet writer/bridge subset: **4 passed**.

## Failure evidence preserved

- The first surface AQTE publish attempt rolled back because the test omitted `_disk` from its helper import. After importing the existing canonical disk reread helper, the same actual writer passed without changing executor behavior. This was a test defect, not a production acceptance bypass.
- A transient WSL `E_UNEXPECTED` occurred during patch/test orchestration and recovered on retry.

## Parameter note

The tested values are explicit call inputs: requested layers, Tet first height/growth/minimum volume, surface layer point IDs, normals, provenance, and writer epsilon. The transaction adapter does not rewrite them or insert defaults. Wider user-controlled parameter coverage across all native engines remains a next-round matrix item.
