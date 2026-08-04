# Next round - native-all-production-gate-066

Next card: make the actual Native Tet and surface wall-edge writers emit the complete AQTE candidate contract without Python-generated identity.

- Native Tet: C++ writer-issued cell/face UIDs, source face/edge IDs, feature/patch/physical-group/component/provenance rows, strict topology summary, signed volume/dihedral/mean-ratio/non-orthogonality/skewness witness, and staged artifact bytes.
- Surface wall-edge: C++ writer-issued face UIDs, source edge/patch/feature IDs, wall/front/side layer roles, positive area/thickness, diagonal quality decision, and persisted artifact readback.
- Run BL=0 identity and BL=1 actual artifact on cube plus sphere/NACA or another curved patch; safe refusal is valid until authority is complete.
- Fix the two signedness warnings in the Tet writer only if isolated and without changing geometry or route semantics.
- Keep Native Poly protected and then reuse the proven callback contract for Hex, Tri, Strict Quad and TRI+QUAD.

Unresolved DOI design questions remain 10.1002/nme.7644 and 10.1016/j.compfluid.2026.107032.
