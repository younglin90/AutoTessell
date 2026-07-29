/* Hex, BL, snap, and polyhedral ctypes fallback kernels.
 * Included from tet_kernels.c after shared math/topology helpers.
 */

/* -----------------------------------------------------------------------
 * hex_stretch_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [stretch_min, stretch_max, stretch_mean].
 * counts_out = [n_below_0p1].
 * ----------------------------------------------------------------------- */
void hex_stretch_stats_batch(const double *pts, int n_pts,
                             const long *hexes, int n_hexes,
                             double *stats_out,
                             long *counts_out)
{
    (void)n_pts;
    stats_out[0] = 0.0;
    stats_out[1] = 1.0;
    stats_out[2] = 0.0;
    counts_out[0] = 0;
    if (n_hexes <= 0) {
        return;
    }

    static const int edges[12][2] = {
        {0, 1}, {1, 2}, {2, 3}, {3, 0},
        {4, 5}, {5, 6}, {6, 7}, {7, 4},
        {0, 4}, {1, 5}, {2, 6}, {3, 7},
    };
    double stretch_min = 0.0;
    double stretch_max = 0.0;
    double stretch_sum = 0.0;
    long n_below = 0;

    for (int h = 0; h < n_hexes; ++h) {
        double e_min = 0.0;
        double e_max = 0.0;
        for (int k = 0; k < 12; ++k) {
            long ia = hexes[(ptrdiff_t)h*8 + edges[k][0]];
            long ib = hexes[(ptrdiff_t)h*8 + edges[k][1]];
            double len = sqrt(_dist2(_pt(pts, ia), _pt(pts, ib)));
            if (k == 0 || len < e_min) e_min = len;
            if (k == 0 || len > e_max) e_max = len;
        }
        double stretch = 0.0;
        if (e_max > 1e-30) {
            stretch = e_min / e_max;
        }
        if (h == 0 || stretch < stretch_min) stretch_min = stretch;
        if (h == 0 || stretch > stretch_max) stretch_max = stretch;
        stretch_sum += stretch;
        if (stretch < 0.1) ++n_below;
    }

    stats_out[0] = stretch_min;
    stats_out[1] = stretch_max;
    stats_out[2] = stretch_sum / (double)n_hexes;
    counts_out[0] = n_below;
}

/* -----------------------------------------------------------------------
 * hex_face_area_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [area_min, area_max, area_mean, ratio_max, ratio_mean].
 * counts_out = [n_stretched].
 * ----------------------------------------------------------------------- */
void hex_face_area_stats_batch(const double *pts, int n_pts,
                               const long *hexes, int n_hexes,
                               double *stats_out,
                               long *counts_out)
{
    (void)n_pts;
    for (int i = 0; i < 5; ++i) {
        stats_out[i] = 0.0;
    }
    counts_out[0] = 0;
    if (n_hexes <= 0) {
        return;
    }

    static const int faces[6][4] = {
        {0, 3, 2, 1},
        {4, 5, 6, 7},
        {0, 1, 5, 4},
        {2, 3, 7, 6},
        {0, 4, 7, 3},
        {1, 2, 6, 5},
    };
    double area_min_all = 0.0;
    double area_max_all = 0.0;
    double area_sum = 0.0;
    double ratio_max_all = 0.0;
    double ratio_sum = 0.0;
    long n_stretched = 0;
    long n_faces_total = 0;

    for (int h = 0; h < n_hexes; ++h) {
        double face_min = 0.0;
        double face_max = 0.0;
        for (int f = 0; f < 6; ++f) {
            const double *P0 = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][0]]);
            const double *P1 = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][1]]);
            const double *P2 = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][2]]);
            const double *P3 = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][3]]);
            double area = _tri_area3(P0, P1, P2) + _tri_area3(P0, P2, P3);
            if (n_faces_total == 0 || area < area_min_all) area_min_all = area;
            if (n_faces_total == 0 || area > area_max_all) area_max_all = area;
            if (f == 0 || area < face_min) face_min = area;
            if (f == 0 || area > face_max) face_max = area;
            area_sum += area;
            ++n_faces_total;
        }
        double ratio = 0.0;
        if (face_min > 1e-30) {
            ratio = face_max / face_min;
        }
        if (h == 0 || ratio > ratio_max_all) ratio_max_all = ratio;
        ratio_sum += ratio;
        if (ratio > 5.0) ++n_stretched;
    }

    stats_out[0] = area_min_all;
    stats_out[1] = area_max_all;
    stats_out[2] = area_sum / (double)n_faces_total;
    stats_out[3] = ratio_max_all;
    stats_out[4] = ratio_sum / (double)n_hexes;
    counts_out[0] = n_stretched;
}

/* -----------------------------------------------------------------------
 * bl_prism_quality_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [aspect_min, aspect_max, aspect_mean,
 *              thickness_uniformity_mean, skew_max, skew_mean].
 * counts_out = [n_inverted].
 * ----------------------------------------------------------------------- */
