/*
 * tet_kernels.c — Native C kernels for AutoTessell native_tet hot loops.
 *
 * C99, no external dependencies (only libm).
 *
 * Exported functions (C ABI, all callable via ctypes):
 *
 *   tet_quality_batch      — radius/edge ratio quality per tet
 *   tet_signed_vol6_batch  — signed volume * 6 per tet
 *   tet_radius_edge_ratio_batch — radius-edge proxy per tet
 *   tet_min_solid_angle_sr_batch — minimum solid angle per tet
 *   tet_qshape_batch      — Klingner-like Q-shape per tet
 *   detect_degenerate_tets_stats — degenerate tet counts and volume extrema
 *   tet_shortest_edges_batch — shortest local edge and length per tet
 *   edge_collapse_priority_batch — grouped edge collapse top-k scores
 *   build_tet_face_adjacency_stats — tet face adjacency and counts
 *   screen_flip_candidates_batch — internal face flip candidates from adjacency
 *   screen_swap_candidates_batch — internal edge swap candidates
 *   tet_vertex_valence_batch — per-vertex incident tet counts and stats
 *   tet_boundary_vertex_stats_batch — boundary/interior tet counts by vertex ids
 *   tet_edge_stats_batch — tet edge length/aniso aggregate stats
 *   tet_volume_stats_batch — tet quality/volume aggregate stats and histogram
 *   tet_inradius_batch — tet inradius array and aggregate stats
 *   tet_circumsphere_batch — tet circumcenters/radii and aggregate stats
 *   tet_aniso_tensor_batch — tet covariance eigenvalue anisotropy ratios
 *   hex_stretch_stats_batch — hex edge stretch aggregate stats
 *   hex_face_area_stats_batch — hex quad face area aggregate stats
 *   bl_prism_quality_stats_batch — boundary-layer prism aggregate stats
 *   hex_skew_simple_stats_batch — hex face-center skew aggregate stats
 *   hex_ortho_stats_batch — hex face-center orthogonality aggregate stats
 *   hex_jacobian_stats_batch — hex corner Jacobian aggregate stats
 *   hex_inverted_stats_batch — inverted hex indices and worst Jacobian
 *   poly_volume_stats_batch — poly cell volume aggregate stats
 *   surface_boundary_edges_batch — boundary edges for triangular faces
 *   surface_edge_stats_batch — edge-count stats for triangular faces
 *   surface_vertex_valence_batch — per-vertex face/edge valence
 *   surface_edge_lengths_stats_batch — triangle edge lengths + unique/aspect stats
 *   surface_unique_edge_length_stats_batch — unique edge length min/max/p01/p99
 *   surface_vertex_gaussian_curvature_batch — vertex Gaussian curvature
 *   surface_feature_edges_stats_batch — boundary/sharp/corner feature counts
 *   surface_vertex_mean_curvature_batch — vertex mean curvature vectors
 *   surface_feature_report_stats_batch — combined unique-edge + feature counts
 *   surface_diag_stats_batch — surface diagnostic aggregate stats
 *   surface_dihedral_histogram_batch — internal-edge dihedral histogram
 *   surface_remove_degenerate_faces_mask — area/duplicate face keep mask
 *   surface_dedup_vertices_quantized — quantized vertex dedup + face remap
 *   surface_area_volume_stats_batch — surface area, signed volume, bbox volume
 *   surface_face_area_distribution_stats_batch — min/max/mean/std/p01/p99
 *   build_face_to_tets     — sorted face triples + owning tet idx + local slot
 *   build_edge_to_tets     — sorted edge pairs + owning tet idx
 *   edge_lengths_batch     — Euclidean edge lengths
 *
 * Quality convention: matches flip.py _tet_quality():
 *   q = 8.48 * |vol| / emax^3   (inscribed-sphere proxy)
 *   sign/scale identical to Python path so tests compare allclose(1e-12).
 *
 * Face encoding for build_face_to_tets:
 *   Each face is stored as (a, b, c) with a <= b <= c (canonical sorted triple).
 *   tet_idx_out[i] = which tet owns face i.
 *   slot_out[i]    = which of the 4 local slots (0..3) that face comes from.
 *   Total output rows = n_tets * 4.  Caller groups by face triple.
 *
 * Edge encoding for build_edge_to_tets:
 *   Each edge (a, b) with a < b.  6 edges per tet.
 *   Total output rows = n_tets * 6.  Caller groups by edge pair.
 *
 * Return values of build_* functions:
 *   The actual number of entries written (n_tets*4 or n_tets*6 unless
 *   max_entries is hit, in which case -1 is returned as overflow signal).
 */

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* -----------------------------------------------------------------------
 * Internal helpers
 * ----------------------------------------------------------------------- */

static inline double _dot3(const double *a, const double *b) {
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}

static inline void _cross3(const double *a, const double *b, double *out) {
    out[0] = a[1]*b[2] - a[2]*b[1];
    out[1] = a[2]*b[0] - a[0]*b[2];
    out[2] = a[0]*b[1] - a[1]*b[0];
}

/* |a - b|^2 */
static inline double _dist2(const double *a, const double *b) {
    double dx = a[0]-b[0], dy = a[1]-b[1], dz = a[2]-b[2];
    return dx*dx + dy*dy + dz*dz;
}

static inline double _tri_area3(const double *a, const double *b, const double *c) {
    double ab[3] = {b[0]-a[0], b[1]-a[1], b[2]-a[2]};
    double ac[3] = {c[0]-a[0], c[1]-a[1], c[2]-a[2]};
    double cr[3];
    _cross3(ab, ac, cr);
    return 0.5 * sqrt(_dot3(cr, cr));
}

static inline double _det3(
    double a00, double a01, double a02,
    double a10, double a11, double a12,
    double a20, double a21, double a22)
{
    return
        a00 * (a11 * a22 - a12 * a21) -
        a01 * (a10 * a22 - a12 * a20) +
        a02 * (a10 * a21 - a11 * a20);
}

static inline void _sym3_eig_min_max(
    double a00, double a01, double a02,
    double a11, double a12, double a22,
    double *eig_min, double *eig_max)
{
    double p1 = a01*a01 + a02*a02 + a12*a12;
    if (p1 < 1e-60) {
        double mn = a00;
        double mx = a00;
        if (a11 < mn) mn = a11;
        if (a22 < mn) mn = a22;
        if (a11 > mx) mx = a11;
        if (a22 > mx) mx = a22;
        *eig_min = mn;
        *eig_max = mx;
        return;
    }

    double q = (a00 + a11 + a22) / 3.0;
    double b00 = a00 - q;
    double b11 = a11 - q;
    double b22 = a22 - q;
    double p2 = b00*b00 + b11*b11 + b22*b22 + 2.0*p1;
    double p = sqrt(p2 / 6.0);
    if (p < 1e-60) {
        *eig_min = q;
        *eig_max = q;
        return;
    }

    double c00 = b00 / p;
    double c01 = a01 / p;
    double c02 = a02 / p;
    double c11 = b11 / p;
    double c12 = a12 / p;
    double c22 = b22 / p;
    double r = _det3(c00, c01, c02, c01, c11, c12, c02, c12, c22) / 2.0;
    double pi = acos(-1.0);
    double phi;
    if (r <= -1.0) {
        phi = pi / 3.0;
    } else if (r >= 1.0) {
        phi = 0.0;
    } else {
        phi = acos(r) / 3.0;
    }

    double eig1 = q + 2.0 * p * cos(phi);
    double eig3 = q + 2.0 * p * cos(phi + (2.0 * pi / 3.0));
    double eig2 = 3.0 * q - eig1 - eig3;
    double mn = eig1;
    double mx = eig1;
    if (eig2 < mn) mn = eig2;
    if (eig3 < mn) mn = eig3;
    if (eig2 > mx) mx = eig2;
    if (eig3 > mx) mx = eig3;
    *eig_min = mn;
    *eig_max = mx;
}

/* pts layout: pts[v*3 .. v*3+2] */
static inline const double *_pt(const double *pts, long v) {
    return pts + (ptrdiff_t)(v) * 3;
}

/* -----------------------------------------------------------------------
 * tet_quality_batch
 * -----------------------------------------------------------------------
 * For each tet, compute q = 8.48 * |vol6/6| / emax^3.
 * out[i] corresponds to tets[i*4 .. i*4+3].
 * ----------------------------------------------------------------------- */
