# Native release authority gate

The release verifier with measured authority is
`scripts/verify_native_release_authority_matrix.py`. It first validates the
existing complete multi-engine matrix, then requires every row to contain a
`source_output_authority` certificate with source/output shape, feature, patch,
physical-group, and provenance SHA-256 values plus preservation and component
bijection flags. A base-matrix PASS without those measurements is
`authority_unverified`.

The gate remains independent of engine routing. It cannot turn a no-op Tri
clone, a default-off Quad route, a cube-only result, or an artifact with
unverified topology into a release pass.