void bl_prism_quality_stats_batch(const double *pts, int n_pts,
                                  const long *prisms, int n_prisms,
                                  double *stats_out,
                                  long *counts_out)
{
    (void)n_pts;
    for (int i = 0; i < 6; ++i) {
        stats_out[i] = 0.0;
    }
    counts_out[0] = 0;
    if (n_prisms <= 0) {
        return;
    }

    double aspect_min = 0.0;
    double aspect_max = 0.0;
    double aspect_sum = 0.0;
    double uniformity_sum = 0.0;
    double skew_max = 0.0;
    double skew_sum = 0.0;
    long n_inv = 0;

    for (int p = 0; p < n_prisms; ++p) {
        const double *P0 = _pt(pts, prisms[(ptrdiff_t)p*6 + 0]);
        const double *P1 = _pt(pts, prisms[(ptrdiff_t)p*6 + 1]);
        const double *P2 = _pt(pts, prisms[(ptrdiff_t)p*6 + 2]);
        const double *P3 = _pt(pts, prisms[(ptrdiff_t)p*6 + 3]);
        const double *P4 = _pt(pts, prisms[(ptrdiff_t)p*6 + 4]);
        const double *P5 = _pt(pts, prisms[(ptrdiff_t)p*6 + 5]);

        double we0 = sqrt(_dist2(P1, P0));
        double we1 = sqrt(_dist2(P2, P1));
        double we2 = sqrt(_dist2(P0, P2));
        double wall_edge_mean = (we0 + we1 + we2) / 3.0;

        double h0 = sqrt(_dist2(P3, P0));
        double h1 = sqrt(_dist2(P4, P1));
        double h2 = sqrt(_dist2(P5, P2));
        double h_mean = (h0 + h1 + h2) / 3.0;
        double h_std = sqrt(((h0 - h_mean)*(h0 - h_mean) +
                             (h1 - h_mean)*(h1 - h_mean) +
                             (h2 - h_mean)*(h2 - h_mean)) / 3.0);
        double h_safe = h_mean > 1e-30 ? h_mean : 1e-30;
        double uniformity = 1.0 - (h_std / h_safe);

        double wall_safe = wall_edge_mean > 1e-30 ? wall_edge_mean : 1e-30;
        double aspect = h_mean / wall_safe;

        double p1p0[3] = {P1[0]-P0[0], P1[1]-P0[1], P1[2]-P0[2]};
        double p2p0[3] = {P2[0]-P0[0], P2[1]-P0[1], P2[2]-P0[2]};
        double wall_n[3];
        _cross3(p1p0, p2p0, wall_n);
        double wall_n_norm = sqrt(_dot3(wall_n, wall_n));
        if (wall_n_norm > 1e-30) {
            wall_n[0] /= wall_n_norm;
            wall_n[1] /= wall_n_norm;
            wall_n[2] /= wall_n_norm;
        }

        double prism_dir[3] = {
            ((P3[0]-P0[0]) + (P4[0]-P1[0]) + (P5[0]-P2[0])) / 3.0,
            ((P3[1]-P0[1]) + (P4[1]-P1[1]) + (P5[1]-P2[1])) / 3.0,
            ((P3[2]-P0[2]) + (P4[2]-P1[2]) + (P5[2]-P2[2])) / 3.0,
        };
        double pd_norm = sqrt(_dot3(prism_dir, prism_dir));
        if (pd_norm > 1e-30) {
            prism_dir[0] /= pd_norm;
            prism_dir[1] /= pd_norm;
            prism_dir[2] /= pd_norm;
        }

        double dot = _dot3(wall_n, prism_dir);
        double cos_a = fabs(dot);
        if (cos_a < 0.0) cos_a = 0.0;
        if (cos_a > 1.0) cos_a = 1.0;
        double skew = acos(cos_a);
        if (dot < 0.0) ++n_inv;

        if (p == 0 || aspect < aspect_min) aspect_min = aspect;
        if (p == 0 || aspect > aspect_max) aspect_max = aspect;
        aspect_sum += aspect;
        uniformity_sum += uniformity;
        if (p == 0 || skew > skew_max) skew_max = skew;
        skew_sum += skew;
    }

    stats_out[0] = aspect_min;
    stats_out[1] = aspect_max;
    stats_out[2] = aspect_sum / (double)n_prisms;
    stats_out[3] = uniformity_sum / (double)n_prisms;
    stats_out[4] = skew_max;
    stats_out[5] = skew_sum / (double)n_prisms;
    counts_out[0] = n_inv;
}

/* -----------------------------------------------------------------------
 * hex_skew_simple_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [skew_min, skew_max, skew_mean].
 * counts_out = [n_above_1].
 * ----------------------------------------------------------------------- */
