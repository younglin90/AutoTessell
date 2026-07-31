# Strict quad pair transaction L0

Opt-in transaction derives quads from explicit complete source-triangle pairs.
It never calls quad-dominant. Every source triangle must be consumed exactly;
output triangles are empty. Existing strict preflight verifies exact vertices,
boundary, features, components/Euler topology, patches, provenance and
coplanarity before the read-only in-memory candidate exists. Default OFF.

Candidate success is not full product readiness: routing/UI/writer remain
disconnected and `independent_product_ready=false`.
