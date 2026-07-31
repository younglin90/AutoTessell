# Strict quad product notes from user-supplied SIAM papers

## Sources read

- Zhu et al. (2025), *Quadrilateral Mesh Generation for Open Surfaces with
  Negative Euler Characteristics Based on Symmetric Abel Differentials*, DOI
  `10.1137/1.9781611978575.6`.
- Zhu et al. (2026), *Surface Quadrilateral Mesh Generation Based on
  Weierstrass ℘ Function*, DOI `10.1137/1.9781611979138.18`.

Both local PDFs were read on 2026-07-31.  They are theory and algorithm
references only.  No code, data, output, dependency, or implementation detail
was copied.

## 2025 symmetric-Abel method

Input is a compact, oriented, triangulated surface with negative Euler
characteristic and multiple boundary components.  The paper doubles the
surface, builds a homology basis (including bridge paths), solves Hodge/Poisson
systems for harmonic forms, symmetrizes the holomorphic basis, quantizes its
periods, then pulls a regular parameter-domain grid back to form quads.  Its
useful independent idea is an explicit preflight: orientability, boundary-loop
identity, homology basis, and seam correspondence must exist before a strict
quad attempt.

The paper demonstrates orthogonality, boundary alignment, uniformity, and
few singularities on one genus-4, three-boundary model.  It does not provide a
bidirectional surface envelope, source-face/patch provenance, physical-group
preservation, deterministic hash, invalid-element census, target-count
tolerance, or an explicit failure contract.  AutoTessell must therefore reject
instead of modifying input when any prerequisite or postcondition is absent.

## 2026 Weierstrass/sigma method

The scope is closed genus-one surfaces or rectangular planar domains with
holes.  It uses Ricci flow and a homology cut to obtain a flat torus, computes
Weierstrass ℘ or sigma functions, adjusts or inserts singularities to satisfy
Abel-Jacobi conditions, builds a quartic differential, traces a motorcycle
graph/T-mesh, then deforms it before regular-grid pullback.  Reported examples
include kitten/vase genus-one meshes and planar circular-or-approximately-
circular-hole cases.  The reported `min J` ranges from `0.454` to `0.683` and
the largest `10000-Holes` run reports `1432.3 s`.

Its useful independent idea is explicit singularity and period feasibility
before extraction.  Its automatic singularity adjustment/insertion, input
scope, approximate lattice sum, and post-graph deformation cannot enter the
native strict-quad route without a source-invariant transaction.  They may not
move or reclassify source geometry/patches silently.

## Product decision

Neither paper authorizes current production `quad` output.  Future C++23
strict-quad work may use a preflight ledger for oriented-manifold topology,
boundary loops, features, patches, source support, and parameter-domain seam
maps.  Final acceptance remains independent: every face degree four, no
triangular handoff/fallback, bidirectional envelope, feature/patch/provenance
preservation, manifold orientation, finite positive geometry, and deterministic
repetition.  Failure must return an explicit rejection; target face count stays
secondary to those contracts.