void hex_skew_simple_stats_batch(const double *pts, int n_pts,
                                 const long *hexes, int n_hexes,
                                 double *stats_out,
                                 long *counts_out)
{
    (void)n_pts;
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    counts_out[0] = 0;
    if (n_hexes <= 0) {
        return;
    }

    static const int faces[6][4] = {
        {0, 3, 2, 1},
        {4, 5, 6, 7},
        {0, 1, 5, 4},
        {2, 3, 7, 6},
        {0, 4, 7, 3},
        {1, 2, 6, 5},
    };
    double skew_min = 0.0;
    double skew_max = 0.0;
    double skew_sum = 0.0;
    long n_above = 0;
    long n_faces_total = 0;

    for (int h = 0; h < n_hexes; ++h) {
        double cell_c[3] = {0.0, 0.0, 0.0};
        for (int k = 0; k < 8; ++k) {
            const double *P = _pt(pts, hexes[(ptrdiff_t)h*8 + k]);
            cell_c[0] += P[0];
            cell_c[1] += P[1];
            cell_c[2] += P[2];
        }
        cell_c[0] /= 8.0;
        cell_c[1] /= 8.0;
        cell_c[2] /= 8.0;

        double hex_skew_max = 0.0;
        for (int f = 0; f < 6; ++f) {
            const double *P0 = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][0]]);
            const double *P1 = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][1]]);
            const double *P2 = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][2]]);
            const double *P3 = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][3]]);
            double face_c[3] = {
                (P0[0] + P1[0] + P2[0] + P3[0]) / 4.0,
                (P0[1] + P1[1] + P2[1] + P3[1]) / 4.0,
                (P0[2] + P1[2] + P2[2] + P3[2]) / 4.0,
            };
            double area = _tri_area3(P0, P1, P2) + _tri_area3(P0, P2, P3);
            double denom = sqrt(area);
            if (denom < 1e-30) denom = 1e-30;
            double dx = face_c[0] - cell_c[0];
            double dy = face_c[1] - cell_c[1];
            double dz = face_c[2] - cell_c[2];
            double skew = sqrt(dx*dx + dy*dy + dz*dz) / denom;
            if (n_faces_total == 0 || skew < skew_min) skew_min = skew;
            if (n_faces_total == 0 || skew > skew_max) skew_max = skew;
            if (f == 0 || skew > hex_skew_max) hex_skew_max = skew;
            skew_sum += skew;
            ++n_faces_total;
        }
        if (hex_skew_max > 1.0) ++n_above;
    }

    stats_out[0] = skew_min;
    stats_out[1] = skew_max;
    stats_out[2] = skew_sum / (double)n_faces_total;
    counts_out[0] = n_above;
}

/* -----------------------------------------------------------------------
 * hex_ortho_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [ortho_min_deg, ortho_max_deg, ortho_mean_deg].
 * counts_out = [n_above_30deg].
 * ----------------------------------------------------------------------- */
void hex_ortho_stats_batch(const double *pts, int n_pts,
                           const long *hexes, int n_hexes,
                           double *stats_out,
                           long *counts_out)
{
    (void)n_pts;
    stats_out[0] = 90.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    counts_out[0] = 0;
    if (n_hexes <= 0) {
        return;
    }

    static const int faces[6][4] = {
        {0, 3, 2, 1},
        {4, 5, 6, 7},
        {0, 1, 5, 4},
        {2, 3, 7, 6},
        {0, 4, 7, 3},
        {1, 2, 6, 5},
    };
    double pi = acos(-1.0);
    double deg = 180.0 / pi;
    double ortho_min = 0.0;
    double ortho_max = 0.0;
    double ortho_sum = 0.0;
    long n_above = 0;
    long n_faces_total = 0;

    for (int h = 0; h < n_hexes; ++h) {
        double cell_c[3] = {0.0, 0.0, 0.0};
        for (int k = 0; k < 8; ++k) {
            const double *P = _pt(pts, hexes[(ptrdiff_t)h*8 + k]);
            cell_c[0] += P[0];
            cell_c[1] += P[1];
            cell_c[2] += P[2];
        }
        cell_c[0] /= 8.0;
        cell_c[1] /= 8.0;
        cell_c[2] /= 8.0;

        for (int f = 0; f < 6; ++f) {
            const double *PA = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][0]]);
            const double *PB = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][1]]);
            const double *PC = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][2]]);
            const double *PD = _pt(pts, hexes[(ptrdiff_t)h*8 + faces[f][3]]);
            double face_c[3] = {
                (PA[0] + PB[0] + PC[0] + PD[0]) / 4.0,
                (PA[1] + PB[1] + PC[1] + PD[1]) / 4.0,
                (PA[2] + PB[2] + PC[2] + PD[2]) / 4.0,
            };
            double diag1[3] = {PC[0]-PA[0], PC[1]-PA[1], PC[2]-PA[2]};
            double diag2[3] = {PD[0]-PB[0], PD[1]-PB[1], PD[2]-PB[2]};
            double n[3];
            _cross3(diag1, diag2, n);
            double n_norm = sqrt(_dot3(n, n));
            if (n_norm > 1e-30) {
                n[0] /= n_norm;
                n[1] /= n_norm;
                n[2] /= n_norm;
            }
            double cv[3] = {
                face_c[0] - cell_c[0],
                face_c[1] - cell_c[1],
                face_c[2] - cell_c[2],
            };
            double cv_norm = sqrt(_dot3(cv, cv));
            if (cv_norm > 1e-30) {
                cv[0] /= cv_norm;
                cv[1] /= cv_norm;
                cv[2] /= cv_norm;
            }
            double cos_a = fabs(_dot3(n, cv));
            if (cos_a < 0.0) cos_a = 0.0;
            if (cos_a > 1.0) cos_a = 1.0;
            double ang_deg = acos(cos_a) * deg;
            if (n_faces_total == 0 || ang_deg < ortho_min) ortho_min = ang_deg;
            if (n_faces_total == 0 || ang_deg > ortho_max) ortho_max = ang_deg;
            ortho_sum += ang_deg;
            if (ang_deg > 30.0) ++n_above;
            ++n_faces_total;
        }
    }

    stats_out[0] = ortho_min;
    stats_out[1] = ortho_max;
    stats_out[2] = ortho_sum / (double)n_faces_total;
    counts_out[0] = n_above;
}

