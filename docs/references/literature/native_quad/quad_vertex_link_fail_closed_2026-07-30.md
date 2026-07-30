# QUAD-VERTEX-LINK-FAIL-CLOSED-1

Status: L0/L1 focused verification. Input-validation card; no target-cell,
boundary-layer, routing, default, or valid-output policy change.

## Hypothesis

An edge-manifold triangle soup can still contain a non-manifold vertex when
its incident-triangle link has more than one connected component. Emitting
quads from that input silently preserves an invalid source topology. Rejecting
only that proven condition before pairing makes the native quad route truthful
without moving source vertices or rejecting disconnected valid components.

## Evidence and provenance

CGAL 6.2's official Polygon Mesh Processing manual defines a polygon mesh as
a 2-manifold surface. Its `PMPPolygonSoupOrientationVisitor` separately reports
`non_manifold_vertex(vid, nb_link_ccs)`, where `nb_link_ccs` is the number of
edge-connected components in the vertex link.

- Documentation: <https://doc.cgal.org/latest/Polygon_mesh_processing/classPMPPolygonSoupOrientationVisitor.html>
- CGAL license record: <https://raw.githubusercontent.com/CGAL/cgal/main/Installation/LICENSE>

CGAL source is GPL/LGPL by file. This card copies no CGAL code, adds no
dependency, and uses an independently written graph reachability check over
the existing NumPy triangle indices.

## Baseline and acceptance

L0 bow-tie fixture: two disjoint oriented triangle fans share vertex `0`.
Before this card, `native_quad_dominant_remesh()` accepted it and emitted two
quads. Acceptance is stable `ValueError("surface contains non-manifold vertex 0")`
on two calls, with input vertices and triangles byte-identical.

L1 canonical cube remains six quads with its existing feature protection.
Two disconnected planar manifold components remain valid and independently
emit two quads. The validator intentionally does not require a single
component, closed boundaries, or any target cell count.