void tet_quality_batch(const double *pts, int n_pts,
                       const long *tets, int n_tets,
                       double *out)
{
    (void)n_pts;  /* unused, kept for API symmetry */

    for (int t = 0; t < n_tets; ++t) {
        long ia = tets[(ptrdiff_t)t*4 + 0];
        long ib = tets[(ptrdiff_t)t*4 + 1];
        long ic = tets[(ptrdiff_t)t*4 + 2];
        long id = tets[(ptrdiff_t)t*4 + 3];

        const double *A = _pt(pts, ia);
        const double *B = _pt(pts, ib);
        const double *C = _pt(pts, ic);
        const double *D = _pt(pts, id);

        /* B-A, C-A, D-A */
        double ba[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ca[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double da[3] = {D[0]-A[0], D[1]-A[1], D[2]-A[2]};

        /* vol * 6 = dot(B-A, cross(C-A, D-A)) */
        double cr[3];
        _cross3(ca, da, cr);
        double vol6 = _dot3(ba, cr);
        double vol = fabs(vol6) / 6.0;

        /* 6 edge lengths^2 */
        double emax2 = 0.0;
        double d2;

        d2 = _dist2(A, B); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(A, C); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(A, D); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(B, C); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(B, D); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(C, D); if (d2 > emax2) emax2 = d2;

        double emax = sqrt(emax2);
        if (emax < 1e-30) {
            out[t] = 0.0;
        } else {
            out[t] = 8.48 * vol / (emax * emax * emax);
        }
    }
}

/* -----------------------------------------------------------------------
 * tet_signed_vol6_batch
 * -----------------------------------------------------------------------
 * vol6[i] = dot(B-A, cross(C-A, D-A))   (signed, × 6)
 * ----------------------------------------------------------------------- */
void tet_signed_vol6_batch(const double *pts, int n_pts,
                           const long *tets, int n_tets,
                           double *out)
{
    (void)n_pts;

    for (int t = 0; t < n_tets; ++t) {
        const double *A = _pt(pts, tets[(ptrdiff_t)t*4 + 0]);
        const double *B = _pt(pts, tets[(ptrdiff_t)t*4 + 1]);
        const double *C = _pt(pts, tets[(ptrdiff_t)t*4 + 2]);
        const double *D = _pt(pts, tets[(ptrdiff_t)t*4 + 3]);

        double ba[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ca[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double da[3] = {D[0]-A[0], D[1]-A[1], D[2]-A[2]};

        double cr[3];
        _cross3(ca, da, cr);
        out[t] = _dot3(ba, cr);
    }
}

/* -----------------------------------------------------------------------
 * tet_min_dihedral_deg_batch
 * -----------------------------------------------------------------------
 * Matches quality.py:tet_min_dihedral_deg. Degenerate face normals are left
 * as zero vectors, so dot=0 and the corresponding normal angle is 90 deg.
 * ----------------------------------------------------------------------- */
static void _unit_face_normal(const double *P, const double *Q, const double *R,
                              double out[3])
{
    double qp[3] = {Q[0]-P[0], Q[1]-P[1], Q[2]-P[2]};
    double rp[3] = {R[0]-P[0], R[1]-P[1], R[2]-P[2]};
    _cross3(qp, rp, out);
    double n2 = _dot3(out, out);
    if (n2 > 1e-60) {
        double inv = 1.0 / sqrt(n2);
        out[0] *= inv;
        out[1] *= inv;
        out[2] *= inv;
    }
}

static double _dihedral_deg_from_normals(const double n1[3], const double n2[3])
{
    double dot = _dot3(n1, n2);
    if (dot > 1.0) dot = 1.0;
    if (dot < -1.0) dot = -1.0;
    return 180.0 - (acos(dot) * (180.0 / 3.14159265358979323846264338327950288));
}

void tet_min_dihedral_deg_batch(const double *pts, int n_pts,
                                const long *tets, int n_tets,
                                double *out)
{
    (void)n_pts;

    for (int t = 0; t < n_tets; ++t) {
        const double *A = _pt(pts, tets[(ptrdiff_t)t*4 + 0]);
        const double *B = _pt(pts, tets[(ptrdiff_t)t*4 + 1]);
        const double *C = _pt(pts, tets[(ptrdiff_t)t*4 + 2]);
        const double *D = _pt(pts, tets[(ptrdiff_t)t*4 + 3]);

        double n_abc[3], n_abd[3], n_acd[3], n_bcd[3];
        _unit_face_normal(A, B, C, n_abc);
        _unit_face_normal(A, B, D, n_abd);
        _unit_face_normal(A, C, D, n_acd);
        _unit_face_normal(B, C, D, n_bcd);

        double min_dh = _dihedral_deg_from_normals(n_abc, n_abd);
        double dh = _dihedral_deg_from_normals(n_abc, n_acd);
        if (dh < min_dh) min_dh = dh;
        dh = _dihedral_deg_from_normals(n_abd, n_acd);
        if (dh < min_dh) min_dh = dh;
        dh = _dihedral_deg_from_normals(n_abc, n_bcd);
        if (dh < min_dh) min_dh = dh;
        dh = _dihedral_deg_from_normals(n_abd, n_bcd);
        if (dh < min_dh) min_dh = dh;
        dh = _dihedral_deg_from_normals(n_acd, n_bcd);
        if (dh < min_dh) min_dh = dh;

        out[t] = min_dh;
    }
}

/* -----------------------------------------------------------------------
 * tet_aspect_ratio_batch
 * -----------------------------------------------------------------------
 * Matches quality.py:tet_aspect_ratio: rmax / inradius, where rmax is
 * half of the longest edge and inradius = 3V / total_face_area.
 * ----------------------------------------------------------------------- */
void tet_aspect_ratio_batch(const double *pts, int n_pts,
                            const long *tets, int n_tets,
                            double *out)
{
    (void)n_pts;

    for (int t = 0; t < n_tets; ++t) {
        const double *A = _pt(pts, tets[(ptrdiff_t)t*4 + 0]);
        const double *B = _pt(pts, tets[(ptrdiff_t)t*4 + 1]);
        const double *C = _pt(pts, tets[(ptrdiff_t)t*4 + 2]);
        const double *D = _pt(pts, tets[(ptrdiff_t)t*4 + 3]);

        double ab[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ac[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double ad[3] = {D[0]-A[0], D[1]-A[1], D[2]-A[2]};

        double cross_ac_ad[3];
        _cross3(ac, ad, cross_ac_ad);
        double vol = fabs(_dot3(ab, cross_ac_ad)) / 6.0;

        double cr[3];
        _cross3(ab, ac, cr);
        double A1 = 0.5 * sqrt(_dot3(cr, cr));
        _cross3(ab, ad, cr);
        double A2 = 0.5 * sqrt(_dot3(cr, cr));
        _cross3(ac, ad, cr);
        double A3 = 0.5 * sqrt(_dot3(cr, cr));

        double cb[3] = {C[0]-B[0], C[1]-B[1], C[2]-B[2]};
        double db[3] = {D[0]-B[0], D[1]-B[1], D[2]-B[2]};
        _cross3(cb, db, cr);
        double A4 = 0.5 * sqrt(_dot3(cr, cr));

        double surf_sum = A1 + A2 + A3 + A4;
        double inrad = surf_sum > 1e-30 ? (3.0 * vol / surf_sum) : 0.0;
        if (inrad <= 1e-30) {
            out[t] = 1e6;
            continue;
        }

        double emax2 = _dist2(A, B);
        double d2 = _dist2(A, C); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(A, D); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(B, C); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(B, D); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(C, D); if (d2 > emax2) emax2 = d2;

        out[t] = (sqrt(emax2) * 0.5) / inrad;
    }
}

/* -----------------------------------------------------------------------
 * tet_radius_edge_ratio_batch
 * -----------------------------------------------------------------------
 * Matches quality.py:tet_radius_edge_ratio: (longest edge / 2) / shortest edge.
 * Degenerate tets with a near-zero shortest edge return 1e6.
 * ----------------------------------------------------------------------- */
void tet_radius_edge_ratio_batch(const double *pts, int n_pts,
                                 const long *tets, int n_tets,
                                 double *out)
{
    (void)n_pts;

    for (int t = 0; t < n_tets; ++t) {
        const double *A = _pt(pts, tets[(ptrdiff_t)t*4 + 0]);
        const double *B = _pt(pts, tets[(ptrdiff_t)t*4 + 1]);
        const double *C = _pt(pts, tets[(ptrdiff_t)t*4 + 2]);
        const double *D = _pt(pts, tets[(ptrdiff_t)t*4 + 3]);

        double emin2 = _dist2(A, B);
        double emax2 = emin2;
        double d2 = _dist2(A, C);
        if (d2 < emin2) emin2 = d2;
        if (d2 > emax2) emax2 = d2;
        d2 = _dist2(A, D);
        if (d2 < emin2) emin2 = d2;
        if (d2 > emax2) emax2 = d2;
        d2 = _dist2(B, C);
        if (d2 < emin2) emin2 = d2;
        if (d2 > emax2) emax2 = d2;
        d2 = _dist2(B, D);
        if (d2 < emin2) emin2 = d2;
        if (d2 > emax2) emax2 = d2;
        d2 = _dist2(C, D);
        if (d2 < emin2) emin2 = d2;
        if (d2 > emax2) emax2 = d2;

        double emin = sqrt(emin2);
        if (emin > 1e-30) {
            out[t] = (0.5 * sqrt(emax2)) / emin;
        } else {
            out[t] = 1e6;
        }
    }
}

/* -----------------------------------------------------------------------
 * tet_min_solid_angle_sr_batch
 * -----------------------------------------------------------------------
 * Matches quality.py:tet_min_solid_angle_sr using the Van Oosterom-Strackee
 * formula at each of the four tetrahedron vertices.
 * ----------------------------------------------------------------------- */
static double _solid_angle_sr(const double *O, const double *P1,
                              const double *P2, const double *P3)
{
    double a[3] = {P1[0]-O[0], P1[1]-O[1], P1[2]-O[2]};
    double b[3] = {P2[0]-O[0], P2[1]-O[1], P2[2]-O[2]};
    double c[3] = {P3[0]-O[0], P3[1]-O[1], P3[2]-O[2]};
    double cr[3];
    _cross3(b, c, cr);
    double num = fabs(_dot3(a, cr));
    double na = sqrt(_dot3(a, a));
    double nb = sqrt(_dot3(b, b));
    double nc = sqrt(_dot3(c, c));
    double ab = _dot3(a, b);
    double bc = _dot3(b, c);
    double ca = _dot3(c, a);
    double denom = na * nb * nc + ab * nc + bc * na + ca * nb;
    if (fabs(denom) <= 1e-30) {
        denom = 1e-30;
    }
    return 2.0 * atan2(num, denom);
}

void tet_min_solid_angle_sr_batch(const double *pts, int n_pts,
                                  const long *tets, int n_tets,
                                  double *out)
{
    (void)n_pts;

    for (int t = 0; t < n_tets; ++t) {
        const double *A = _pt(pts, tets[(ptrdiff_t)t*4 + 0]);
        const double *B = _pt(pts, tets[(ptrdiff_t)t*4 + 1]);
        const double *C = _pt(pts, tets[(ptrdiff_t)t*4 + 2]);
        const double *D = _pt(pts, tets[(ptrdiff_t)t*4 + 3]);

        double sa0 = _solid_angle_sr(A, B, C, D);
        double sa1 = _solid_angle_sr(B, A, C, D);
        double sa2 = _solid_angle_sr(C, A, B, D);
        double sa3 = _solid_angle_sr(D, A, B, C);
        double mn = sa0;
        if (sa1 < mn) mn = sa1;
        if (sa2 < mn) mn = sa2;
        if (sa3 < mn) mn = sa3;
        out[t] = mn;
    }
}

/* -----------------------------------------------------------------------
 * tet_qshape_batch
 * -----------------------------------------------------------------------
 * Matches core.evaluator.tet_qshape: Q = ((3V)^(2/3) / sum(edge^2)) / 0.0857,
 * clipped to [0, 1], with inverted or degenerate tets mapped to 0.
 * ----------------------------------------------------------------------- */
void tet_qshape_batch(const double *pts, int n_pts,
                      const long *tets, int n_tets,
                      double *out)
{
    (void)n_pts;

    for (int t = 0; t < n_tets; ++t) {
        const double *A = _pt(pts, tets[(ptrdiff_t)t*4 + 0]);
        const double *B = _pt(pts, tets[(ptrdiff_t)t*4 + 1]);
        const double *C = _pt(pts, tets[(ptrdiff_t)t*4 + 2]);
        const double *D = _pt(pts, tets[(ptrdiff_t)t*4 + 3]);

        double ab[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ac[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double ad[3] = {D[0]-A[0], D[1]-A[1], D[2]-A[2]};
        double cr[3];
        _cross3(ab, ac, cr);
        double vol = _dot3(cr, ad) / 6.0;

        double sum_l_sq = _dist2(A, B) + _dist2(A, C) + _dist2(A, D)
                        + _dist2(B, C) + _dist2(B, D) + _dist2(C, D);
        if (vol <= 0.0 || sum_l_sq <= 1e-30) {
            out[t] = 0.0;
            continue;
        }

        double raw = pow(3.0 * vol, 2.0 / 3.0) / sum_l_sq;
        double q = raw / 0.0857;
        if (q < 0.0) q = 0.0;
        if (q > 1.0) q = 1.0;
        out[t] = q;
    }
}

/* -----------------------------------------------------------------------
 * detect_degenerate_tets_stats
 * -----------------------------------------------------------------------
 * counts_out = [n_inverted, n_zero, n_sliver, n_ok]
 * stats_out  = [worst_volume, smallest_abs_volume]
 * ----------------------------------------------------------------------- */
void detect_degenerate_tets_stats(const double *pts, int n_pts,
                                  const long *tets, int n_tets,
                                  double zero_tol,
                                  double sliver_cube_ratio,
                                  long *counts_out,
                                  double *stats_out)
{
    (void)n_pts;

    long n_inv = 0;
    long n_zero = 0;
    long n_sliv = 0;
    double worst = 0.0;
    double smallest_abs = 0.0;

    for (int t = 0; t < n_tets; ++t) {
        const double *A = _pt(pts, tets[(ptrdiff_t)t*4 + 0]);
        const double *B = _pt(pts, tets[(ptrdiff_t)t*4 + 1]);
        const double *C = _pt(pts, tets[(ptrdiff_t)t*4 + 2]);
        const double *D = _pt(pts, tets[(ptrdiff_t)t*4 + 3]);

        double ab[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ac[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double ad[3] = {D[0]-A[0], D[1]-A[1], D[2]-A[2]};
        double cr[3];
        _cross3(ab, ac, cr);
        double vol = _dot3(cr, ad) / 6.0;
        double abs_vol = fabs(vol);

        if (t == 0 || vol < worst) {
            worst = vol;
        }
        if (t == 0 || abs_vol < smallest_abs) {
            smallest_abs = abs_vol;
        }

        int inverted = vol < -zero_tol;
        int zero = abs_vol <= zero_tol;
        if (inverted) {
            ++n_inv;
            continue;
        }
        if (zero) {
            ++n_zero;
            continue;
        }

        double emax2 = _dist2(A, B);
        double d2 = _dist2(A, C); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(A, D); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(B, C); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(B, D); if (d2 > emax2) emax2 = d2;
        d2 = _dist2(C, D); if (d2 > emax2) emax2 = d2;
        double emax = sqrt(emax2);
        if (emax < 1e-30) {
            emax = 1e-30;
        }
        double cube_ratio = abs_vol / (emax * emax * emax);
        if (cube_ratio < sliver_cube_ratio) {
            ++n_sliv;
        }
    }

    counts_out[0] = n_inv;
    counts_out[1] = n_zero;
    counts_out[2] = n_sliv;
    counts_out[3] = (long)n_tets - n_inv - n_zero - n_sliv;
    stats_out[0] = worst;
    stats_out[1] = smallest_abs;
}

/* -----------------------------------------------------------------------
 * tet_shortest_edges_batch
 * -----------------------------------------------------------------------
 * For each tet, emit the first shortest edge in the same local edge order as
 * Python's _TET_EDGES: 01, 02, 03, 12, 13, 23.
 * ----------------------------------------------------------------------- */
void tet_shortest_edges_batch(const double *pts, int n_pts,
                              const long *tets, int n_tets,
                              long *edges_out,
                              double *lengths_out)
{
    (void)n_pts;

    for (int t = 0; t < n_tets; ++t) {
        long ids[4] = {
            tets[(ptrdiff_t)t*4 + 0],
            tets[(ptrdiff_t)t*4 + 1],
            tets[(ptrdiff_t)t*4 + 2],
            tets[(ptrdiff_t)t*4 + 3],
        };
        int pairs[6][2] = {
            {0, 1}, {0, 2}, {0, 3}, {1, 2}, {1, 3}, {2, 3},
        };

        int best = 0;
        const double *P0 = _pt(pts, ids[pairs[0][0]]);
        const double *P1 = _pt(pts, ids[pairs[0][1]]);
        double best_d2 = _dist2(P0, P1);
        for (int k = 1; k < 6; ++k) {
            const double *A = _pt(pts, ids[pairs[k][0]]);
            const double *B = _pt(pts, ids[pairs[k][1]]);
            double d2 = _dist2(A, B);
            if (d2 < best_d2) {
                best_d2 = d2;
                best = k;
            }
        }

        edges_out[(ptrdiff_t)t*2 + 0] = ids[pairs[best][0]];
        edges_out[(ptrdiff_t)t*2 + 1] = ids[pairs[best][1]];
        lengths_out[t] = sqrt(best_d2);
    }
}

typedef struct {
    long u;
    long v;
    long tet;
    double len;
} EdgeRecord;

typedef struct {
    long u;
    long v;
    double score;
} EdgeCandidate;

static int _cmp_edge_record(const void *pa, const void *pb)
{
    const EdgeRecord *a = (const EdgeRecord *)pa;
    const EdgeRecord *b = (const EdgeRecord *)pb;
    if (a->u < b->u) return -1;
    if (a->u > b->u) return 1;
    if (a->v < b->v) return -1;
    if (a->v > b->v) return 1;
    return 0;
}

static int _cmp_edge_candidate_desc(const void *pa, const void *pb)
{
    const EdgeCandidate *a = (const EdgeCandidate *)pa;
    const EdgeCandidate *b = (const EdgeCandidate *)pb;
    if (a->score > b->score) return -1;
    if (a->score < b->score) return 1;
    if (a->u < b->u) return -1;
    if (a->u > b->u) return 1;
    if (a->v < b->v) return -1;
    if (a->v > b->v) return 1;
    return 0;
}

/* -----------------------------------------------------------------------
 * edge_collapse_priority_batch
 * -----------------------------------------------------------------------
 * Computes the same score as analyzer.edge_collapse_score:
 * score = (1 - worst_Q) / (max(edge_len, 1e-30) * incident_tet_count)
 * for unique edges whose incident worst_Q is below q_threshold.
 * n_out[0] is the number of top entries written, or -1 on allocation failure.
 * ----------------------------------------------------------------------- */
void edge_collapse_priority_batch(const double *pts, int n_pts,
                                  const long *tets, int n_tets,
                                  const double *q,
                                  double q_threshold,
                                  int top_k,
                                  long *edges_out,
                                  double *scores_out,
                                  long *n_out)
{
    (void)n_pts;
    n_out[0] = 0;
    if (n_tets <= 0 || top_k <= 0) {
        return;
    }

    const int pairs[6][2] = {
        {0, 1}, {0, 2}, {0, 3}, {1, 2}, {1, 3}, {2, 3},
    };
    long n_records = (long)n_tets * 6L;
    EdgeRecord *records = (EdgeRecord *)malloc((size_t)n_records * sizeof(EdgeRecord));
    EdgeCandidate *candidates = (EdgeCandidate *)malloc((size_t)n_records * sizeof(EdgeCandidate));
    if (records == NULL || candidates == NULL) {
        free(records);
        free(candidates);
        n_out[0] = -1;
        return;
    }

    long r = 0;
    for (int t = 0; t < n_tets; ++t) {
        long ids[4] = {
            tets[(ptrdiff_t)t*4 + 0],
            tets[(ptrdiff_t)t*4 + 1],
            tets[(ptrdiff_t)t*4 + 2],
            tets[(ptrdiff_t)t*4 + 3],
        };
        for (int k = 0; k < 6; ++k) {
            long u = ids[pairs[k][0]];
            long v = ids[pairs[k][1]];
            if (v < u) {
                long tmp = u;
                u = v;
                v = tmp;
            }
            const double *A = _pt(pts, u);
            const double *B = _pt(pts, v);
            records[r].u = u;
            records[r].v = v;
            records[r].tet = (long)t;
            records[r].len = sqrt(_dist2(A, B));
            ++r;
        }
    }

    qsort(records, (size_t)n_records, sizeof(EdgeRecord), _cmp_edge_record);

    long n_candidates = 0;
    long i = 0;
    while (i < n_records) {
        long j = i + 1;
        double worst_q = q[records[i].tet];
        while (j < n_records && records[j].u == records[i].u && records[j].v == records[i].v) {
            double qj = q[records[j].tet];
            if (qj < worst_q) {
                worst_q = qj;
            }
            ++j;
        }
        long cnt = j - i;
        if (worst_q < q_threshold) {
            double edge_len = records[i].len;
            if (edge_len < 1e-30) {
                edge_len = 1e-30;
            }
            candidates[n_candidates].u = records[i].u;
            candidates[n_candidates].v = records[i].v;
            candidates[n_candidates].score = (1.0 - worst_q) / (edge_len * (double)cnt);
            ++n_candidates;
        }
        i = j;
    }

    if (n_candidates > 0) {
        qsort(candidates, (size_t)n_candidates, sizeof(EdgeCandidate), _cmp_edge_candidate_desc);
    }
    long n_keep = n_candidates < (long)top_k ? n_candidates : (long)top_k;
    for (long k = 0; k < n_keep; ++k) {
        edges_out[k*2 + 0] = candidates[k].u;
        edges_out[k*2 + 1] = candidates[k].v;
        scores_out[k] = candidates[k].score;
    }

    n_out[0] = n_keep;
    free(records);
    free(candidates);
}

typedef struct {
    long a;
    long b;
    long c;
    long tet;
    long slot;
} FaceRecord;

static int _cmp_face_record(const void *pa, const void *pb)
{
    const FaceRecord *a = (const FaceRecord *)pa;
    const FaceRecord *b = (const FaceRecord *)pb;
    if (a->a < b->a) return -1;
    if (a->a > b->a) return 1;
    if (a->b < b->b) return -1;
    if (a->b > b->b) return 1;
    if (a->c < b->c) return -1;
    if (a->c > b->c) return 1;
    return 0;
}

static inline void _sort3_long(long *a, long *b, long *c)
{
    long tmp;
    if (*a > *b) { tmp = *a; *a = *b; *b = tmp; }
    if (*b > *c) { tmp = *b; *b = *c; *c = tmp; }
    if (*a > *b) { tmp = *a; *a = *b; *b = tmp; }
}

/* -----------------------------------------------------------------------
 * build_tet_face_adjacency_stats
 * -----------------------------------------------------------------------
 * adj_out is shape (n_tets, 4), flattened, initialized to -1 here.
 * stats_out = [n_unique, n_boundary, n_interior, n_nonmanifold].
 * Returns stats_out[0] = -1 on allocation failure.
 * ----------------------------------------------------------------------- */
void build_tet_face_adjacency_stats(const long *tets, int n_tets,
                                    long *adj_out,
                                    long *stats_out)
{
    static const int FACE_VERTS[4][3] = {
        {1, 2, 3},
        {0, 2, 3},
        {0, 1, 3},
        {0, 1, 2},
    };

    long n_faces = (long)n_tets * 4L;
    for (long i = 0; i < n_faces; ++i) {
        adj_out[i] = -1;
    }
    stats_out[0] = 0;
    stats_out[1] = 0;
    stats_out[2] = 0;
    stats_out[3] = 0;
    if (n_tets <= 0) {
        return;
    }

    FaceRecord *records = (FaceRecord *)malloc((size_t)n_faces * sizeof(FaceRecord));
    if (records == NULL) {
        stats_out[0] = -1;
        return;
    }

    long r = 0;
    for (int t = 0; t < n_tets; ++t) {
        long vv[4] = {
            tets[(ptrdiff_t)t*4 + 0],
            tets[(ptrdiff_t)t*4 + 1],
            tets[(ptrdiff_t)t*4 + 2],
            tets[(ptrdiff_t)t*4 + 3],
        };
        for (int s = 0; s < 4; ++s) {
            long a = vv[FACE_VERTS[s][0]];
            long b = vv[FACE_VERTS[s][1]];
            long c = vv[FACE_VERTS[s][2]];
            _sort3_long(&a, &b, &c);
            records[r].a = a;
            records[r].b = b;
            records[r].c = c;
            records[r].tet = (long)t;
            records[r].slot = (long)s;
            ++r;
        }
    }

    qsort(records, (size_t)n_faces, sizeof(FaceRecord), _cmp_face_record);

    long n_unique = 0;
    long n_bnd = 0;
    long n_int = 0;
    long n_nm = 0;
    long i = 0;
    while (i < n_faces) {
        long j = i + 1;
        while (
            j < n_faces
            && records[j].a == records[i].a
            && records[j].b == records[i].b
            && records[j].c == records[i].c
        ) {
            ++j;
        }
        long cnt = j - i;
        ++n_unique;
        if (cnt == 1) {
            ++n_bnd;
        } else if (cnt == 2) {
            ++n_int;
            long t0 = records[i].tet;
            long f0 = records[i].slot;
            long t1 = records[i + 1].tet;
            long f1 = records[i + 1].slot;
            adj_out[t0 * 4 + f0] = t1;
            adj_out[t1 * 4 + f1] = t0;
        } else {
            ++n_nm;
        }
        i = j;
    }

    stats_out[0] = n_unique;
    stats_out[1] = n_bnd;
    stats_out[2] = n_int;
    stats_out[3] = n_nm;
    free(records);
}

typedef struct {
    long a;
    long b;
    double q;
} FlipCandidate;

typedef struct {
    long u;
    long v;
    double q;
} SwapCandidate;

static int _cmp_flip_candidate_q(const void *pa, const void *pb)
{
    const FlipCandidate *a = (const FlipCandidate *)pa;
    const FlipCandidate *b = (const FlipCandidate *)pb;
    if (a->q < b->q) return -1;
    if (a->q > b->q) return 1;
    if (a->a < b->a) return -1;
    if (a->a > b->a) return 1;
    if (a->b < b->b) return -1;
    if (a->b > b->b) return 1;
    return 0;
}

static int _cmp_swap_candidate_q(const void *pa, const void *pb)
{
    const SwapCandidate *a = (const SwapCandidate *)pa;
    const SwapCandidate *b = (const SwapCandidate *)pb;
    if (a->q < b->q) return -1;
    if (a->q > b->q) return 1;
    return 0;
}

/* -----------------------------------------------------------------------
 * screen_flip_candidates_batch
 * -----------------------------------------------------------------------
 * pairs_out is allocated by the caller with capacity n_tets*4 rows.
 * counts_out = [n_internal_faces, n_flip_candidates], or [-1, 0] on failure.
 * ----------------------------------------------------------------------- */
void screen_flip_candidates_batch(const long *adj, int n_tets,
                                  const double *q,
                                  double q_threshold,
                                  long *pairs_out,
                                  double *q_out,
                                  long *counts_out)
{
    counts_out[0] = 0;
    counts_out[1] = 0;
    if (n_tets <= 0) {
        return;
    }

    long cap = (long)n_tets * 4L;
    FlipCandidate *candidates = (FlipCandidate *)malloc((size_t)cap * sizeof(FlipCandidate));
    if (candidates == NULL) {
        counts_out[0] = -1;
        return;
    }

    long n_internal = 0;
    long n_candidates = 0;
    for (int ti = 0; ti < n_tets; ++ti) {
        for (int fi = 0; fi < 4; ++fi) {
            long tj = adj[(ptrdiff_t)ti*4 + fi];
            if (tj <= ti) {
                continue;
            }
            ++n_internal;
            double worst = q[ti] < q[tj] ? q[ti] : q[tj];
            if (worst < q_threshold) {
                candidates[n_candidates].a = (long)ti;
                candidates[n_candidates].b = tj;
                candidates[n_candidates].q = worst;
                ++n_candidates;
            }
        }
    }

    if (n_candidates > 0) {
        qsort(candidates, (size_t)n_candidates, sizeof(FlipCandidate), _cmp_flip_candidate_q);
    }
    for (long i = 0; i < n_candidates; ++i) {
        pairs_out[i*2 + 0] = candidates[i].a;
        pairs_out[i*2 + 1] = candidates[i].b;
        q_out[i] = candidates[i].q;
    }
    counts_out[0] = n_internal;
    counts_out[1] = n_candidates;
    free(candidates);
}

/* -----------------------------------------------------------------------
 * screen_swap_candidates_batch
 * -----------------------------------------------------------------------
 * Groups all tet edges and emits candidate edges with incident count 2..7
 * and worst incident Q below threshold.
 * counts_out = [n_internal_edges, n_candidates, n_2_3_shell, n_4_7_shell],
 * or [-1, 0, 0, 0] on allocation failure.
 * ----------------------------------------------------------------------- */
void screen_swap_candidates_batch(const long *tets, int n_tets,
                                  const double *q,
                                  double q_threshold,
                                  long *edges_out,
                                  double *q_out,
                                  long *counts_out)
{
    const int pairs[6][2] = {
        {0, 1}, {0, 2}, {0, 3}, {1, 2}, {1, 3}, {2, 3},
    };
    counts_out[0] = 0;
    counts_out[1] = 0;
    counts_out[2] = 0;
    counts_out[3] = 0;
    if (n_tets <= 0) {
        return;
    }

    long n_records = (long)n_tets * 6L;
    EdgeRecord *records = (EdgeRecord *)malloc((size_t)n_records * sizeof(EdgeRecord));
    SwapCandidate *candidates = (SwapCandidate *)malloc((size_t)n_records * sizeof(SwapCandidate));
    if (records == NULL || candidates == NULL) {
        free(records);
        free(candidates);
        counts_out[0] = -1;
        return;
    }

    long r = 0;
    for (int t = 0; t < n_tets; ++t) {
        long ids[4] = {
            tets[(ptrdiff_t)t*4 + 0],
            tets[(ptrdiff_t)t*4 + 1],
            tets[(ptrdiff_t)t*4 + 2],
            tets[(ptrdiff_t)t*4 + 3],
        };
        for (int k = 0; k < 6; ++k) {
            long u = ids[pairs[k][0]];
            long v = ids[pairs[k][1]];
            if (v < u) {
                long tmp = u;
                u = v;
                v = tmp;
            }
            records[r].u = u;
            records[r].v = v;
            records[r].tet = (long)t;
            records[r].len = 0.0;
            ++r;
        }
    }

    qsort(records, (size_t)n_records, sizeof(EdgeRecord), _cmp_edge_record);

    long n_internal = 0;
    long n_candidates = 0;
    long n_2_3 = 0;
    long n_4_7 = 0;
    long i = 0;
    while (i < n_records) {
        long j = i + 1;
        double worst_q = q[records[i].tet];
        while (j < n_records && records[j].u == records[i].u && records[j].v == records[i].v) {
            double qj = q[records[j].tet];
            if (qj < worst_q) {
                worst_q = qj;
            }
            ++j;
        }
        long cnt = j - i;
        if (cnt >= 2) {
            ++n_internal;
            if (cnt == 2 || cnt == 3) {
                ++n_2_3;
            } else if (cnt >= 4 && cnt <= 7) {
                ++n_4_7;
            }
            if (worst_q < q_threshold && cnt <= 7) {
                candidates[n_candidates].u = records[i].u;
                candidates[n_candidates].v = records[i].v;
                candidates[n_candidates].q = worst_q;
                ++n_candidates;
            }
        }
        i = j;
    }

    for (long k = 0; k < n_candidates; ++k) {
        edges_out[k*2 + 0] = candidates[k].u;
        edges_out[k*2 + 1] = candidates[k].v;
        q_out[k] = candidates[k].q;
    }
    counts_out[0] = n_internal;
    counts_out[1] = n_candidates;
    counts_out[2] = n_2_3;
    counts_out[3] = n_4_7;

    free(records);
    free(candidates);
}

typedef struct {
    long u;
    long v;
} SurfaceEdge;

static int _cmp_surface_edge(const void *pa, const void *pb)
{
    const SurfaceEdge *a = (const SurfaceEdge *)pa;
    const SurfaceEdge *b = (const SurfaceEdge *)pb;
    if (a->u < b->u) return -1;
    if (a->u > b->u) return 1;
    if (a->v < b->v) return -1;
    if (a->v > b->v) return 1;
    return 0;
}

static int _cmp_double_value(const void *pa, const void *pb)
{
    double a = *(const double *)pa;
    double b = *(const double *)pb;
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
}

static double _percentile_sorted_linear(const double *values, long n, double pct)
{
    if (n <= 0) {
        return 0.0;
    }
    if (n == 1) {
        return values[0];
    }
    double pos = ((double)n - 1.0) * pct / 100.0;
    long lo = (long)floor(pos);
    long hi = (long)ceil(pos);
    double frac = pos - (double)lo;
    return values[lo] * (1.0 - frac) + values[hi] * frac;
}

static long _histogram_kth_value(const long *hist, long hist_len, long kth)
{
    long seen = 0;
    for (long i = 0; i < hist_len; ++i) {
        seen += hist[i];
        if (kth < seen) {
            return i;
        }
    }
    return hist_len > 0 ? hist_len - 1 : 0;
}

static void _swap_double(double *a, double *b)
{
    double tmp = *a;
    *a = *b;
    *b = tmp;
}

static double _quickselect_double(double *values, long n, long kth)
{
    long left = 0;
    long right = n - 1;
    while (left < right) {
        double pivot = values[(left + right) / 2];
        long i = left;
        long j = right;
        while (i <= j) {
            while (values[i] < pivot) ++i;
            while (values[j] > pivot) --j;
            if (i <= j) {
                _swap_double(&values[i], &values[j]);
                ++i;
                --j;
            }
        }
        if (kth <= j) {
            right = j;
        } else if (kth >= i) {
            left = i;
        } else {
            return values[kth];
        }
    }
    return values[left];
}

/* -----------------------------------------------------------------------
 * tet_vertex_valence_batch
 * -----------------------------------------------------------------------
 * valence_out has shape (n_verts,).
 * stats_out = [n_used, valence_min, valence_max, n_above_50, n_isolated].
 * float_out = [valence_mean, valence_p99].
 * stats_out[0] = -1 on allocation failure.
 * ----------------------------------------------------------------------- */
void tet_vertex_valence_batch(const long *tets, int n_tets,
                              int n_verts,
                              long *valence_out,
                              long *stats_out,
                              double *float_out)
{
    stats_out[0] = 0;
    stats_out[1] = 0;
    stats_out[2] = 0;
    stats_out[3] = 0;
    stats_out[4] = n_verts > 0 ? n_verts : 0;
    float_out[0] = 0.0;
    float_out[1] = 0.0;

    for (int v = 0; v < n_verts; ++v) {
        valence_out[v] = 0;
    }
    if (n_tets <= 0 || n_verts <= 0) {
        return;
    }

    for (int t = 0; t < n_tets; ++t) {
        long a = tets[(ptrdiff_t)t*4 + 0];
        long b = tets[(ptrdiff_t)t*4 + 1];
        long c = tets[(ptrdiff_t)t*4 + 2];
        long d = tets[(ptrdiff_t)t*4 + 3];
        if (a >= 0 && a < n_verts) valence_out[a] += 1;
        if (b >= 0 && b < n_verts) valence_out[b] += 1;
        if (c >= 0 && c < n_verts) valence_out[c] += 1;
        if (d >= 0 && d < n_verts) valence_out[d] += 1;
    }

    long n_used = 0;
    long n_isolated = 0;
    long n_above_50 = 0;
    long val_min = 0;
    long val_max = 0;
    double sum = 0.0;
    for (int v = 0; v < n_verts; ++v) {
        long val = valence_out[v];
        if (val > 0) {
            if (n_used == 0 || val < val_min) val_min = val;
            if (val > val_max) val_max = val;
            if (val > 50) ++n_above_50;
            sum += (double)val;
            ++n_used;
        } else {
            ++n_isolated;
        }
    }

    stats_out[0] = n_used;
    stats_out[1] = val_min;
    stats_out[2] = val_max;
    stats_out[3] = n_above_50;
    stats_out[4] = n_isolated;
    if (n_used <= 0) {
        return;
    }
    float_out[0] = sum / (double)n_used;

    long hist_len = val_max + 1;
    long *hist = (long *)calloc((size_t)hist_len, sizeof(long));
    if (hist == NULL) {
        stats_out[0] = -1;
        return;
    }
    for (int v = 0; v < n_verts; ++v) {
        long val = valence_out[v];
        if (val > 0) {
            hist[val] += 1;
        }
    }

    double pos = ((double)n_used - 1.0) * 99.0 / 100.0;
    long lo = (long)floor(pos);
    long hi = (long)ceil(pos);
    double frac = pos - (double)lo;
    long lo_val = _histogram_kth_value(hist, hist_len, lo);
    long hi_val = _histogram_kth_value(hist, hist_len, hi);
    float_out[1] = (double)lo_val * (1.0 - frac) + (double)hi_val * frac;
    free(hist);
}

/* -----------------------------------------------------------------------
 * tet_boundary_vertex_stats_batch
 * -----------------------------------------------------------------------
 * counts_out = [n_boundary_tets, n_interior_tets].
 * A tet is boundary if at least one vertex id is below n_surface_verts.
 * ----------------------------------------------------------------------- */
void tet_boundary_vertex_stats_batch(const long *tets, int n_tets,
                                     int n_surface_verts,
                                     long *counts_out)
{
    long n_boundary = 0;
    if (n_tets <= 0) {
        counts_out[0] = 0;
        counts_out[1] = 0;
        return;
    }

    for (int t = 0; t < n_tets; ++t) {
        long a = tets[(ptrdiff_t)t*4 + 0];
        long b = tets[(ptrdiff_t)t*4 + 1];
        long c = tets[(ptrdiff_t)t*4 + 2];
        long d = tets[(ptrdiff_t)t*4 + 3];
        if (a < n_surface_verts || b < n_surface_verts ||
            c < n_surface_verts || d < n_surface_verts) {
            ++n_boundary;
        }
    }
    counts_out[0] = n_boundary;
    counts_out[1] = (long)n_tets - n_boundary;
}

/* -----------------------------------------------------------------------
 * tet_edge_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [edge_min, edge_max, edge_mean, edge_p99, aniso_max, aniso_mean].
 * counts_out = [n_sliver], or [-1] on allocation failure.
 * ----------------------------------------------------------------------- */
void tet_edge_stats_batch(const double *pts, int n_pts,
                          const long *tets, int n_tets,
                          double sliver_aniso,
                          double *stats_out,
                          long *counts_out)
{
    (void)n_pts;
    for (int i = 0; i < 6; ++i) {
        stats_out[i] = 0.0;
    }
    counts_out[0] = 0;
    if (n_tets <= 0) {
        return;
    }

    long n_edges = (long)n_tets * 6L;
    double *lengths = (double *)malloc((size_t)n_edges * sizeof(double));
    if (lengths == NULL) {
        counts_out[0] = -1;
        return;
    }

    double edge_min = 0.0;
    double edge_max = 0.0;
    double edge_sum = 0.0;
    double aniso_max = 0.0;
    double aniso_sum = 0.0;
    long n_sliver = 0;
    long r = 0;

    for (int t = 0; t < n_tets; ++t) {
        long ia = tets[(ptrdiff_t)t*4 + 0];
        long ib = tets[(ptrdiff_t)t*4 + 1];
        long ic = tets[(ptrdiff_t)t*4 + 2];
        long id = tets[(ptrdiff_t)t*4 + 3];
        const double *A = _pt(pts, ia);
        const double *B = _pt(pts, ib);
        const double *C = _pt(pts, ic);
        const double *D = _pt(pts, id);

        double e[6];
        e[0] = sqrt(_dist2(A, B));
        e[1] = sqrt(_dist2(A, C));
        e[2] = sqrt(_dist2(A, D));
        e[3] = sqrt(_dist2(B, C));
        e[4] = sqrt(_dist2(B, D));
        e[5] = sqrt(_dist2(C, D));

        double tet_min = e[0];
        double tet_max = e[0];
        for (int k = 0; k < 6; ++k) {
            double val = e[k];
            lengths[r++] = val;
            if (r == 1 || val < edge_min) edge_min = val;
            if (r == 1 || val > edge_max) edge_max = val;
            if (val < tet_min) tet_min = val;
            if (val > tet_max) tet_max = val;
            edge_sum += val;
        }

        double aniso = 0.0;
        if (tet_min > 1e-30) {
            aniso = tet_max / tet_min;
        }
        if (aniso > aniso_max) aniso_max = aniso;
        aniso_sum += aniso;
        if (aniso > sliver_aniso) ++n_sliver;
    }

    double pos = ((double)n_edges - 1.0) * 99.0 / 100.0;
    long lo = (long)floor(pos);
    long hi = (long)ceil(pos);
    double frac = pos - (double)lo;
    double lo_val = _quickselect_double(lengths, n_edges, lo);
    double hi_val = lo == hi ? lo_val : _quickselect_double(lengths, n_edges, hi);

    stats_out[0] = edge_min;
    stats_out[1] = edge_max;
    stats_out[2] = edge_sum / (double)n_edges;
    stats_out[3] = lo_val * (1.0 - frac) + hi_val * frac;
    stats_out[4] = aniso_max;
    stats_out[5] = aniso_sum / (double)n_tets;
    counts_out[0] = n_sliver;
    free(lengths);
}

/* -----------------------------------------------------------------------
 * tet_volume_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [q_min, q_max, q_mean, q_p5, q_p50, q_p95,
 *              vol_min, vol_max, vol_total].
 * counts_out = [n_negative_volume], or [-1] on allocation failure.
 * hist_out has shape (n_bins,).
 * ----------------------------------------------------------------------- */
void tet_volume_stats_batch(const double *pts, int n_pts,
                            const long *tets, int n_tets,
                            int n_bins,
                            double *stats_out,
                            long *counts_out,
                            long *hist_out)
{
    (void)n_pts;
    for (int i = 0; i < 9; ++i) {
        stats_out[i] = 0.0;
    }
    counts_out[0] = 0;
    for (int i = 0; i < n_bins; ++i) {
        hist_out[i] = 0;
    }
    if (n_tets <= 0) {
        return;
    }

    double *qualities = (double *)malloc((size_t)n_tets * sizeof(double));
    if (qualities == NULL) {
        counts_out[0] = -1;
        return;
    }

    double q_min = 0.0;
    double q_max = 0.0;
    double q_sum = 0.0;
    double vol_min = 0.0;
    double vol_max = 0.0;
    double vol_total = 0.0;
    long n_negative = 0;

    for (int t = 0; t < n_tets; ++t) {
        long ia = tets[(ptrdiff_t)t*4 + 0];
        long ib = tets[(ptrdiff_t)t*4 + 1];
        long ic = tets[(ptrdiff_t)t*4 + 2];
        long id = tets[(ptrdiff_t)t*4 + 3];
        const double *A = _pt(pts, ia);
        const double *B = _pt(pts, ib);
        const double *C = _pt(pts, ic);
        const double *D = _pt(pts, id);

        double e0[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double e1[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double e2[3] = {D[0]-A[0], D[1]-A[1], D[2]-A[2]};
        double e3[3] = {C[0]-B[0], C[1]-B[1], C[2]-B[2]};
        double e4[3] = {D[0]-B[0], D[1]-B[1], D[2]-B[2]};
        double e5[3] = {D[0]-C[0], D[1]-C[1], D[2]-C[2]};
        double e_sq_sum =
            _dot3(e0, e0) + _dot3(e1, e1) + _dot3(e2, e2) +
            _dot3(e3, e3) + _dot3(e4, e4) + _dot3(e5, e5);

        double cr[3];
        _cross3(e1, e2, cr);
        double vol6 = _dot3(e0, cr);
        if (vol6 < 0.0) ++n_negative;
        double vol = fabs(vol6) / 6.0;
        double q = 0.0;
        if (e_sq_sum > 1e-30) {
            q = 12.0 * pow(3.0 * vol, 2.0 / 3.0) / e_sq_sum;
            if (q < 0.0) q = 0.0;
            if (q > 1.0) q = 1.0;
        }

        qualities[t] = q;
        if (t == 0 || q < q_min) q_min = q;
        if (t == 0 || q > q_max) q_max = q;
        q_sum += q;
        if (t == 0 || vol < vol_min) vol_min = vol;
        if (t == 0 || vol > vol_max) vol_max = vol;
        vol_total += vol;

        if (n_bins > 0) {
            int bin = (int)floor(q * (double)n_bins);
            if (bin < 0) bin = 0;
            if (bin >= n_bins) bin = n_bins - 1;
            hist_out[bin] += 1;
        }
    }

    double pos5 = ((double)n_tets - 1.0) * 5.0 / 100.0;
    long lo5 = (long)floor(pos5);
    long hi5 = (long)ceil(pos5);
    double frac5 = pos5 - (double)lo5;
    double lo5_val = _quickselect_double(qualities, n_tets, lo5);
    double hi5_val = lo5 == hi5 ? lo5_val : _quickselect_double(qualities, n_tets, hi5);

    double pos50 = ((double)n_tets - 1.0) * 50.0 / 100.0;
    long lo50 = (long)floor(pos50);
    long hi50 = (long)ceil(pos50);
    double frac50 = pos50 - (double)lo50;
    double lo50_val = _quickselect_double(qualities, n_tets, lo50);
    double hi50_val = lo50 == hi50 ? lo50_val : _quickselect_double(qualities, n_tets, hi50);

    double pos95 = ((double)n_tets - 1.0) * 95.0 / 100.0;
    long lo95 = (long)floor(pos95);
    long hi95 = (long)ceil(pos95);
    double frac95 = pos95 - (double)lo95;
    double lo95_val = _quickselect_double(qualities, n_tets, lo95);
    double hi95_val = lo95 == hi95 ? lo95_val : _quickselect_double(qualities, n_tets, hi95);

    stats_out[0] = q_min;
    stats_out[1] = q_max;
    stats_out[2] = q_sum / (double)n_tets;
    stats_out[3] = lo5_val * (1.0 - frac5) + hi5_val * frac5;
    stats_out[4] = lo50_val * (1.0 - frac50) + hi50_val * frac50;
    stats_out[5] = lo95_val * (1.0 - frac95) + hi95_val * frac95;
    stats_out[6] = vol_min;
    stats_out[7] = vol_max;
    stats_out[8] = vol_total;
    counts_out[0] = n_negative;
    free(qualities);
}

/* -----------------------------------------------------------------------
 * tet_inradius_batch
 * -----------------------------------------------------------------------
 * radii_out has shape (n_tets,).
 * stats_out = [r_min, r_max, r_mean].
 * counts_out = [n_zero_radius].
 * ----------------------------------------------------------------------- */
void tet_inradius_batch(const double *pts, int n_pts,
                        const long *tets, int n_tets,
                        double *radii_out,
                        double *stats_out,
                        long *counts_out)
{
    (void)n_pts;
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    counts_out[0] = 0;
    if (n_tets <= 0) {
        return;
    }

    double r_min = 0.0;
    double r_max = 0.0;
    double r_sum = 0.0;
    long n_zero = 0;
    for (int t = 0; t < n_tets; ++t) {
        long ia = tets[(ptrdiff_t)t*4 + 0];
        long ib = tets[(ptrdiff_t)t*4 + 1];
        long ic = tets[(ptrdiff_t)t*4 + 2];
        long id = tets[(ptrdiff_t)t*4 + 3];
        const double *A = _pt(pts, ia);
        const double *B = _pt(pts, ib);
        const double *C = _pt(pts, ic);
        const double *D = _pt(pts, id);

        double ba[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ca[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double da[3] = {D[0]-A[0], D[1]-A[1], D[2]-A[2]};
        double cr[3];
        _cross3(ba, ca, cr);
        double vol = fabs(_dot3(cr, da)) / 6.0;

        double s =
            _tri_area3(A, B, C) + _tri_area3(A, B, D) +
            _tri_area3(A, C, D) + _tri_area3(B, C, D);
        double r = 0.0;
        if (s > 1e-30) {
            r = 3.0 * vol / s;
        }
        radii_out[t] = r;
        if (t == 0 || r < r_min) r_min = r;
        if (t == 0 || r > r_max) r_max = r;
        r_sum += r;
        if (r < 1e-12) ++n_zero;
    }

    stats_out[0] = r_min;
    stats_out[1] = r_max;
    stats_out[2] = r_sum / (double)n_tets;
    counts_out[0] = n_zero;
}

/* -----------------------------------------------------------------------
 * tet_circumsphere_batch
 * -----------------------------------------------------------------------
 * centers_out has shape (n_tets, 3), radii_out has shape (n_tets,).
 * stats_out = [radius_min_positive, radius_max_positive, radius_mean_positive].
 * counts_out = [n_degenerate].
 * ----------------------------------------------------------------------- */
void tet_circumsphere_batch(const double *pts, int n_pts,
                            const long *tets, int n_tets,
                            double *centers_out,
                            double *radii_out,
                            double *stats_out,
                            long *counts_out)
{
    (void)n_pts;
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    counts_out[0] = 0;
    if (n_tets <= 0) {
        return;
    }

    long n_deg = 0;
    long n_positive = 0;
    double r_min = 0.0;
    double r_max = 0.0;
    double r_sum = 0.0;

    for (int t = 0; t < n_tets; ++t) {
        long ia = tets[(ptrdiff_t)t*4 + 0];
        long ib = tets[(ptrdiff_t)t*4 + 1];
        long ic = tets[(ptrdiff_t)t*4 + 2];
        long id = tets[(ptrdiff_t)t*4 + 3];
        const double *A = _pt(pts, ia);
        const double *B = _pt(pts, ib);
        const double *C = _pt(pts, ic);
        const double *D = _pt(pts, id);

        double m00 = 2.0 * (B[0] - A[0]);
        double m01 = 2.0 * (B[1] - A[1]);
        double m02 = 2.0 * (B[2] - A[2]);
        double m10 = 2.0 * (C[0] - A[0]);
        double m11 = 2.0 * (C[1] - A[1]);
        double m12 = 2.0 * (C[2] - A[2]);
        double m20 = 2.0 * (D[0] - A[0]);
        double m21 = 2.0 * (D[1] - A[1]);
        double m22 = 2.0 * (D[2] - A[2]);
        double rhs0 = _dot3(B, B) - _dot3(A, A);
        double rhs1 = _dot3(C, C) - _dot3(A, A);
        double rhs2 = _dot3(D, D) - _dot3(A, A);

        double det = _det3(m00, m01, m02, m10, m11, m12, m20, m21, m22);
        double cx;
        double cy;
        double cz;
        double radius;
        if (fabs(det) < 1e-30) {
            cx = A[0];
            cy = A[1];
            cz = A[2];
            radius = 0.0;
            ++n_deg;
        } else {
            cx = _det3(rhs0, m01, m02, rhs1, m11, m12, rhs2, m21, m22) / det;
            cy = _det3(m00, rhs0, m02, m10, rhs1, m12, m20, rhs2, m22) / det;
            cz = _det3(m00, m01, rhs0, m10, m11, rhs1, m20, m21, rhs2) / det;
            double dx = A[0] - cx;
            double dy = A[1] - cy;
            double dz = A[2] - cz;
            radius = sqrt(dx*dx + dy*dy + dz*dz);
        }

        centers_out[(ptrdiff_t)t*3 + 0] = cx;
        centers_out[(ptrdiff_t)t*3 + 1] = cy;
        centers_out[(ptrdiff_t)t*3 + 2] = cz;
        radii_out[t] = radius;
        if (radius > 0.0) {
            if (n_positive == 0 || radius < r_min) r_min = radius;
            if (n_positive == 0 || radius > r_max) r_max = radius;
            r_sum += radius;
            ++n_positive;
        }
    }

    stats_out[0] = n_positive > 0 ? r_min : 0.0;
    stats_out[1] = n_positive > 0 ? r_max : 0.0;
    stats_out[2] = n_positive > 0 ? r_sum / (double)n_positive : 0.0;
    counts_out[0] = n_deg;
}

/* -----------------------------------------------------------------------
 * tet_aniso_tensor_batch
 * -----------------------------------------------------------------------
 * ratio_out has shape (n_tets,).
 * stats_out = [aniso_min, aniso_max, aniso_mean, aniso_p99].
 * counts_out = [n_above_5].
 * ----------------------------------------------------------------------- */
void tet_aniso_tensor_batch(const double *pts, int n_pts,
                            const long *tets, int n_tets,
                            double *ratio_out,
                            double *stats_out,
                            long *counts_out)
{
    (void)n_pts;
    for (int i = 0; i < 4; ++i) {
        stats_out[i] = 0.0;
    }
    counts_out[0] = 0;
    if (n_tets <= 0) {
        return;
    }

    double *ratio_copy = (double *)malloc((size_t)n_tets * sizeof(double));
    if (ratio_copy == NULL) {
        counts_out[0] = -1;
        return;
    }

    double ratio_min = 0.0;
    double ratio_max = 0.0;
    double ratio_sum = 0.0;
    long n_above_5 = 0;

    for (int t = 0; t < n_tets; ++t) {
        long ia = tets[(ptrdiff_t)t*4 + 0];
        long ib = tets[(ptrdiff_t)t*4 + 1];
        long ic = tets[(ptrdiff_t)t*4 + 2];
        long id = tets[(ptrdiff_t)t*4 + 3];
        const double *A = _pt(pts, ia);
        const double *B = _pt(pts, ib);
        const double *C = _pt(pts, ic);
        const double *D = _pt(pts, id);
        double e[6][3] = {
            {B[0]-A[0], B[1]-A[1], B[2]-A[2]},
            {C[0]-A[0], C[1]-A[1], C[2]-A[2]},
            {D[0]-A[0], D[1]-A[1], D[2]-A[2]},
            {C[0]-B[0], C[1]-B[1], C[2]-B[2]},
            {D[0]-B[0], D[1]-B[1], D[2]-B[2]},
            {D[0]-C[0], D[1]-C[1], D[2]-C[2]},
        };

        double m00 = 0.0;
        double m01 = 0.0;
        double m02 = 0.0;
        double m11 = 0.0;
        double m12 = 0.0;
        double m22 = 0.0;
        for (int k = 0; k < 6; ++k) {
            m00 += e[k][0] * e[k][0];
            m01 += e[k][0] * e[k][1];
            m02 += e[k][0] * e[k][2];
            m11 += e[k][1] * e[k][1];
            m12 += e[k][1] * e[k][2];
            m22 += e[k][2] * e[k][2];
        }
        m00 /= 6.0;
        m01 /= 6.0;
        m02 /= 6.0;
        m11 /= 6.0;
        m12 /= 6.0;
        m22 /= 6.0;

        double lam_min;
        double lam_max;
        _sym3_eig_min_max(m00, m01, m02, m11, m12, m22, &lam_min, &lam_max);
        double ratio = 1e6;
        if (lam_min > 1e-30 && lam_max >= 0.0) {
            ratio = sqrt(lam_max / lam_min);
        }
        ratio_out[t] = ratio;
        ratio_copy[t] = ratio;
        if (t == 0 || ratio < ratio_min) ratio_min = ratio;
        if (t == 0 || ratio > ratio_max) ratio_max = ratio;
        ratio_sum += ratio;
        if (ratio > 5.0) ++n_above_5;
    }

    double pos = ((double)n_tets - 1.0) * 99.0 / 100.0;
    long lo = (long)floor(pos);
    long hi = (long)ceil(pos);
    double frac = pos - (double)lo;
    double lo_val = _quickselect_double(ratio_copy, n_tets, lo);
    double hi_val = lo == hi ? lo_val : _quickselect_double(ratio_copy, n_tets, hi);

    stats_out[0] = ratio_min;
    stats_out[1] = ratio_max;
    stats_out[2] = ratio_sum / (double)n_tets;
    stats_out[3] = lo_val * (1.0 - frac) + hi_val * frac;
    counts_out[0] = n_above_5;
    free(ratio_copy);
}

/* Hex, BL, snap, and polyhedral ctypes fallback kernels. */
#include "tet_kernels_hex_poly.inc"

/* NativeMeshChecker ctypes fallback kernels. */
#include "tet_kernels_native_checker.inc"

/* Surface analysis and repair ctypes fallback kernels. */
#include "tet_kernels_surface.inc"

/* -----------------------------------------------------------------------
 * build_face_to_tets
 * -----------------------------------------------------------------------
 * For n_tets tetrahedra, each with 4 faces, output:
 *   faces_out  : [n_tets*4 × 3]  sorted face vertices (a <= b <= c)
 *   tet_idx_out: [n_tets*4]      which tet
 *   slot_out   : [n_tets*4]      local slot 0..3
 *
 * Local slot convention (matches flip.py _face_map_vectorized):
 *   slot 0 = opposite to vertex 0 → face (v1, v2, v3)
 *   slot 1 = opposite to vertex 1 → face (v0, v2, v3)
 *   slot 2 = opposite to vertex 2 → face (v0, v1, v3)
 *   slot 3 = opposite to vertex 3 → face (v0, v1, v2)
 *
 * Returns number of entries written (= n_tets*4), or -1 if overflow.
 * ----------------------------------------------------------------------- */
int build_face_to_tets(const long *tets, int n_tets,
                       long *faces_out, long *tet_idx_out, long *slot_out,
                       int max_entries)
{
    int total = n_tets * 4;
    if (total > max_entries) return -1;

    /* Local face vertex index sets, indexed by slot */
    static const int FACE_VERTS[4][3] = {
        {1, 2, 3},  /* slot 0: opposite v0 */
        {0, 2, 3},  /* slot 1: opposite v1 */
        {0, 1, 3},  /* slot 2: opposite v2 */
        {0, 1, 2},  /* slot 3: opposite v3 */
    };

    int out_idx = 0;
    for (int t = 0; t < n_tets; ++t) {
        long v0 = tets[(ptrdiff_t)t*4 + 0];
        long v1 = tets[(ptrdiff_t)t*4 + 1];
        long v2 = tets[(ptrdiff_t)t*4 + 2];
        long v3 = tets[(ptrdiff_t)t*4 + 3];
        long vv[4] = {v0, v1, v2, v3};

        for (int s = 0; s < 4; ++s) {
            long fa = vv[FACE_VERTS[s][0]];
            long fb = vv[FACE_VERTS[s][1]];
            long fc = vv[FACE_VERTS[s][2]];
            /* sort fa <= fb <= fc */
            long tmp;
            if (fa > fb) { tmp = fa; fa = fb; fb = tmp; }
            if (fb > fc) { tmp = fb; fb = fc; fc = tmp; }
            if (fa > fb) { tmp = fa; fa = fb; fb = tmp; }

            faces_out[(ptrdiff_t)out_idx*3 + 0] = fa;
            faces_out[(ptrdiff_t)out_idx*3 + 1] = fb;
            faces_out[(ptrdiff_t)out_idx*3 + 2] = fc;
            tet_idx_out[out_idx] = (long)t;
            slot_out[out_idx]    = (long)s;
            ++out_idx;
        }
    }
    return out_idx;
}

/* -----------------------------------------------------------------------
 * build_edge_to_tets
 * -----------------------------------------------------------------------
 * For n_tets tetrahedra, each with 6 edges, output:
 *   edges_out  : [n_tets*6 × 2]  sorted edge pairs (a < b)
 *   tet_idx_out: [n_tets*6]      which tet
 *
 * Returns number of entries written (= n_tets*6), or -1 if overflow.
 * ----------------------------------------------------------------------- */
int build_edge_to_tets(const long *tets, int n_tets,
                       long *edges_out, long *tet_idx_out,
                       int max_entries)
{
    int total = n_tets * 6;
    if (total > max_entries) return -1;

    static const int EDGE_PAIRS[6][2] = {
        {0, 1}, {0, 2}, {0, 3},
        {1, 2}, {1, 3}, {2, 3},
    };

    int out_idx = 0;
    for (int t = 0; t < n_tets; ++t) {
        long v0 = tets[(ptrdiff_t)t*4 + 0];
        long v1 = tets[(ptrdiff_t)t*4 + 1];
        long v2 = tets[(ptrdiff_t)t*4 + 2];
        long v3 = tets[(ptrdiff_t)t*4 + 3];
        long vv[4] = {v0, v1, v2, v3};

        for (int e = 0; e < 6; ++e) {
            long ea = vv[EDGE_PAIRS[e][0]];
            long eb = vv[EDGE_PAIRS[e][1]];
            if (ea > eb) { long tmp = ea; ea = eb; eb = tmp; }

            edges_out[(ptrdiff_t)out_idx*2 + 0] = ea;
            edges_out[(ptrdiff_t)out_idx*2 + 1] = eb;
            tet_idx_out[out_idx] = (long)t;
            ++out_idx;
        }
    }
    return out_idx;
}

/* -----------------------------------------------------------------------
 * edge_lengths_batch
 * -----------------------------------------------------------------------
 * Compute Euclidean length for each (u, v) edge pair.
 *   edges[i*2]   = u
 *   edges[i*2+1] = v
 *   out[i]       = |pts[u] - pts[v]|
 * ----------------------------------------------------------------------- */
void edge_lengths_batch(const double *pts,
                        const long *edges, int n_edges,
                        double *out)
{
    for (int i = 0; i < n_edges; ++i) {
        const double *A = _pt(pts, edges[(ptrdiff_t)i*2 + 0]);
        const double *B = _pt(pts, edges[(ptrdiff_t)i*2 + 1]);
        double dx = A[0]-B[0], dy = A[1]-B[1], dz = A[2]-B[2];
        out[i] = sqrt(dx*dx + dy*dy + dz*dz);
    }
}

/* -----------------------------------------------------------------------
 * metric_edge_lengths_batch
 * -----------------------------------------------------------------------
 * Compute each tet's 6 metric-aware edge lengths.
 * M is row-major [n_pts, 3, 3]. Output is row-major [n_tets, 6].
 * l^2 = d^T (0.5 * (M_u + M_v)) d, where d = pts[u] - pts[v].
 * ----------------------------------------------------------------------- */
void metric_edge_lengths_batch(const double *pts,
                               const long *tets, int n_tets,
                               const double *M,
                               double *out)
{
    static const int EDGE_PAIRS[6][2] = {
        {0, 1}, {0, 2}, {0, 3},
        {1, 2}, {1, 3}, {2, 3},
    };

    for (int t = 0; t < n_tets; ++t) {
        long vv[4] = {
            tets[(ptrdiff_t)t*4 + 0],
            tets[(ptrdiff_t)t*4 + 1],
            tets[(ptrdiff_t)t*4 + 2],
            tets[(ptrdiff_t)t*4 + 3],
        };
        for (int e = 0; e < 6; ++e) {
            long u = vv[EDGE_PAIRS[e][0]];
            long v = vv[EDGE_PAIRS[e][1]];
            const double *P = _pt(pts, u);
            const double *Q = _pt(pts, v);
            double d0 = P[0] - Q[0];
            double d1 = P[1] - Q[1];
            double d2 = P[2] - Q[2];
            const double *Mu = M + (ptrdiff_t)u * 9;
            const double *Mv = M + (ptrdiff_t)v * 9;

            double m00 = 0.5 * (Mu[0] + Mv[0]);
            double m01 = 0.5 * (Mu[1] + Mv[1]);
            double m02 = 0.5 * (Mu[2] + Mv[2]);
            double m10 = 0.5 * (Mu[3] + Mv[3]);
            double m11 = 0.5 * (Mu[4] + Mv[4]);
            double m12 = 0.5 * (Mu[5] + Mv[5]);
            double m20 = 0.5 * (Mu[6] + Mv[6]);
            double m21 = 0.5 * (Mu[7] + Mv[7]);
            double m22 = 0.5 * (Mu[8] + Mv[8]);

            double md0 = m00*d0 + m01*d1 + m02*d2;
            double md1 = m10*d0 + m11*d1 + m12*d2;
            double md2 = m20*d0 + m21*d1 + m22*d2;
            double l2 = d0*md0 + d1*md1 + d2*md2;
            out[(ptrdiff_t)t*6 + e] = sqrt(l2 > 0.0 ? l2 : 0.0);
        }
    }
}
