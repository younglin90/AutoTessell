/* Surface analysis and repair ctypes fallback kernels.
 * Included from tet_kernels.c after shared math/topology helpers.
 */

static int _cmp_surface_face_key(const void *pa, const void *pb)
{
    const SurfaceFaceKey *a = (const SurfaceFaceKey *)pa;
    const SurfaceFaceKey *b = (const SurfaceFaceKey *)pb;
    if (a->a < b->a) return -1;
    if (a->a > b->a) return 1;
    if (a->b < b->b) return -1;
    if (a->b > b->b) return 1;
    if (a->c < b->c) return -1;
    if (a->c > b->c) return 1;
    if (a->index < b->index) return -1;
    if (a->index > b->index) return 1;
    return 0;
}

typedef struct {
    long x;
    long y;
    long z;
    long index;
} QuantVertexKey;

static int _cmp_quant_vertex_key(const void *pa, const void *pb)
{
    const QuantVertexKey *a = (const QuantVertexKey *)pa;
    const QuantVertexKey *b = (const QuantVertexKey *)pb;
    if (a->x < b->x) return -1;
    if (a->x > b->x) return 1;
    if (a->y < b->y) return -1;
    if (a->y > b->y) return 1;
    if (a->z < b->z) return -1;
    if (a->z > b->z) return 1;
    if (a->index < b->index) return -1;
    if (a->index > b->index) return 1;
    return 0;
}

/* -----------------------------------------------------------------------
 * surface_boundary_edges_batch
 * -----------------------------------------------------------------------
 * faces are triangular (n_faces, 3). edges_out capacity is n_faces*3 rows.
 * n_out[0] = boundary edge count, or -1 on allocation failure.
 * ----------------------------------------------------------------------- */
void surface_boundary_edges_batch(const long *faces, int n_faces,
                                  long *edges_out,
                                  long *n_out)
{
    n_out[0] = 0;
    if (n_faces <= 0) {
        return;
    }

    long n_edges = (long)n_faces * 3L;
    SurfaceEdge *edges = (SurfaceEdge *)malloc((size_t)n_edges * sizeof(SurfaceEdge));
    if (edges == NULL) {
        n_out[0] = -1;
        return;
    }

    long r = 0;
    for (int f = 0; f < n_faces; ++f) {
        long a = faces[(ptrdiff_t)f*3 + 0];
        long b = faces[(ptrdiff_t)f*3 + 1];
        long c = faces[(ptrdiff_t)f*3 + 2];
        long u, v, tmp;

        u = a; v = b;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = b; v = c;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = c; v = a;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;
    }

    qsort(edges, (size_t)n_edges, sizeof(SurfaceEdge), _cmp_surface_edge);

    long out = 0;
    long i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        if (j - i == 1) {
            edges_out[out*2 + 0] = edges[i].u;
            edges_out[out*2 + 1] = edges[i].v;
            ++out;
        }
        i = j;
    }
    n_out[0] = out;
    free(edges);
}

/* -----------------------------------------------------------------------
 * surface_edge_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [n_unique, n_boundary, n_nonmanifold, max_count].
 * stats_out[0] = -1 on allocation failure.
 * ----------------------------------------------------------------------- */
void surface_edge_stats_batch(const long *faces, int n_faces,
                              long *stats_out)
{
    stats_out[0] = 0;
    stats_out[1] = 0;
    stats_out[2] = 0;
    stats_out[3] = 0;
    if (n_faces <= 0) {
        return;
    }

    long n_edges = (long)n_faces * 3L;
    SurfaceEdge *edges = (SurfaceEdge *)malloc((size_t)n_edges * sizeof(SurfaceEdge));
    if (edges == NULL) {
        stats_out[0] = -1;
        return;
    }

    long r = 0;
    for (int f = 0; f < n_faces; ++f) {
        long a = faces[(ptrdiff_t)f*3 + 0];
        long b = faces[(ptrdiff_t)f*3 + 1];
        long c = faces[(ptrdiff_t)f*3 + 2];
        long u, v, tmp;

        u = a; v = b;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = b; v = c;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = c; v = a;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;
    }

    qsort(edges, (size_t)n_edges, sizeof(SurfaceEdge), _cmp_surface_edge);

    long n_unique = 0;
    long n_boundary = 0;
    long n_nonmanifold = 0;
    long max_count = 0;
    long i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        long cnt = j - i;
        ++n_unique;
        if (cnt == 1) {
            ++n_boundary;
        }
        if (cnt >= 3) {
            ++n_nonmanifold;
        }
        if (cnt > max_count) {
            max_count = cnt;
        }
        i = j;
    }

    stats_out[0] = n_unique;
    stats_out[1] = n_boundary;
    stats_out[2] = n_nonmanifold;
    stats_out[3] = max_count;
    free(edges);
}

/* -----------------------------------------------------------------------
 * surface_vertex_valence_batch
 * -----------------------------------------------------------------------
 * face_val_out and edge_val_out have shape (n_verts,).
 * stats_out = [n_used, face_min, face_max, edge_min, edge_max,
 *              n_high_face_valence, n_isolated].
 * mean_out = [face_mean, edge_mean].
 * stats_out[0] = -1 on allocation failure.
 * ----------------------------------------------------------------------- */
