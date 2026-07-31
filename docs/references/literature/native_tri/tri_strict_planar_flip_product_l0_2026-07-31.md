# Native tri strict planar flip candidate L0

One real `OperatorTransaction.flip_edge` candidate is materialized only for an
opt-in, same-patch, non-feature interior edge.  Source coordinates stay exact.
The adapter checks exact boundary-edge set, component/Euler topology, declared
feature-edge retention, patch equality, and explicit two-source-face region
provenance.  Any missing condition rejects with no candidate.

This is not a production tri mesher: returned candidate is read-only and
`independent_product_ready=false`; no routing/UI/writer changes. Future product
work needs whole-surface envelope, feature path, physical-group and per-face
provenance certificates over many operations.
