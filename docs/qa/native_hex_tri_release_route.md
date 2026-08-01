# Native Hex and Tri release-route evidence

## Native Hex

'generate_native_hex' accepts an explicit CAD provenance payload. The release
route consumes the canonical B-Rep vertex/face stream, not the face-local raw
triangulation. When the caller also supplies authoritative physical-group
names, the writer records one patch per source B-Rep face and returns a
measured 'native_hex_source_binding' certificate containing:

- source STEP digest;
- deterministic output boundary-face IDs;
- output-to-source B-Rep face ordinals;
- output physical-group digest;
- maximum source-triangle surface distance and the explicit cell-diagonal tolerance for the measured stair-step boundary. A coarse curved CAD run is still rejected when the measured distance exceeds this bound.

Missing CAD provenance or physical groups never becomes a source-binding claim.
The tier wrapper fails closed for a CAD input whose measured binding is
incomplete. Geometry-only STL runs remain supported but are not CAD-authority
evidence.

## Native Tri

'core.preprocessor.native_tri.release_route.run_native_tri_release' is the
independent, explicitly enabled route. It executes the transactional local
operator loop and measures:

- actual transaction acceptance and non-clone output hashes;
- source/output manifold and watertight status;
- source-envelope containment;
- explicit per-face source provenance and physical-group mapping;
- explicit feature-edge coverage, including split-edge chains.

The old L2 route remains unchanged and default-off. The release route requires
'AUTO_TESSELL_NATIVE_TRI_RELEASE=1' and explicit source authority; it never
serves the TRI+QUAD or strict-quad products.

## Measured corpus additions

- The actual non-cube Hex B-Rep test exports a fused stepped solid to STEP,
  reloads its canonical OCP provenance, injects authoritative per-face physical
  groups, and repeats the written Hex route three times. At target edge 0.25,
  the measured binding is complete, the maximum source distance is 0, all
  strict volume topology counters are zero, and the artifact digest repeats.
- Native Tet now has an actual cube/sphere/NACA/duct corpus with the explicit
  same-side transaction enabled. Each case is written and independently
  audited for duplicate, non-manifold, open-edge, and inverted-cell counts.
- Native Poly has a sphere/cylinder/duct quality-repeatability corpus and an
  actual positive two-layer boundary-layer transaction with first thickness
  0.05 and strict readback.
- Strict Quad and TRI+QUAD have an independent stepped-prism corpus. The
  all-quad artifact has no triangles; the mixed artifact retains both triangle
  and quad arrays, patch/group payloads, and pair provenance, with three
  byte-identical repetitions. Neither artifact claims product routing.

## Native Poly release mode

AUTO_TESSELL_NATIVE_POLY_RELEASE=1 (or the explicit `release_route` tier parameter) selects the native Poly harness as an independent release route. If the strict harness fails, this mode returns the measured failure and forbids the legacy Voronoi fallback. The default route remains unchanged for best-effort compatibility; a fallback artifact cannot satisfy a Poly release claim.


The Poly release mode also has a source-bound structured thin-extrusion route
for planar watertight sources. It is selected only by explicit release mode,
writes through the generic polyhedral writer, and is admitted only after the
independent strict artifact audit. The measured NACA and extreme-gear cases
retain source patch bindings; the gear artifact is byte-identical over three
runs. The normal Tet-to-dual route and default routing remain unchanged.