void surface_vertex_valence_batch(const long *faces, int n_faces,
                                  int n_verts,
                                  long *face_val_out,
                                  long *edge_val_out,
                                  long *stats_out,
                                  double *mean_out)
{
    stats_out[0] = 0;
    stats_out[1] = 0;
    stats_out[2] = 0;
    stats_out[3] = 0;
    stats_out[4] = 0;
    stats_out[5] = 0;
    stats_out[6] = 0;
    mean_out[0] = 0.0;
    mean_out[1] = 0.0;

    for (int v = 0; v < n_verts; ++v) {
        face_val_out[v] = 0;
        edge_val_out[v] = 0;
    }
    if (n_faces <= 0 || n_verts <= 0) {
        stats_out[6] = n_verts > 0 ? n_verts : 0;
        return;
    }

    long n_edges = (long)n_faces * 3L;
    SurfaceEdge *edges = (SurfaceEdge *)malloc((size_t)n_edges * sizeof(SurfaceEdge));
    if (edges == NULL) {
        stats_out[0] = -1;
        return;
    }

    long r = 0;
    for (int f = 0; f < n_faces; ++f) {
        long a = faces[(ptrdiff_t)f*3 + 0];
        long b = faces[(ptrdiff_t)f*3 + 1];
        long c = faces[(ptrdiff_t)f*3 + 2];
        if (a >= 0 && a < n_verts) face_val_out[a] += 1;
        if (b >= 0 && b < n_verts) face_val_out[b] += 1;
        if (c >= 0 && c < n_verts) face_val_out[c] += 1;

        long u, v, tmp;
        u = a; v = b;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = b; v = c;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = c; v = a;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;
    }

    qsort(edges, (size_t)n_edges, sizeof(SurfaceEdge), _cmp_surface_edge);
    long i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        long u = edges[i].u;
        long v = edges[i].v;
        if (u >= 0 && u < n_verts) edge_val_out[u] += 1;
        if (v >= 0 && v < n_verts) edge_val_out[v] += 1;
        i = j;
    }

    long n_used = 0;
    long n_isolated = 0;
    long n_high = 0;
    long face_min = 0;
    long face_max = 0;
    long edge_min = 0;
    long edge_max = 0;
    double face_sum = 0.0;
    double edge_sum = 0.0;
    for (int v = 0; v < n_verts; ++v) {
        long fv = face_val_out[v];
        long ev = edge_val_out[v];
        if (fv > 0) {
            if (n_used == 0 || fv < face_min) face_min = fv;
            if (n_used == 0 || fv > face_max) face_max = fv;
            if (n_used == 0 || ev < edge_min) edge_min = ev;
            if (n_used == 0 || ev > edge_max) edge_max = ev;
            if (fv >= 12) ++n_high;
            face_sum += (double)fv;
            edge_sum += (double)ev;
            ++n_used;
        } else {
            ++n_isolated;
        }
    }

    stats_out[0] = n_used;
    stats_out[1] = face_min;
    stats_out[2] = face_max;
    stats_out[3] = edge_min;
    stats_out[4] = edge_max;
    stats_out[5] = n_high;
    stats_out[6] = n_isolated;
    if (n_used > 0) {
        mean_out[0] = face_sum / (double)n_used;
        mean_out[1] = edge_sum / (double)n_used;
    }

    free(edges);
}

/* -----------------------------------------------------------------------
 * surface_edge_lengths_stats_batch
 * -----------------------------------------------------------------------
 * lengths_out has shape (n_faces*3) and order [e01, e12, e20] per face.
 * counts_out = [n_unique], or [-1] on allocation failure.
 * aspect_out = [aspect_max, aspect_mean].
 * ----------------------------------------------------------------------- */
void surface_edge_lengths_stats_batch(const double *verts, int n_verts,
                                      const long *faces, int n_faces,
                                      double *lengths_out,
                                      long *counts_out,
                                      double *aspect_out)
{
    (void)n_verts;
    counts_out[0] = 0;
    aspect_out[0] = 0.0;
    aspect_out[1] = 0.0;
    if (n_faces <= 0) {
        return;
    }

    long n_edges = (long)n_faces * 3L;
    SurfaceEdge *edges = (SurfaceEdge *)malloc((size_t)n_edges * sizeof(SurfaceEdge));
    if (edges == NULL) {
        counts_out[0] = -1;
        return;
    }

    double aspect_max = 0.0;
    double aspect_sum = 0.0;
    long r = 0;
    for (int f = 0; f < n_faces; ++f) {
        long ia = faces[(ptrdiff_t)f*3 + 0];
        long ib = faces[(ptrdiff_t)f*3 + 1];
        long ic = faces[(ptrdiff_t)f*3 + 2];
        const double *A = _pt(verts, ia);
        const double *B = _pt(verts, ib);
        const double *C = _pt(verts, ic);

        double e0 = sqrt(_dist2(B, A));
        double e1 = sqrt(_dist2(C, B));
        double e2 = sqrt(_dist2(A, C));
        lengths_out[(ptrdiff_t)f*3 + 0] = e0;
        lengths_out[(ptrdiff_t)f*3 + 1] = e1;
        lengths_out[(ptrdiff_t)f*3 + 2] = e2;

        double mn = e0;
        if (e1 < mn) mn = e1;
        if (e2 < mn) mn = e2;
        double mx = e0;
        if (e1 > mx) mx = e1;
        if (e2 > mx) mx = e2;
        double aspect = mx / (mn > 1e-30 ? mn : 1e-30);
        if (aspect > aspect_max) {
            aspect_max = aspect;
        }
        aspect_sum += aspect;

        long u, v, tmp;
        u = ia; v = ib;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = ib; v = ic;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = ic; v = ia;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;
    }

    qsort(edges, (size_t)n_edges, sizeof(SurfaceEdge), _cmp_surface_edge);
    long n_unique = 0;
    long i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        ++n_unique;
        i = j;
    }

    counts_out[0] = n_unique;
    aspect_out[0] = aspect_max;
    aspect_out[1] = aspect_sum / (double)n_faces;
    free(edges);
}

/* -----------------------------------------------------------------------
 * surface_unique_edge_length_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [edge_min, edge_max, p01, p99].
 * count_out = [n_unique], or [-1] on allocation failure.
 * Matches feature_report.py unique-edge length statistics.
 * ----------------------------------------------------------------------- */
void surface_unique_edge_length_stats_batch(const double *verts, int n_verts,
                                            const long *faces, int n_faces,
                                            long *count_out,
                                            double *stats_out)
{
    (void)n_verts;
    count_out[0] = 0;
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    stats_out[3] = 0.0;
    if (n_faces <= 0) {
        return;
    }

    long n_edges = (long)n_faces * 3L;
    SurfaceEdge *edges = (SurfaceEdge *)malloc((size_t)n_edges * sizeof(SurfaceEdge));
    if (edges == NULL) {
        count_out[0] = -1;
        return;
    }

    long r = 0;
    for (int f = 0; f < n_faces; ++f) {
        long a = faces[(ptrdiff_t)f*3 + 0];
        long b = faces[(ptrdiff_t)f*3 + 1];
        long c = faces[(ptrdiff_t)f*3 + 2];
        long u, v, tmp;

        u = a; v = b;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = b; v = c;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;

        u = c; v = a;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; ++r;
    }

    qsort(edges, (size_t)n_edges, sizeof(SurfaceEdge), _cmp_surface_edge);

    long n_unique = 0;
    long i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        ++n_unique;
        i = j;
    }

    double *lengths = (double *)malloc((size_t)n_unique * sizeof(double));
    if (lengths == NULL) {
        free(edges);
        count_out[0] = -1;
        return;
    }

    long out = 0;
    i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        const double *A = _pt(verts, edges[i].u);
        const double *B = _pt(verts, edges[i].v);
        lengths[out] = sqrt(_dist2(A, B));
        ++out;
        i = j;
    }

    qsort(lengths, (size_t)n_unique, sizeof(double), _cmp_double_value);
    count_out[0] = n_unique;
    stats_out[0] = lengths[0];
    stats_out[1] = lengths[n_unique - 1];
    stats_out[2] = _percentile_sorted_linear(lengths, n_unique, 1.0);
    stats_out[3] = _percentile_sorted_linear(lengths, n_unique, 99.0);

    free(lengths);
    free(edges);
}