/* -----------------------------------------------------------------------
 * hex_jacobian_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [j_min, j_max, j_mean, scaled_j_min, scaled_j_mean].
 * counts_out = [n_inverted].
 * ----------------------------------------------------------------------- */
void hex_jacobian_stats_batch(const double *pts, int n_pts,
                              const long *hexes, int n_hexes,
                              double *stats_out,
                              long *counts_out)
{
    (void)n_pts;
    for (int i = 0; i < 5; ++i) {
        stats_out[i] = 0.0;
    }
    counts_out[0] = 0;
    if (n_hexes <= 0) {
        return;
    }

    static const int corners[8][4] = {
        {0, 1, 3, 4},
        {1, 2, 0, 5},
        {2, 3, 1, 6},
        {3, 0, 2, 7},
        {4, 7, 5, 0},
        {5, 4, 6, 1},
        {6, 5, 7, 2},
        {7, 6, 4, 3},
    };
    double global_j_min = 0.0;
    double global_j_max = 0.0;
    double j_sum = 0.0;
    double scaled_min = 0.0;
    double scaled_sum = 0.0;
    long n_inv = 0;
    long n_j = 0;

    for (int h = 0; h < n_hexes; ++h) {
        double hex_j_min = 0.0;
        double hex_j_max = 0.0;
        for (int ci = 0; ci < 8; ++ci) {
            const double *C = _pt(pts, hexes[(ptrdiff_t)h*8 + corners[ci][0]]);
            const double *A = _pt(pts, hexes[(ptrdiff_t)h*8 + corners[ci][1]]);
            const double *B = _pt(pts, hexes[(ptrdiff_t)h*8 + corners[ci][2]]);
            const double *D = _pt(pts, hexes[(ptrdiff_t)h*8 + corners[ci][3]]);
            double e1[3] = {A[0]-C[0], A[1]-C[1], A[2]-C[2]};
            double e2[3] = {B[0]-C[0], B[1]-C[1], B[2]-C[2]};
            double e3[3] = {D[0]-C[0], D[1]-C[1], D[2]-C[2]};
            double cr[3];
            _cross3(e1, e2, cr);
            double j = _dot3(cr, e3);
            if (n_j == 0 || j < global_j_min) global_j_min = j;
            if (n_j == 0 || j > global_j_max) global_j_max = j;
            if (ci == 0 || j < hex_j_min) hex_j_min = j;
            if (ci == 0 || j > hex_j_max) hex_j_max = j;
            j_sum += j;
            ++n_j;
        }
        if (hex_j_min < 0.0) ++n_inv;
        double scaled = 0.0;
        double denom = fabs(hex_j_max);
        if (denom > 1e-30) {
            scaled = hex_j_min / denom;
        }
        if (h == 0 || scaled < scaled_min) scaled_min = scaled;
        scaled_sum += scaled;
    }

    stats_out[0] = global_j_min;
    stats_out[1] = global_j_max;
    stats_out[2] = j_sum / (double)n_j;
    stats_out[3] = scaled_min;
    stats_out[4] = scaled_sum / (double)n_hexes;
    counts_out[0] = n_inv;
}

/* -----------------------------------------------------------------------
 * hex_inverted_stats_batch
 * -----------------------------------------------------------------------
 * counts_out = [n_inverted, worst_hex_idx, n_written_indices].
 * worst_out = [worst_j_min].
 * indices_out capacity is max_indices.
 * ----------------------------------------------------------------------- */
