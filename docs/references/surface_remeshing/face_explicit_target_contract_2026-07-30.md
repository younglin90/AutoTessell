# FACE-EXPLICIT-TARGET-CONTRACT-1 Evidence

Date: 2026-07-30

Status: L0/L1 fail-closed reporting contract. This is not face-count-target
support or a promotion of either native surface route.

## Measured limitation

On the icosphere fixture, the available target-edge mapping was exercised with
requested triangle counts `40`, `80`, `160`, and `320`. Only the `80` request
passed the existing hard gates, and its actual output had `56` triangles
(absolute error `24`, relative error `0.30`). The `40`, `160`, and `320`
requests were rejected by the hard gates.

This is insufficient evidence for a `target_faces` contract: the target-edge
heuristic neither produces a reliable face count nor preserves the existing
surface gates across the measured requests. Do not weaken those gates to claim
count targeting.

## Reference boundary

CGAL's `Uniform_sizing_field` documentation describes a uniform **target edge
length** for isotropic remeshing, with split/collapse thresholds around that
length. It is useful reference context for a future sizing implementation, but
it does not establish an exact target-face-count contract for these routes.
No CGAL source code was copied.

Source: <https://doc.cgal.org/latest/PMP_Remeshing/classCGAL_1_1Polygon__mesh__processing_1_1Uniform__sizing__field.html>

## Decision

Until a separately measured and gated face-count mechanism exists,
`native_face_remesh` and `native_quad_dominant` reject every positive
`target_faces` request before either native engine is invoked. The rejection
returns a byte-equivalent triangle surface and reports requested, actual,
absolute-error, relative-error, and route-specific unsupported-reason fields.
It never falls through to the default native or legacy route.

For `target_faces=None` or `0`, the existing explicit route remains unchanged.
Its records report the truthful produced count but no target error. Quad output
is reported as both native mixed elements and the distinct triangular handoff:
each native quad is split into two triangles for the `trimesh` pipeline
boundary, so those two counts must not be conflated.

## Unblock condition

Replace this refusal only with a mechanism that has an explicit count-control
algorithm, measured error bounds across canonical and target-hard fixtures,
unchanged surface/topology/orientation/provenance gates, deterministic repeats,
and an equally explicit mixed-quad versus triangular-handoff count contract.