/* -----------------------------------------------------------------------
 * surface_vertex_gaussian_curvature_batch
 * -----------------------------------------------------------------------
 * Matches core.analyzer.curvature.vertex_gaussian_curvature.
 * stats_out = [min, max, mean, total].
 * ----------------------------------------------------------------------- */
void surface_vertex_gaussian_curvature_batch(const double *verts, int n_verts,
                                             const long *faces, int n_faces,
                                             double *k_out,
                                             double *stats_out)
{
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    stats_out[3] = 0.0;
    if (n_verts <= 0) {
        return;
    }
    for (int i = 0; i < n_verts; ++i) {
        k_out[i] = 0.0;
    }
    if (n_faces <= 0) {
        return;
    }

    double *angle_sum = (double *)calloc((size_t)n_verts, sizeof(double));
    double *area_sum = (double *)calloc((size_t)n_verts, sizeof(double));
    if (angle_sum == NULL || area_sum == NULL) {
        free(angle_sum);
        free(area_sum);
        return;
    }

    for (int f = 0; f < n_faces; ++f) {
        long ia = faces[(ptrdiff_t)f*3 + 0];
        long ib = faces[(ptrdiff_t)f*3 + 1];
        long ic = faces[(ptrdiff_t)f*3 + 2];
        const double *A = _pt(verts, ia);
        const double *B = _pt(verts, ib);
        const double *C = _pt(verts, ic);

        double ba[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ca[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double cr[3];
        _cross3(ba, ca, cr);
        double face_area = 0.5 * sqrt(_dot3(cr, cr));
        double third_area = face_area / 3.0;
        area_sum[ia] += third_area;
        area_sum[ib] += third_area;
        area_sum[ic] += third_area;

        const double *P[3] = {A, B, C};
        long ids[3] = {ia, ib, ic};
        int left[3] = {1, 0, 0};
        int right[3] = {2, 2, 1};
        for (int corner = 0; corner < 3; ++corner) {
            const double *PV = P[corner];
            const double *PL = P[left[corner]];
            const double *PR = P[right[corner]];
            double e1[3] = {PL[0]-PV[0], PL[1]-PV[1], PL[2]-PV[2]};
            double e2[3] = {PR[0]-PV[0], PR[1]-PV[1], PR[2]-PV[2]};
            double n1 = sqrt(_dot3(e1, e1));
            double n2 = sqrt(_dot3(e2, e2));
            if (n1 < 1e-30 || n2 < 1e-30) {
                continue;
            }
            double cos_t = _dot3(e1, e2) / (n1 * n2);
            if (cos_t > 1.0) cos_t = 1.0;
            if (cos_t < -1.0) cos_t = -1.0;
            angle_sum[ids[corner]] += acos(cos_t);
        }
    }

    const double two_pi = 6.28318530717958647692528676655900576;
    double min_k = 0.0;
    double max_k = 0.0;
    double sum_k = 0.0;
    double total = 0.0;
    for (int i = 0; i < n_verts; ++i) {
        double k = 0.0;
        if (area_sum[i] > 1e-30) {
            k = (two_pi - angle_sum[i]) / area_sum[i];
        }
        k_out[i] = k;
        if (i == 0 || k < min_k) min_k = k;
        if (i == 0 || k > max_k) max_k = k;
        sum_k += k;
        total += k * area_sum[i];
    }
    stats_out[0] = min_k;
    stats_out[1] = max_k;
    stats_out[2] = sum_k / (double)n_verts;
    stats_out[3] = total;

    free(angle_sum);
    free(area_sum);
}

static inline double _cot3(const double u[3], const double v[3])
{
    double cr[3];
    _cross3(u, v, cr);
    double den = sqrt(_dot3(cr, cr));
    return _dot3(u, v) / (den > 1e-30 ? den : 1e-30);
}

/* -----------------------------------------------------------------------
 * surface_vertex_mean_curvature_batch
 * -----------------------------------------------------------------------
 * Matches analyzer.mean_curvature.vertex_mean_curvature.
 * h_out has shape (n_verts, 3).
 * stats_out = [h_norm_min, h_norm_max, h_norm_mean, h_norm_p99].
 * stats_out[0] = -1 on allocation failure.
 * ----------------------------------------------------------------------- */
void surface_vertex_mean_curvature_batch(const double *verts, int n_verts,
                                         const long *faces, int n_faces,
                                         double *h_out,
                                         double *stats_out)
{
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    stats_out[3] = 0.0;
    if (n_verts <= 0) {
        return;
    }
    for (int i = 0; i < n_verts * 3; ++i) {
        h_out[i] = 0.0;
    }
    if (n_faces <= 0) {
        return;
    }

    double *area = (double *)calloc((size_t)n_verts, sizeof(double));
    double *norms = (double *)malloc((size_t)n_verts * sizeof(double));
    if (area == NULL || norms == NULL) {
        free(area);
        free(norms);
        stats_out[0] = -1.0;
        return;
    }

    for (int f = 0; f < n_faces; ++f) {
        long ia = faces[(ptrdiff_t)f*3 + 0];
        long ib = faces[(ptrdiff_t)f*3 + 1];
        long ic = faces[(ptrdiff_t)f*3 + 2];
        const double *A = _pt(verts, ia);
        const double *B = _pt(verts, ib);
        const double *C = _pt(verts, ic);

        double e_ab[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double e_ac[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double face_n[3];
        _cross3(e_ab, e_ac, face_n);
        double face_area = 0.5 * sqrt(_dot3(face_n, face_n));
        if (face_area < 1e-30) {
            continue;
        }

        double e_bc[3] = {C[0]-B[0], C[1]-B[1], C[2]-B[2]};
        double e_ba[3] = {-e_ab[0], -e_ab[1], -e_ab[2]};
        double e_cb[3] = {-e_bc[0], -e_bc[1], -e_bc[2]};
        double e_ca[3] = {-e_ac[0], -e_ac[1], -e_ac[2]};

        double cot_a = _cot3(e_ab, e_ac);
        double cot_b = _cot3(e_ba, e_bc);
        double cot_c = _cot3(e_ca, e_cb);

        double *HA = h_out + (ptrdiff_t)ia * 3;
        double *HB = h_out + (ptrdiff_t)ib * 3;
        double *HC = h_out + (ptrdiff_t)ic * 3;

        /* H[a] += cot_c * (pb-pa) + cot_b * (pc-pa) */
        HA[0] += cot_c * e_ab[0] + cot_b * e_ac[0];
        HA[1] += cot_c * e_ab[1] + cot_b * e_ac[1];
        HA[2] += cot_c * e_ab[2] + cot_b * e_ac[2];

        /* H[b] += cot_c * (pa-pb) + cot_a * (pc-pb) */
        HB[0] += cot_c * e_ba[0] + cot_a * e_bc[0];
        HB[1] += cot_c * e_ba[1] + cot_a * e_bc[1];
        HB[2] += cot_c * e_ba[2] + cot_a * e_bc[2];

        /* H[c] += cot_b * (pa-pc) + cot_a * (pb-pc) */
        HC[0] += cot_b * e_ca[0] + cot_a * e_cb[0];
        HC[1] += cot_b * e_ca[1] + cot_a * e_cb[1];
        HC[2] += cot_b * e_ca[2] + cot_a * e_cb[2];

        double third_area = face_area / 3.0;
        area[ia] += third_area;
        area[ib] += third_area;
        area[ic] += third_area;
    }

    double min_norm = 0.0;
    double max_norm = 0.0;
    double sum_norm = 0.0;
    for (int i = 0; i < n_verts; ++i) {
        double *H = h_out + (ptrdiff_t)i * 3;
        if (area[i] > 1e-30) {
            double inv = 1.0 / (2.0 * area[i]);
            H[0] *= inv;
            H[1] *= inv;
            H[2] *= inv;
        } else {
            H[0] = 0.0;
            H[1] = 0.0;
            H[2] = 0.0;
        }
        double nrm = sqrt(H[0]*H[0] + H[1]*H[1] + H[2]*H[2]);
        norms[i] = nrm;
        if (i == 0 || nrm < min_norm) min_norm = nrm;
        if (i == 0 || nrm > max_norm) max_norm = nrm;
        sum_norm += nrm;
    }

    qsort(norms, (size_t)n_verts, sizeof(double), _cmp_double_value);
    stats_out[0] = min_norm;
    stats_out[1] = max_norm;
    stats_out[2] = sum_norm / (double)n_verts;
    stats_out[3] = _percentile_sorted_linear(norms, (long)n_verts, 99.0);

    free(area);
    free(norms);
}

typedef struct {
    long u;
    long v;
    long face;
} SurfaceEdgeFace;

static int _cmp_surface_edge_face(const void *pa, const void *pb)
{
    const SurfaceEdgeFace *a = (const SurfaceEdgeFace *)pa;
    const SurfaceEdgeFace *b = (const SurfaceEdgeFace *)pb;
    if (a->u < b->u) return -1;
    if (a->u > b->u) return 1;
    if (a->v < b->v) return -1;
    if (a->v > b->v) return 1;
    return 0;
}

/* -----------------------------------------------------------------------
 * surface_feature_edges_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [n_feature, n_boundary, n_sharp, n_corner_vertices].
 * stats_out[0] = -1 on allocation failure.
 * ----------------------------------------------------------------------- */
void surface_feature_edges_stats_batch(const double *verts, int n_verts,
                                       const long *faces, int n_faces,
                                       double cos_threshold,
                                       long *stats_out)
{
    stats_out[0] = 0;
    stats_out[1] = 0;
    stats_out[2] = 0;
    stats_out[3] = 0;
    if (n_faces <= 0 || n_verts <= 0) {
        return;
    }

    long n_edges = (long)n_faces * 3L;
    SurfaceEdgeFace *edges = (SurfaceEdgeFace *)malloc((size_t)n_edges * sizeof(SurfaceEdgeFace));
    double *normals = (double *)malloc((size_t)n_faces * 3U * sizeof(double));
    long *feature_count = (long *)calloc((size_t)n_verts, sizeof(long));
    if (edges == NULL || normals == NULL || feature_count == NULL) {
        free(edges);
        free(normals);
        free(feature_count);
        stats_out[0] = -1;
        return;
    }

    long r = 0;
    for (int f = 0; f < n_faces; ++f) {
        long ia = faces[(ptrdiff_t)f*3 + 0];
        long ib = faces[(ptrdiff_t)f*3 + 1];
        long ic = faces[(ptrdiff_t)f*3 + 2];
        const double *A = _pt(verts, ia);
        const double *B = _pt(verts, ib);
        const double *C = _pt(verts, ic);
        double e1[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double e2[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double n[3];
        _cross3(e1, e2, n);
        double nrm = sqrt(_dot3(n, n));
        if (nrm < 1e-30) {
            nrm = 1e-30;
        }
        normals[(ptrdiff_t)f*3 + 0] = n[0] / nrm;
        normals[(ptrdiff_t)f*3 + 1] = n[1] / nrm;
        normals[(ptrdiff_t)f*3 + 2] = n[2] / nrm;

        long u, v, tmp;
        u = ia; v = ib;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;

        u = ib; v = ic;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;

        u = ic; v = ia;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;
    }

    qsort(edges, (size_t)n_edges, sizeof(SurfaceEdgeFace), _cmp_surface_edge_face);

    long n_bnd = 0;
    long n_sharp = 0;
    long i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        long cnt = j - i;
        int is_feature = 0;
        if (cnt == 1) {
            ++n_bnd;
            is_feature = 1;
        } else if (cnt == 2) {
            long f0 = edges[i].face;
            long f1 = edges[i + 1].face;
            const double *n0 = normals + (ptrdiff_t)f0 * 3;
            const double *n1 = normals + (ptrdiff_t)f1 * 3;
            double cos_a = _dot3(n0, n1);
            if (cos_a > 1.0) cos_a = 1.0;
            if (cos_a < -1.0) cos_a = -1.0;
            if (cos_a < cos_threshold) {
                ++n_sharp;
                is_feature = 1;
            }
        }
        if (is_feature) {
            if (edges[i].u >= 0 && edges[i].u < n_verts) {
                feature_count[edges[i].u] += 1;
            }
            if (edges[i].v >= 0 && edges[i].v < n_verts) {
                feature_count[edges[i].v] += 1;
            }
        }
        i = j;
    }

    long n_corners = 0;
    for (int v = 0; v < n_verts; ++v) {
        if (feature_count[v] >= 3) {
            ++n_corners;
        }
    }
    stats_out[0] = n_bnd + n_sharp;
    stats_out[1] = n_bnd;
    stats_out[2] = n_sharp;
    stats_out[3] = n_corners;

    free(edges);
    free(normals);
    free(feature_count);
}

/* -----------------------------------------------------------------------
 * surface_feature_report_stats_batch
 * -----------------------------------------------------------------------
 * count_out = [n_unique, n_feature, n_boundary, n_sharp, n_corner_vertices].
 * count_out[0] = -1 on allocation failure.
 * length_stats_out = [edge_min, edge_max, p01, p99].
 * This fuses feature_report.py's unique edge lengths and feature-edge stats
 * into one edge sort.
 * ----------------------------------------------------------------------- */
void surface_feature_report_stats_batch(const double *verts, int n_verts,
                                        const long *faces, int n_faces,
                                        double cos_threshold,
                                        long *count_out,
                                        double *length_stats_out)
{
    count_out[0] = 0;
    count_out[1] = 0;
    count_out[2] = 0;
    count_out[3] = 0;
    count_out[4] = 0;
    length_stats_out[0] = 0.0;
    length_stats_out[1] = 0.0;
    length_stats_out[2] = 0.0;
    length_stats_out[3] = 0.0;
    if (n_faces <= 0 || n_verts <= 0) {
        return;
    }

    long n_edges = (long)n_faces * 3L;
    SurfaceEdgeFace *edges = (SurfaceEdgeFace *)malloc((size_t)n_edges * sizeof(SurfaceEdgeFace));
    double *normals = (double *)malloc((size_t)n_faces * 3U * sizeof(double));
    long *feature_count = (long *)calloc((size_t)n_verts, sizeof(long));
    if (edges == NULL || normals == NULL || feature_count == NULL) {
        free(edges);
        free(normals);
        free(feature_count);
        count_out[0] = -1;
        return;
    }

    long r = 0;
    for (int f = 0; f < n_faces; ++f) {
        long ia = faces[(ptrdiff_t)f*3 + 0];
        long ib = faces[(ptrdiff_t)f*3 + 1];
        long ic = faces[(ptrdiff_t)f*3 + 2];
        const double *A = _pt(verts, ia);
        const double *B = _pt(verts, ib);
        const double *C = _pt(verts, ic);
        double e1[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double e2[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double n[3];
        _cross3(e1, e2, n);
        double nrm = sqrt(_dot3(n, n));
        if (nrm < 1e-30) {
            nrm = 1e-30;
        }
        normals[(ptrdiff_t)f*3 + 0] = n[0] / nrm;
        normals[(ptrdiff_t)f*3 + 1] = n[1] / nrm;
        normals[(ptrdiff_t)f*3 + 2] = n[2] / nrm;

        long u, v, tmp;
        u = ia; v = ib;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;

        u = ib; v = ic;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;

        u = ic; v = ia;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;
    }

    qsort(edges, (size_t)n_edges, sizeof(SurfaceEdgeFace), _cmp_surface_edge_face);

    long n_unique = 0;
    long i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        ++n_unique;
        i = j;
    }

    double *lengths = (double *)malloc((size_t)n_unique * sizeof(double));
    if (lengths == NULL) {
        free(edges);
        free(normals);
        free(feature_count);
        count_out[0] = -1;
        return;
    }

    long n_bnd = 0;
    long n_sharp = 0;
    long out = 0;
    i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        long cnt = j - i;
        int is_feature = 0;

        const double *A = _pt(verts, edges[i].u);
        const double *B = _pt(verts, edges[i].v);
        lengths[out] = sqrt(_dist2(A, B));
        ++out;

        if (cnt == 1) {
            ++n_bnd;
            is_feature = 1;
        } else if (cnt == 2) {
            long f0 = edges[i].face;
            long f1 = edges[i + 1].face;
            const double *n0 = normals + (ptrdiff_t)f0 * 3;
            const double *n1 = normals + (ptrdiff_t)f1 * 3;
            double cos_a = _dot3(n0, n1);
            if (cos_a > 1.0) cos_a = 1.0;
            if (cos_a < -1.0) cos_a = -1.0;
            if (cos_a < cos_threshold) {
                ++n_sharp;
                is_feature = 1;
            }
        }
        if (is_feature) {
            if (edges[i].u >= 0 && edges[i].u < n_verts) {
                feature_count[edges[i].u] += 1;
            }
            if (edges[i].v >= 0 && edges[i].v < n_verts) {
                feature_count[edges[i].v] += 1;
            }
        }
        i = j;
    }

    long n_corners = 0;
    for (int v = 0; v < n_verts; ++v) {
        if (feature_count[v] >= 3) {
            ++n_corners;
        }
    }

    qsort(lengths, (size_t)n_unique, sizeof(double), _cmp_double_value);
    count_out[0] = n_unique;
    count_out[1] = n_bnd + n_sharp;
    count_out[2] = n_bnd;
    count_out[3] = n_sharp;
    count_out[4] = n_corners;
    length_stats_out[0] = lengths[0];
    length_stats_out[1] = lengths[n_unique - 1];
    length_stats_out[2] = _percentile_sorted_linear(lengths, n_unique, 1.0);
    length_stats_out[3] = _percentile_sorted_linear(lengths, n_unique, 99.0);

    free(lengths);
    free(edges);
    free(normals);
    free(feature_count);
}

/* -----------------------------------------------------------------------
 * surface_diag_stats_batch
 * -----------------------------------------------------------------------
 * counts_out = [n_inconsistent, n_sliver, n_sharp, n_dihedral_pairs].
 * counts_out[0] = -1 on allocation failure.
 * stats_out = [dihedral_min_deg, dihedral_max_deg, dihedral_mean_deg,
 *              face_area_min, face_area_max, aspect_ratio_max].
 * Matches analyzer.surface_diag.diagnose_surface aggregate behavior.
 * ----------------------------------------------------------------------- */
void surface_diag_stats_batch(const double *verts, int n_verts,
                              const long *faces, int n_faces,
                              double cos_threshold,
                              double sliver_area_tol,
                              long *counts_out,
                              double *stats_out)
{
    (void)n_verts;
    counts_out[0] = 0;
    counts_out[1] = 0;
    counts_out[2] = 0;
    counts_out[3] = 0;
    for (int k = 0; k < 6; ++k) {
        stats_out[k] = 0.0;
    }
    if (n_faces <= 0) {
        return;
    }

    long n_edges = (long)n_faces * 3L;
    SurfaceEdgeFace *edges = (SurfaceEdgeFace *)malloc((size_t)n_edges * sizeof(SurfaceEdgeFace));
    double *normals = (double *)malloc((size_t)n_faces * 3U * sizeof(double));
    if (edges == NULL || normals == NULL) {
        free(edges);
        free(normals);
        counts_out[0] = -1;
        return;
    }

    double face_area_min = 0.0;
    double face_area_max = 0.0;
    double aspect_max = 0.0;
    long n_sliver = 0;
    long r = 0;
    for (int f = 0; f < n_faces; ++f) {
        long ia = faces[(ptrdiff_t)f*3 + 0];
        long ib = faces[(ptrdiff_t)f*3 + 1];
        long ic = faces[(ptrdiff_t)f*3 + 2];
        const double *A = _pt(verts, ia);
        const double *B = _pt(verts, ib);
        const double *C = _pt(verts, ic);
        double e1[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double e2[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double e3[3] = {C[0]-B[0], C[1]-B[1], C[2]-B[2]};
        double n[3];
        _cross3(e1, e2, n);
        double n_len = sqrt(_dot3(n, n));
        double area = 0.5 * n_len;
        if (f == 0 || area < face_area_min) face_area_min = area;
        if (f == 0 || area > face_area_max) face_area_max = area;
        if (area < sliver_area_tol) {
            ++n_sliver;
        }

        double edge_a = sqrt(_dot3(e1, e1));
        double edge_b = sqrt(_dot3(e2, e2));
        double edge_c = sqrt(_dot3(e3, e3));
        double e_min = edge_a;
        if (edge_b < e_min) e_min = edge_b;
        if (edge_c < e_min) e_min = edge_c;
        double e_max = edge_a;
        if (edge_b > e_max) e_max = edge_b;
        if (edge_c > e_max) e_max = edge_c;
        double aspect = e_max / (e_min > 1e-30 ? e_min : 1e-30);
        if (aspect > aspect_max) aspect_max = aspect;

        if (n_len > 1e-30) {
            normals[(ptrdiff_t)f*3 + 0] = n[0] / n_len;
            normals[(ptrdiff_t)f*3 + 1] = n[1] / n_len;
            normals[(ptrdiff_t)f*3 + 2] = n[2] / n_len;
        } else {
            normals[(ptrdiff_t)f*3 + 0] = 0.0;
            normals[(ptrdiff_t)f*3 + 1] = 0.0;
            normals[(ptrdiff_t)f*3 + 2] = 0.0;
        }

        long u, v, tmp;
        u = ia; v = ib;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;

        u = ib; v = ic;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;

        u = ic; v = ia;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;
    }

    qsort(edges, (size_t)n_edges, sizeof(SurfaceEdgeFace), _cmp_surface_edge_face);

    long n_inconsistent = 0;
    long n_sharp = 0;
    long n_pairs = 0;
    double dihedral_min = 0.0;
    double dihedral_max = 0.0;
    double dihedral_sum = 0.0;
    long i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        if (j - i == 2) {
            long f0 = edges[i].face;
            long f1 = edges[i + 1].face;
            const double *n0 = normals + (ptrdiff_t)f0 * 3;
            const double *n1 = normals + (ptrdiff_t)f1 * 3;
            double cos_a = _dot3(n0, n1);
            if (cos_a > 1.0) cos_a = 1.0;
            if (cos_a < -1.0) cos_a = -1.0;
            double deg = acos(cos_a) * 57.295779513082320876798154814105;
            if (n_pairs == 0 || deg < dihedral_min) dihedral_min = deg;
            if (n_pairs == 0 || deg > dihedral_max) dihedral_max = deg;
            dihedral_sum += deg;
            ++n_pairs;
            if (cos_a < -0.9) {
                ++n_inconsistent;
            }
            if (cos_a < cos_threshold) {
                ++n_sharp;
            }
        }
        i = j;
    }

    counts_out[0] = n_inconsistent;
    counts_out[1] = n_sliver;
    counts_out[2] = n_sharp;
    counts_out[3] = n_pairs;
    stats_out[0] = n_pairs > 0 ? dihedral_min : 0.0;
    stats_out[1] = n_pairs > 0 ? dihedral_max : 0.0;
    stats_out[2] = n_pairs > 0 ? dihedral_sum / (double)n_pairs : 0.0;
    stats_out[3] = face_area_min;
    stats_out[4] = face_area_max;
    stats_out[5] = aspect_max;

    free(edges);
    free(normals);
}

/* -----------------------------------------------------------------------
 * surface_dihedral_histogram_batch
 * -----------------------------------------------------------------------
 * hist_out has shape (n_bin_edges - 1).
 * meta_out = [n_internal_edges], or [-1] on allocation failure.
 * stats_out = [angle_min_deg, angle_max_deg, angle_mean_deg].
 * ----------------------------------------------------------------------- */
void surface_dihedral_histogram_batch(const double *verts, int n_verts,
                                      const long *faces, int n_faces,
                                      const double *bin_edges, int n_bin_edges,
                                      long *hist_out,
                                      long *meta_out,
                                      double *stats_out)
{
    (void)n_verts;
    meta_out[0] = 0;
    stats_out[0] = 180.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    int n_bins = n_bin_edges - 1;
    for (int b = 0; b < n_bins; ++b) {
        hist_out[b] = 0;
    }
    if (n_faces <= 0 || n_bins <= 0) {
        return;
    }

    long n_edges = (long)n_faces * 3L;
    SurfaceEdgeFace *edges = (SurfaceEdgeFace *)malloc((size_t)n_edges * sizeof(SurfaceEdgeFace));
    double *normals = (double *)malloc((size_t)n_faces * 3U * sizeof(double));
    if (edges == NULL || normals == NULL) {
        free(edges);
        free(normals);
        meta_out[0] = -1;
        return;
    }

    long r = 0;
    for (int f = 0; f < n_faces; ++f) {
        long ia = faces[(ptrdiff_t)f*3 + 0];
        long ib = faces[(ptrdiff_t)f*3 + 1];
        long ic = faces[(ptrdiff_t)f*3 + 2];
        const double *A = _pt(verts, ia);
        const double *B = _pt(verts, ib);
        const double *C = _pt(verts, ic);
        double e1[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double e2[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double n[3];
        _cross3(e1, e2, n);
        double n_len = sqrt(_dot3(n, n));
        if (n_len > 1e-30) {
            normals[(ptrdiff_t)f*3 + 0] = n[0] / n_len;
            normals[(ptrdiff_t)f*3 + 1] = n[1] / n_len;
            normals[(ptrdiff_t)f*3 + 2] = n[2] / n_len;
        } else {
            normals[(ptrdiff_t)f*3 + 0] = 0.0;
            normals[(ptrdiff_t)f*3 + 1] = 0.0;
            normals[(ptrdiff_t)f*3 + 2] = 0.0;
        }

        long u, v, tmp;
        u = ia; v = ib;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;

        u = ib; v = ic;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;

        u = ic; v = ia;
        if (v < u) { tmp = u; u = v; v = tmp; }
        edges[r].u = u; edges[r].v = v; edges[r].face = (long)f; ++r;
    }

    qsort(edges, (size_t)n_edges, sizeof(SurfaceEdgeFace), _cmp_surface_edge_face);

    long n_internal = 0;
    double angle_min = 180.0;
    double angle_max = 0.0;
    double angle_sum = 0.0;
    long i = 0;
    while (i < n_edges) {
        long j = i + 1;
        while (j < n_edges && edges[j].u == edges[i].u && edges[j].v == edges[i].v) {
            ++j;
        }
        if (j - i == 2) {
            long f0 = edges[i].face;
            long f1 = edges[i + 1].face;
            const double *n0 = normals + (ptrdiff_t)f0 * 3;
            const double *n1 = normals + (ptrdiff_t)f1 * 3;
            double cos_a = _dot3(n0, n1);
            if (cos_a > 1.0) cos_a = 1.0;
            if (cos_a < -1.0) cos_a = -1.0;
            double angle = acos(cos_a) * 57.295779513082320876798154814105;
            if (n_internal == 0 || angle < angle_min) angle_min = angle;
            if (n_internal == 0 || angle > angle_max) angle_max = angle;
            angle_sum += angle;
            ++n_internal;

            for (int b = 0; b < n_bins; ++b) {
                int in_bin = 0;
                if (b == n_bins - 1) {
                    in_bin = (angle >= bin_edges[b] && angle <= bin_edges[b + 1]);
                } else {
                    in_bin = (angle >= bin_edges[b] && angle < bin_edges[b + 1]);
                }
                if (in_bin) {
                    hist_out[b] += 1;
                    break;
                }
            }
        }
        i = j;
    }

    meta_out[0] = n_internal;
    if (n_internal > 0) {
        stats_out[0] = angle_min;
        stats_out[1] = angle_max;
        stats_out[2] = angle_sum / (double)n_internal;
    }

    free(edges);
    free(normals);
}

/* -----------------------------------------------------------------------
 * surface_remove_degenerate_faces_mask
 * -----------------------------------------------------------------------
 * keep_out has shape (n_faces,), values 0/1.
 * counts_out = [n_removed], or [-1] on allocation failure.
 * Matches native_repair.degenerate.remove_degenerate_faces:
 * keep area >= area_tol and the first original occurrence per sorted face.
 * ----------------------------------------------------------------------- */
void surface_remove_degenerate_faces_mask(const double *verts, int n_verts,
                                          const long *faces, int n_faces,
                                          double area_tol,
                                          long *keep_out,
                                          long *counts_out)
{
    (void)n_verts;
    counts_out[0] = 0;
    if (n_faces <= 0) {
        return;
    }

    SurfaceFaceKey *keys = (SurfaceFaceKey *)malloc((size_t)n_faces * sizeof(SurfaceFaceKey));
    if (keys == NULL) {
        counts_out[0] = -1;
        return;
    }

    for (int f = 0; f < n_faces; ++f) {
        long ia = faces[(ptrdiff_t)f*3 + 0];
        long ib = faces[(ptrdiff_t)f*3 + 1];
        long ic = faces[(ptrdiff_t)f*3 + 2];
        const double *A = _pt(verts, ia);
        const double *B = _pt(verts, ib);
        const double *C = _pt(verts, ic);
        double ba[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ca[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double cr[3];
        _cross3(ba, ca, cr);
        double area = 0.5 * sqrt(_dot3(cr, cr));
        keep_out[f] = (area >= area_tol) ? 1 : 0;

        long a = ia;
        long b = ib;
        long c = ic;
        _sort3_long(&a, &b, &c);
        keys[f].a = a;
        keys[f].b = b;
        keys[f].c = c;
        keys[f].index = (long)f;
    }

    qsort(keys, (size_t)n_faces, sizeof(SurfaceFaceKey), _cmp_surface_face_key);

    long i = 0;
    while (i < n_faces) {
        long j = i + 1;
        while (j < n_faces &&
               keys[j].a == keys[i].a &&
               keys[j].b == keys[i].b &&
               keys[j].c == keys[i].c) {
            ++j;
        }
        for (long k = i + 1; k < j; ++k) {
            keep_out[keys[k].index] = 0;
        }
        i = j;
    }

    long n_keep = 0;
    for (int f = 0; f < n_faces; ++f) {
        if (keep_out[f]) {
            ++n_keep;
        }
    }
    counts_out[0] = (long)n_faces - n_keep;
    free(keys);
}

/* -----------------------------------------------------------------------
 * surface_dedup_vertices_quantized
 * -----------------------------------------------------------------------
 * new_verts_out capacity is n_verts*3; new_faces_out capacity is n_faces*3.
 * counts_out = [n_unique, n_merged], or [-1, 0] on allocation failure.
 * Matches native_repair.dedup.dedup_vertices for non-halfway quantization:
 * keys = round(V / tol), np.unique(axis=0, return_index/inverse).
 * ----------------------------------------------------------------------- */
void surface_dedup_vertices_quantized(const double *verts, int n_verts,
                                      const long *faces, int n_faces,
                                      double tol,
                                      double *new_verts_out,
                                      long *new_faces_out,
                                      long *counts_out)
{
    counts_out[0] = 0;
    counts_out[1] = 0;
    if (n_verts <= 0) {
        return;
    }

    QuantVertexKey *keys = (QuantVertexKey *)malloc((size_t)n_verts * sizeof(QuantVertexKey));
    long *inverse = (long *)malloc((size_t)n_verts * sizeof(long));
    if (keys == NULL || inverse == NULL) {
        free(keys);
        free(inverse);
        counts_out[0] = -1;
        return;
    }

    double safe_tol = tol > 1e-30 ? tol : 1e-30;
    double scale = 1.0 / safe_tol;
    for (int i = 0; i < n_verts; ++i) {
        const double *P = _pt(verts, (long)i);
        keys[i].x = (long)llrint(P[0] * scale);
        keys[i].y = (long)llrint(P[1] * scale);
        keys[i].z = (long)llrint(P[2] * scale);
        keys[i].index = (long)i;
    }

    qsort(keys, (size_t)n_verts, sizeof(QuantVertexKey), _cmp_quant_vertex_key);

    long n_unique = 0;
    long i = 0;
    while (i < n_verts) {
        long j = i + 1;
        while (j < n_verts &&
               keys[j].x == keys[i].x &&
               keys[j].y == keys[i].y &&
               keys[j].z == keys[i].z) {
            ++j;
        }

        long src = keys[i].index;
        const double *P = _pt(verts, src);
        new_verts_out[n_unique*3 + 0] = P[0];
        new_verts_out[n_unique*3 + 1] = P[1];
        new_verts_out[n_unique*3 + 2] = P[2];
        for (long k = i; k < j; ++k) {
            inverse[keys[k].index] = n_unique;
        }
        ++n_unique;
        i = j;
    }

    for (int f = 0; f < n_faces; ++f) {
        long ia = faces[(ptrdiff_t)f*3 + 0];
        long ib = faces[(ptrdiff_t)f*3 + 1];
        long ic = faces[(ptrdiff_t)f*3 + 2];
        new_faces_out[(ptrdiff_t)f*3 + 0] = inverse[ia];
        new_faces_out[(ptrdiff_t)f*3 + 1] = inverse[ib];
        new_faces_out[(ptrdiff_t)f*3 + 2] = inverse[ic];
    }

    counts_out[0] = n_unique;
    counts_out[1] = (long)n_verts - n_unique;
    free(keys);
    free(inverse);
}

/* -----------------------------------------------------------------------
 * surface_area_volume_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [surface_area, signed_volume, bbox_volume].
 * Matches analyzer.surface_volume.surface_volume_integral aggregate math.
 * ----------------------------------------------------------------------- */
void surface_area_volume_stats_batch(const double *verts, int n_verts,
                                     const long *faces, int n_faces,
                                     double *stats_out)
{
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    if (n_verts <= 0 || n_faces <= 0) {
        return;
    }

    double min_x = verts[0], min_y = verts[1], min_z = verts[2];
    double max_x = verts[0], max_y = verts[1], max_z = verts[2];
    for (int i = 1; i < n_verts; ++i) {
        const double *P = _pt(verts, (long)i);
        if (P[0] < min_x) min_x = P[0];
        if (P[1] < min_y) min_y = P[1];
        if (P[2] < min_z) min_z = P[2];
        if (P[0] > max_x) max_x = P[0];
        if (P[1] > max_y) max_y = P[1];
        if (P[2] > max_z) max_z = P[2];
    }

    double area = 0.0;
    double vol = 0.0;
    for (int f = 0; f < n_faces; ++f) {
        const double *A = _pt(verts, faces[(ptrdiff_t)f*3 + 0]);
        const double *B = _pt(verts, faces[(ptrdiff_t)f*3 + 1]);
        const double *C = _pt(verts, faces[(ptrdiff_t)f*3 + 2]);

        double ba[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ca[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double area_cross[3];
        _cross3(ba, ca, area_cross);
        area += 0.5 * sqrt(_dot3(area_cross, area_cross));

        double bc_cross[3];
        _cross3(B, C, bc_cross);
        vol += _dot3(A, bc_cross) / 6.0;
    }

    double dx = max_x - min_x;
    double dy = max_y - min_y;
    double dz = max_z - min_z;
    if (dx < 0.0) dx = 0.0;
    if (dy < 0.0) dy = 0.0;
    if (dz < 0.0) dz = 0.0;
    stats_out[0] = area;
    stats_out[1] = vol;
    stats_out[2] = dx * dy * dz;
}

/* -----------------------------------------------------------------------
 * surface_face_area_distribution_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [min, max, mean, std, p01, p99], or [-1, ...] on alloc fail.
 * ----------------------------------------------------------------------- */
void surface_face_area_distribution_stats_batch(const double *verts, int n_verts,
                                                const long *faces, int n_faces,
                                                double *stats_out)
{
    (void)n_verts;
    for (int i = 0; i < 6; ++i) {
        stats_out[i] = 0.0;
    }
    if (n_faces <= 0) {
        return;
    }

    double *areas = (double *)malloc((size_t)n_faces * sizeof(double));
    if (areas == NULL) {
        stats_out[0] = -1.0;
        return;
    }

    double min_area = 0.0;
    double max_area = 0.0;
    double sum = 0.0;
    double sum_sq = 0.0;
    for (int f = 0; f < n_faces; ++f) {
        const double *A = _pt(verts, faces[(ptrdiff_t)f*3 + 0]);
        const double *B = _pt(verts, faces[(ptrdiff_t)f*3 + 1]);
        const double *C = _pt(verts, faces[(ptrdiff_t)f*3 + 2]);
        double ba[3] = {B[0]-A[0], B[1]-A[1], B[2]-A[2]};
        double ca[3] = {C[0]-A[0], C[1]-A[1], C[2]-A[2]};
        double cr[3];
        _cross3(ba, ca, cr);
        double area = 0.5 * sqrt(_dot3(cr, cr));
        areas[f] = area;
        if (f == 0 || area < min_area) min_area = area;
        if (f == 0 || area > max_area) max_area = area;
        sum += area;
        sum_sq += area * area;
    }

    double mean = sum / (double)n_faces;
    double var = sum_sq / (double)n_faces - mean * mean;
    if (var < 0.0 && var > -1e-24) {
        var = 0.0;
    }
    qsort(areas, (size_t)n_faces, sizeof(double), _cmp_double_value);

    stats_out[0] = min_area;
    stats_out[1] = max_area;
    stats_out[2] = mean;
    stats_out[3] = sqrt(var > 0.0 ? var : 0.0);
    stats_out[4] = _percentile_sorted_linear(areas, (long)n_faces, 1.0);
    stats_out[5] = _percentile_sorted_linear(areas, (long)n_faces, 99.0);

    free(areas);
}