void hex_inverted_stats_batch(const double *pts, int n_pts,
                              const long *hexes, int n_hexes,
                              int max_indices,
                              long *indices_out,
                              long *counts_out,
                              double *worst_out)
{
    (void)n_pts;
    counts_out[0] = 0;
    counts_out[1] = -1;
    counts_out[2] = 0;
    worst_out[0] = 0.0;
    if (n_hexes <= 0) {
        return;
    }

    static const int corners[8][4] = {
        {0, 1, 3, 4},
        {1, 2, 0, 5},
        {2, 3, 1, 6},
        {3, 0, 2, 7},
        {4, 7, 5, 0},
        {5, 4, 6, 1},
        {6, 5, 7, 2},
        {7, 6, 4, 3},
    };
    long n_inv = 0;
    long n_written = 0;
    double worst = 0.0;
    long worst_idx = 0;

    for (int h = 0; h < n_hexes; ++h) {
        double hex_j_min = 0.0;
        for (int ci = 0; ci < 8; ++ci) {
            const double *C = _pt(pts, hexes[(ptrdiff_t)h*8 + corners[ci][0]]);
            const double *A = _pt(pts, hexes[(ptrdiff_t)h*8 + corners[ci][1]]);
            const double *B = _pt(pts, hexes[(ptrdiff_t)h*8 + corners[ci][2]]);
            const double *D = _pt(pts, hexes[(ptrdiff_t)h*8 + corners[ci][3]]);
            double e1[3] = {A[0]-C[0], A[1]-C[1], A[2]-C[2]};
            double e2[3] = {B[0]-C[0], B[1]-C[1], B[2]-C[2]};
            double e3[3] = {D[0]-C[0], D[1]-C[1], D[2]-C[2]};
            double cr[3];
            _cross3(e1, e2, cr);
            double j = _dot3(cr, e3);
            if (ci == 0 || j < hex_j_min) hex_j_min = j;
        }
        if (h == 0 || hex_j_min < worst) {
            worst = hex_j_min;
            worst_idx = h;
        }
        if (hex_j_min < 0.0) {
            if (n_written < max_indices) {
                indices_out[n_written] = h;
                ++n_written;
            }
            ++n_inv;
        }
    }

    counts_out[0] = n_inv;
    counts_out[1] = worst_idx;
    counts_out[2] = n_written;
    worst_out[0] = worst;
}

static double _hex_signed_volume5(const double *pts, const long *cell)
{
    static const int T[5][4] = {
        {0, 1, 3, 4},
        {1, 2, 3, 6},
        {3, 4, 6, 7},
        {1, 4, 5, 6},
        {1, 3, 4, 6},
    };
    double total = 0.0;
    for (int ti = 0; ti < 5; ++ti) {
        const double *A = _pt(pts, cell[T[ti][0]]);
        const double *B = _pt(pts, cell[T[ti][1]]);
        const double *C = _pt(pts, cell[T[ti][2]]);
        const double *D = _pt(pts, cell[T[ti][3]]);
        double e1[3] = {B[0] - A[0], B[1] - A[1], B[2] - A[2]};
        double e2[3] = {C[0] - A[0], C[1] - A[1], C[2] - A[2]};
        double e3[3] = {D[0] - A[0], D[1] - A[1], D[2] - A[2]};
        double cr[3];
        _cross3(e2, e3, cr);
        total += _dot3(e1, cr);
    }
    return total;
}

/* -----------------------------------------------------------------------
 * hex_validate_volumes_batch
 * -----------------------------------------------------------------------
 * hexes is modified in-place. counts_out = [n_flipped, n_degenerate].
 * ----------------------------------------------------------------------- */
void hex_validate_volumes_batch(const double *pts, int n_pts,
                                long *hexes,
                                int n_hexes,
                                double degenerate_eps,
                                long *counts_out)
{
    (void)n_pts;
    counts_out[0] = 0;
    counts_out[1] = 0;
    for (int hi = 0; hi < n_hexes; ++hi) {
        long *cell = hexes + (ptrdiff_t)hi * 8;
        double vol = _hex_signed_volume5(pts, cell);
        if (vol >= -degenerate_eps) {
            continue;
        }

        long orig[8];
        for (int j = 0; j < 8; ++j) {
            orig[j] = cell[j];
        }
        cell[0] = orig[4];
        cell[1] = orig[5];
        cell[2] = orig[6];
        cell[3] = orig[7];
        cell[4] = orig[0];
        cell[5] = orig[1];
        cell[6] = orig[2];
        cell[7] = orig[3];
        double vol2 = _hex_signed_volume5(pts, cell);
        if (vol2 < -degenerate_eps) {
            for (int j = 0; j < 8; ++j) {
                cell[j] = orig[j];
            }
            counts_out[1] += 1;
        } else {
            counts_out[0] += 1;
        }
    }
}

