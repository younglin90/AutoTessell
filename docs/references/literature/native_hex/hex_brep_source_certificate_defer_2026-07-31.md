# Hex Gate 4 B-Rep source-certificate feasibility — 2026-07-31

## Card state

`DEFER / CORRECTNESS_KEEP`.  This is report-only evidence.  No reader,
mesher, routing, threshold, acceptance, or product behavior changes.

## Reader evidence

`core/analyzer/readers/step.py` preserves a deterministic *input-side* B-Rep
triangle certificate:

- authoritative `triangle_face_ordinals`, `triangle_orientation_reversed`,
  `seam_vertex_ids`, `canonical_vertex_source_ids`, and
  `oriented_canonical_faces`;
- authority flags `face_ordinals_authoritative`,
  `face_orientation_authoritative`, and `seam_connectivity_authoritative`;
- SHA-256 values for ordered triangle coordinates, face ordinals, orientation,
  and canonical seam connectivity.

`tests/test_native_hex_cad_front_contract.py` already repeats those four input
hashes three times on `t_junction.step`.  This card confirms the exact
dataclass fields without requiring OCP at test time.

## Gate-4 result

The certificate is insufficient for generated-mesh Gate 4.  The native Hex
production mesher does not consume `CadNativeTriangulation` or
`CadEntityProvenance`; it has no immutable generated boundary-face -> input
B-Rep face-ordinal mapping and no output-side digest binding such a mapping to
the source certificate.  Existing CAD evidence diagnostics remain report-only
and do not create that binding.

Consequently, input hashes demonstrate deterministic reader traversal only.
They cannot prove that a generated boundary face preserved its source B-Rep
face, topology, or patch/provenance identity.  Missing physical-group mapping
remains a separate hard gap and is not inferred from face names, layers,
colours, or geometry.

## Unblock condition

Add an explicit immutable mapping from every generated boundary face to one or
more authoritative source B-Rep face ordinals, carry the source certificate
through the Hex result/writer boundary, and hash both the mapping and its
source certificate.  Verify complete coverage, no ambiguous/unexplained
generated boundary faces, repeat determinism, and no changed mesh output
before this can support a product Gate-4 claim.
