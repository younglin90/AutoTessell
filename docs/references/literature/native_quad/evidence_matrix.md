# Native Quad / Quad-Dominant Literature Evidence Matrix

Status: batch 1 complete. `FULL_READ` means the complete paper, equations,
algorithms, experiments, limitations, and references were inspected.

| Paper | Status | Main evidence | Candidate cards | Critical caution |
| --- | --- | --- | --- | --- |
| Alliez et al. 2003 | FULL_READ | Curvature tensor, anisotropic spacing, curvature-line sampling, feature-side smoothing, umbilic fallback, conforming hybrid extraction | `QUAD-METRIC-FIELD1`, `QUAD-FEATURE-SIDE1`, `QUAD-UMBILIC-MODE1`, `QUAD-CONFORMING1` | Genus-zero/global-parameterization assumption; sampling bottleneck; no hard fidelity or quality guarantee |
| Jakob et al. 2015 | FULL_READ | 4-RoSy plus 4-PoSy, intrinsic/extrinsic energies, multiresolution colored relaxation, singularity-aware extraction | `QUAD-ROSY1`, `QUAD-POSY1`, `QUAD-MULTIRES1`, `QUAD-SINGULARITY1`, `QUAD-EXTRACT1` | Local minima and extra singularities; extraction can become non-manifold or lose elements |
| Huang et al. 2018 | FULL_READ | Integer-offset regularity, multiresolution min-cost flow, inversion cleanup, constrained continuous solve, simple quad extraction | `QUAD-OFFSET-LEDGER1`, `QUAD-MCF1`, `QUAD-INVERSION1`, `QUAD-FEATURE-SLIDE1`, `QUAD-FIDELITY1` | SAT is incomplete in practice; roughly 20% watertightness failures reported; topology regularity can erase detail |

## Code audit and decision

`core/preprocessor/native_remesh/quad_dominant.py` is a deterministic,
quality-gated triangle-pair merger. It rejects boundary/feature/wall crossings,
non-convex pairs, poor scaled Jacobian, excessive aspect ratio, and warpage.
Tests cover a planar pair, cube pairing, and warped-pair rejection. This is a
useful conservative fallback, but not a quad meshing engine: it has no field
construction, singularity representation, global consistency, or independent
surface sampling.

Implement in evidence order:

1. Common hard contract: manifold orientation, patch/feature provenance,
   bidirectional fidelity, deterministic rollback.
2. Curvature/size metric and 4-RoSy orientation field.
3. 4-PoSy position field plus explicit integer-offset/singularity ledger.
4. Transactional conforming extraction; retain the pair merger as fallback.
5. Only then add min-cost-flow singularity reduction and bounded inversion
   cleanup. Never accept topology regularity at the expense of fidelity.

Primary metrics: quad fraction, singularity count/type, minimum scaled
Jacobian, angle/area distortion, maximum bidirectional distance, feature
coverage, manifold/watertight status, determinism, peak memory, and runtime.