static void _closest_point_triangle3(const double *P,
                                     const double *A,
                                     const double *B,
                                     const double *C,
                                     double *out)
{
    double ab[3] = {B[0] - A[0], B[1] - A[1], B[2] - A[2]};
    double ac[3] = {C[0] - A[0], C[1] - A[1], C[2] - A[2]};
    double ap[3] = {P[0] - A[0], P[1] - A[1], P[2] - A[2]};
    double d1 = _dot3(ab, ap);
    double d2 = _dot3(ac, ap);
    if (d1 <= 0.0 && d2 <= 0.0) {
        out[0] = A[0]; out[1] = A[1]; out[2] = A[2];
        return;
    }

    double bp[3] = {P[0] - B[0], P[1] - B[1], P[2] - B[2]};
    double d3 = _dot3(ab, bp);
    double d4 = _dot3(ac, bp);
    if (d3 >= 0.0 && d4 <= d3) {
        out[0] = B[0]; out[1] = B[1]; out[2] = B[2];
        return;
    }

    double vc = d1 * d4 - d3 * d2;
    if (vc <= 0.0 && d1 >= 0.0 && d3 <= 0.0) {
        double v = d1 / (d1 - d3);
        out[0] = A[0] + v * ab[0];
        out[1] = A[1] + v * ab[1];
        out[2] = A[2] + v * ab[2];
        return;
    }

    double cp[3] = {P[0] - C[0], P[1] - C[1], P[2] - C[2]};
    double d5 = _dot3(ab, cp);
    double d6 = _dot3(ac, cp);
    if (d6 >= 0.0 && d5 <= d6) {
        out[0] = C[0]; out[1] = C[1]; out[2] = C[2];
        return;
    }

    double vb = d5 * d2 - d1 * d6;
    if (vb <= 0.0 && d2 >= 0.0 && d6 <= 0.0) {
        double w = d2 / (d2 - d6);
        out[0] = A[0] + w * ac[0];
        out[1] = A[1] + w * ac[1];
        out[2] = A[2] + w * ac[2];
        return;
    }

    double va = d3 * d6 - d5 * d4;
    if (va <= 0.0 && (d4 - d3) >= 0.0 && (d5 - d6) >= 0.0) {
        double w = (d4 - d3) / ((d4 - d3) + (d5 - d6));
        out[0] = B[0] + w * (C[0] - B[0]);
        out[1] = B[1] + w * (C[1] - B[1]);
        out[2] = B[2] + w * (C[2] - B[2]);
        return;
    }

    double denom = 1.0 / (va + vb + vc);
    double v = vb * denom;
    double w = vc * denom;
    out[0] = A[0] + ab[0] * v + ac[0] * w;
    out[1] = A[1] + ab[1] * v + ac[1] * w;
    out[2] = A[2] + ab[2] * v + ac[2] * w;
}

/* -----------------------------------------------------------------------
 * closest_points_on_triangles_candidates_batch
 * -----------------------------------------------------------------------
 * candidate_idx has shape (n_points, k). Invalid candidates are <0 or >=n_tri.
 * has_out[i] is 1 if at least one candidate was valid.
 * ----------------------------------------------------------------------- */
void closest_points_on_triangles_candidates_batch(const double *points,
                                                  int n_points,
                                                  const double *tri_a,
                                                  const double *tri_b,
                                                  const double *tri_c,
                                                  int n_tri,
                                                  const long *candidate_idx,
                                                  int k,
                                                  double *best_points_out,
                                                  double *best_dist2_out,
                                                  long *has_out)
{
    for (int i = 0; i < n_points; ++i) {
        const double *P = points + 3 * i;
        double best_pt[3] = {P[0], P[1], P[2]};
        double best_d2 = INFINITY;
        long has = 0;
        for (int j = 0; j < k; ++j) {
            long ti = candidate_idx[(ptrdiff_t)i * k + j];
            if (ti < 0 || ti >= n_tri) {
                continue;
            }
            double cp[3];
            _closest_point_triangle3(
                P,
                tri_a + 3 * ti,
                tri_b + 3 * ti,
                tri_c + 3 * ti,
                cp
            );
            double dx = cp[0] - P[0];
            double dy = cp[1] - P[1];
            double dz = cp[2] - P[2];
            double d2 = dx * dx + dy * dy + dz * dz;
            if (!has || d2 < best_d2) {
                best_d2 = d2;
                best_pt[0] = cp[0];
                best_pt[1] = cp[1];
                best_pt[2] = cp[2];
                has = 1;
            }
        }
        best_points_out[3 * i + 0] = best_pt[0];
        best_points_out[3 * i + 1] = best_pt[1];
        best_points_out[3 * i + 2] = best_pt[2];
        best_dist2_out[i] = best_d2;
        has_out[i] = has;
    }
}

/* -----------------------------------------------------------------------
 * poly_volume_stats_batch
 * -----------------------------------------------------------------------
 * face_indices is a flattened vertex-index array.
 * face_offsets has shape (n_faces + 1).
 * cell_offsets has shape (n_cells + 1), indexing faces in sequential order.
 * volumes_out has shape (n_cells,).
 * stats_out = [volume_min, volume_max, volume_mean, total_volume].
 * counts_out = [n_negative].
 * ----------------------------------------------------------------------- */
