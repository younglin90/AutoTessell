/*
 * tet_kernels.c — Native C kernels for AutoTessell native_tet hot loops.
 *
 * C99, no external dependencies (only libm).
 *
 * Exported functions (C ABI, all callable via ctypes):
 *
 *   tet_quality_batch      — radius/edge ratio quality per tet
 *   tet_signed_vol6_batch  — signed volume * 6 per tet
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
