# Alliez et al. 2003 — Anisotropic Polygonal Remeshing

Status: `FULL_READ` (9/9 pages, including equations, algorithm, experiments,
limitations, and references). The first page was also rendered and visually
checked.

- Authors: Pierre Alliez, David Cohen-Steiner, Olivier Devillers, Bruno Lévy,
  Mathieu Desbrun
- Venue: ACM Transactions on Graphics / SIGGRAPH 2003
- DOI: `10.1145/882262.882296` (some metadata services expose the proceedings
  alias `10.1145/1201775.882296`)
- Open PDF: https://www.geometry.caltech.edu/pubs/ACDLD03.pdf

## Method reconstructed

The method estimates a curvature tensor at every input vertex from the normal
cycle over a small neighborhood `B`:

`T(v) = (1 / |B|) sum_e beta(e) |e intersect B| e_bar e_bar^T`.

It smooths the tensor, extracts the minimum and maximum principal-curvature
directions, maps a genus-zero surface patch to a conformal 2-D domain, and
traces curvature lines with fourth-order Runge--Kutta integration. Sampling
density follows the local approximation-error relation

`d(k) = 2 sqrt(epsilon (2 / |k| - epsilon))`,

while the asymptotic desired element aspect ratio is
`sqrt(|k_max| / |k_min|)`. Intersections of the traced lines and additional
samples in isotropic regions become vertices of a constrained Delaunay mesh.
Line samples are decimated only when planarity and intersection structure are
preserved. Polygon decomposition and conforming-edge insertion remove hanging
connections and produce a hybrid of elongated quads and isotropic triangles.

Feature curves are not blurred across: tensor estimation and smoothing are
clipped to the appropriate side of a sharp edge. Umbilics are detected from
the vanishing deviator of the tensor and receive isotropic sampling because no
stable principal direction exists there.

## Evidence and limitations

- The figures demonstrate direction-aligned, curvature-adaptive polygonal
  meshes on several scanned and analytic models.
- Tensor estimation is inexpensive in the reported timings; line sampling is
  the dominant cost (about 60 seconds on typical examples and eight minutes on
  the David model), versus roughly one second for the final meshing stage.
- The construction assumes a genus-zero non-closed patch. Higher-genus or
  closed geometry requires cuts and stitching in a parameter domain.
- Flat or undersampled regions require random fallback samples.
- There is no hard Hausdorff, minimum-angle, manifoldness, or termination
  guarantee. The paper recommends robust filtered predicates for geometric
  decisions.

## AutoTessell mapping

The current `core/preprocessor/native_remesh/quad_dominant.py` only greedily
pairs adjacent input triangles. It has no tensor/metric field, cross field,
umbilic handling, parameterization, or conforming extraction.

Adopt locally, without making global flattening the production default:

- `QUAD-METRIC-FIELD1`: curvature-tensor-derived anisotropic size/direction
  field, with noise and anisotropy clamps.
- `QUAD-FEATURE-SIDE1`: estimate and smooth fields independently on each side
  of protected curves.
- `QUAD-UMBILIC-MODE1`: switch to isotropic targets when the tensor deviator is
  below a scale-aware threshold.
- `QUAD-CONFORMING1`: reject or repair hanging connections before accepting an
  extracted surface.

Falsification gates: finite positive metric eigenvalues; stable output under
input triangle refinement; no feature crossing; no non-manifold edge; symmetric
surface-distance budget; deterministic result for a fixed seed.