void poly_volume_stats_batch(const double *pts, int n_pts,
                             const long *face_indices,
                             const long *face_offsets,
                             int n_faces,
                             const long *cell_offsets,
                             int n_cells,
                             double *volumes_out,
                             double *stats_out,
                             long *counts_out)
{
    (void)n_pts;
    (void)n_faces;
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    stats_out[3] = 0.0;
    counts_out[0] = 0;
    if (n_cells <= 0) {
        return;
    }

    double vol_min = 0.0;
    double vol_max = 0.0;
    double vol_total = 0.0;
    long n_negative = 0;

    for (int ci = 0; ci < n_cells; ++ci) {
        double cell_vol = 0.0;
        long f_begin = cell_offsets[ci];
        long f_end = cell_offsets[ci + 1];
        for (long fi = f_begin; fi < f_end; ++fi) {
            long i_begin = face_offsets[fi];
            long i_end = face_offsets[fi + 1];
            long n_v = i_end - i_begin;
            if (n_v < 3) {
                continue;
            }
            double center[3] = {0.0, 0.0, 0.0};
            for (long k = i_begin; k < i_end; ++k) {
                const double *P = _pt(pts, face_indices[k]);
                center[0] += P[0];
                center[1] += P[1];
                center[2] += P[2];
            }
            center[0] /= (double)n_v;
            center[1] /= (double)n_v;
            center[2] /= (double)n_v;

            double face_n[3] = {0.0, 0.0, 0.0};
            for (long j = 0; j < n_v; ++j) {
                const double *P0 = _pt(pts, face_indices[i_begin + j]);
                const double *P1 = _pt(pts, face_indices[i_begin + ((j + 1) % n_v)]);
                double a[3] = {P0[0]-center[0], P0[1]-center[1], P0[2]-center[2]};
                double b[3] = {P1[0]-center[0], P1[1]-center[1], P1[2]-center[2]};
                double cr[3];
                _cross3(a, b, cr);
                face_n[0] += cr[0];
                face_n[1] += cr[1];
                face_n[2] += cr[2];
            }
            cell_vol += _dot3(center, face_n) / 6.0;
        }

        volumes_out[ci] = cell_vol;
        if (ci == 0 || cell_vol < vol_min) vol_min = cell_vol;
        if (ci == 0 || cell_vol > vol_max) vol_max = cell_vol;
        vol_total += cell_vol;
        if (cell_vol < 0.0) ++n_negative;
    }

    stats_out[0] = vol_min;
    stats_out[1] = vol_max;
    stats_out[2] = vol_total / (double)n_cells;
    stats_out[3] = vol_total;
    counts_out[0] = n_negative;
}

/* -----------------------------------------------------------------------
 * poly_validate_volumes_batch
 * -----------------------------------------------------------------------
 * Same centroid fan-volume convention as native_poly.voronoi validation.
 * counts_out = [n_negative, n_degenerate].
 * ----------------------------------------------------------------------- */
void poly_validate_volumes_batch(const double *pts, int n_pts,
                                 const long *face_indices,
                                 const long *face_offsets,
                                 int n_faces,
                                 const long *cell_offsets,
                                 int n_cells,
                                 double degenerate_eps,
                                 long *counts_out)
{
    (void)n_pts;
    (void)n_faces;
    counts_out[0] = 0;
    counts_out[1] = 0;
    for (int ci = 0; ci < n_cells; ++ci) {
        long f_begin = cell_offsets[ci];
        long f_end = cell_offsets[ci + 1];
        long max_idx_count = 0;
        for (long fi = f_begin; fi < f_end; ++fi) {
            max_idx_count += face_offsets[fi + 1] - face_offsets[fi];
        }
        if (max_idx_count < 4) {
            counts_out[1] += 1;
            continue;
        }
        long *unique = (long *)malloc((size_t)max_idx_count * sizeof(long));
        if (unique == NULL) {
            counts_out[1] += 1;
            continue;
        }
        long n_unique = 0;
        for (long fi = f_begin; fi < f_end; ++fi) {
            for (long k = face_offsets[fi]; k < face_offsets[fi + 1]; ++k) {
                long v = face_indices[k];
                int seen = 0;
                for (long u = 0; u < n_unique; ++u) {
                    if (unique[u] == v) {
                        seen = 1;
                        break;
                    }
                }
                if (!seen) {
                    unique[n_unique++] = v;
                }
            }
        }
        if (n_unique < 4) {
            free(unique);
            counts_out[1] += 1;
            continue;
        }

        double centroid[3] = {0.0, 0.0, 0.0};
        for (long u = 0; u < n_unique; ++u) {
            const double *P = _pt(pts, unique[u]);
            centroid[0] += P[0];
            centroid[1] += P[1];
            centroid[2] += P[2];
        }
        centroid[0] /= (double)n_unique;
        centroid[1] /= (double)n_unique;
        centroid[2] /= (double)n_unique;

        double total_vol = 0.0;
        for (long fi = f_begin; fi < f_end; ++fi) {
            long begin = face_offsets[fi];
            long end = face_offsets[fi + 1];
            long n_v = end - begin;
            if (n_v < 3) {
                continue;
            }
            const double *A = _pt(pts, face_indices[begin]);
            double a[3] = {
                A[0] - centroid[0],
                A[1] - centroid[1],
                A[2] - centroid[2],
            };
            for (long k = 1; k < n_v - 1; ++k) {
                const double *B = _pt(pts, face_indices[begin + k]);
                const double *C = _pt(pts, face_indices[begin + k + 1]);
                double b[3] = {
                    B[0] - centroid[0],
                    B[1] - centroid[1],
                    B[2] - centroid[2],
                };
                double c[3] = {
                    C[0] - centroid[0],
                    C[1] - centroid[1],
                    C[2] - centroid[2],
                };
                double cr[3];
                _cross3(b, c, cr);
                total_vol += _dot3(a, cr);
            }
        }
        free(unique);
        if (fabs(total_vol) < degenerate_eps) {
            counts_out[1] += 1;
        } else if (total_vol < 0.0) {
            counts_out[0] += 1;
        }
    }
}

/* -----------------------------------------------------------------------
 * poly_aspect_stats_batch
 * -----------------------------------------------------------------------
 * cell_indices is a flattened vertex-index array.
 * cell_offsets has shape (n_cells + 1).
 * stats_out = [aspect_min, aspect_max, aspect_mean] over valid cells.
 * counts_out = [n_above_5, n_valid].
 * ----------------------------------------------------------------------- */
void poly_aspect_stats_batch(const double *pts, int n_pts,
                             const long *cell_indices,
                             const long *cell_offsets,
                             int n_cells,
                             double *stats_out,
                             long *counts_out)
{
    (void)n_pts;
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    stats_out[2] = 0.0;
    counts_out[0] = 0;
    counts_out[1] = 0;
    if (n_cells <= 0) {
        return;
    }

    double aspect_min = 0.0;
    double aspect_max = 0.0;
    double aspect_sum = 0.0;
    long n_valid = 0;
    long n_above_5 = 0;

    for (int ci = 0; ci < n_cells; ++ci) {
        long begin = cell_offsets[ci];
        long end = cell_offsets[ci + 1];
        long n_v = end - begin;
        if (n_v < 4) {
            continue;
        }

        const double *P0 = _pt(pts, cell_indices[begin]);
        double min_x = P0[0], max_x = P0[0];
        double min_y = P0[1], max_y = P0[1];
        double min_z = P0[2], max_z = P0[2];
        for (long k = begin + 1; k < end; ++k) {
            const double *P = _pt(pts, cell_indices[k]);
            if (P[0] < min_x) min_x = P[0];
            if (P[0] > max_x) max_x = P[0];
            if (P[1] < min_y) min_y = P[1];
            if (P[1] > max_y) max_y = P[1];
            if (P[2] < min_z) min_z = P[2];
            if (P[2] > max_z) max_z = P[2];
        }

        double ex = max_x - min_x;
        double ey = max_y - min_y;
        double ez = max_z - min_z;
        double ext_min = ex;
        if (ey < ext_min) ext_min = ey;
        if (ez < ext_min) ext_min = ez;
        double ext_max = ex;
        if (ey > ext_max) ext_max = ey;
        if (ez > ext_max) ext_max = ez;

        double aspect = (ext_min < 1e-30) ? 1e6 : (ext_max / ext_min);
        if (n_valid == 0 || aspect < aspect_min) aspect_min = aspect;
        if (n_valid == 0 || aspect > aspect_max) aspect_max = aspect;
        aspect_sum += aspect;
        if (aspect > 5.0) ++n_above_5;
        ++n_valid;
    }

    if (n_valid > 0) {
        stats_out[0] = aspect_min;
        stats_out[1] = aspect_max;
        stats_out[2] = aspect_sum / (double)n_valid;
    }
    counts_out[0] = n_above_5;
    counts_out[1] = n_valid;
}

/* -----------------------------------------------------------------------
 * poly_convex_stats_batch
 * -----------------------------------------------------------------------
 * cell_indices is a flattened vertex-index array.
 * cell_offsets has shape (n_cells + 1).
 * planes is a flattened (n_planes, 4) array.
 * plane_offsets has shape (n_cells + 1).
 * counts_out = [n_convex].
 * stats_out = [max_violation].
 * ----------------------------------------------------------------------- */
void poly_convex_stats_batch(const double *pts, int n_pts,
                             const long *cell_indices,
                             const long *cell_offsets,
                             const double *planes,
                             const long *plane_offsets,
                             int n_cells,
                             double tol,
                             long *counts_out,
                             double *stats_out)
{
    (void)n_pts;
    counts_out[0] = 0;
    stats_out[0] = 0.0;
    if (n_cells <= 0) {
        return;
    }

    long n_convex = 0;
    double max_violation = 0.0;

    for (int ci = 0; ci < n_cells; ++ci) {
        long v_begin = cell_offsets[ci];
        long v_end = cell_offsets[ci + 1];
        long p_begin = plane_offsets[ci];
        long p_end = plane_offsets[ci + 1];
        if (v_end <= v_begin || p_end <= p_begin) {
            ++n_convex;
            continue;
        }

        double max_signed = 0.0;
        int has_signed = 0;
        for (long vk = v_begin; vk < v_end; ++vk) {
            const double *P = _pt(pts, cell_indices[vk]);
            for (long pk = p_begin; pk < p_end; ++pk) {
                const double *pl = planes + 4 * pk;
                double signed_dist = pl[0] * P[0] + pl[1] * P[1] + pl[2] * P[2] + pl[3];
                if (!has_signed || signed_dist > max_signed) {
                    max_signed = signed_dist;
                    has_signed = 1;
                }
            }
        }

        double violation = max_signed > 0.0 ? max_signed : 0.0;
        if (violation > tol) {
            if (violation > max_violation) {
                max_violation = violation;
            }
        } else {
            ++n_convex;
        }
    }

    counts_out[0] = n_convex;
    stats_out[0] = max_violation;
}
