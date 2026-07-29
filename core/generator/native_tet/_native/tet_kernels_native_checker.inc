/* NativeMeshChecker ctypes fallback kernels.
 * Included from tet_kernels.c after shared math/topology helpers.
 */

/* -----------------------------------------------------------------------
 * native_checker_non_orthogonality_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [max_non_ortho_deg, avg_non_ortho_deg].
 * counts_out = [severe_count, valid_count].
 * ----------------------------------------------------------------------- */
void native_checker_non_orthogonality_stats_batch(const double *face_normals,
                                                  const double *cell_centres,
                                                  const long *owner,
                                                  const long *neighbour,
                                                  int n_internal,
                                                  double severe_threshold,
                                                  double *stats_out,
                                                  long *counts_out)
{
    stats_out[0] = 0.0;
    stats_out[1] = 0.0;
    counts_out[0] = 0;
    counts_out[1] = 0;
    if (n_internal <= 0) {
        return;
    }

    const double rad_to_deg = 57.2957795130823208768;
    double max_angle = 0.0;
    double sum_angle = 0.0;
    long severe_count = 0;
    long valid_count = 0;

    for (int i = 0; i < n_internal; ++i) {
        const double *no = face_normals + 3 * i;
        const double *co = cell_centres + 3 * owner[i];
        const double *cn = cell_centres + 3 * neighbour[i];
        double dx = cn[0] - co[0];
        double dy = cn[1] - co[1];
        double dz = cn[2] - co[2];
        double d_mag = sqrt(dx * dx + dy * dy + dz * dz);
        double n_mag = sqrt(no[0] * no[0] + no[1] * no[1] + no[2] * no[2]);
        if (d_mag <= 1e-30 || n_mag <= 1e-30) {
            continue;
        }
        double dot = dx * no[0] + dy * no[1] + dz * no[2];
        double c = fabs(dot) / (d_mag * n_mag);
        if (c < 0.0) c = 0.0;
        if (c > 1.0) c = 1.0;
        double angle = acos(c) * rad_to_deg;
        if (angle > max_angle) max_angle = angle;
        sum_angle += angle;
        if (angle > severe_threshold) ++severe_count;
        ++valid_count;
    }

    if (valid_count > 0) {
        stats_out[0] = max_angle;
        stats_out[1] = sum_angle / (double)valid_count;
    }
    counts_out[0] = severe_count;
    counts_out[1] = valid_count;
}

/* -----------------------------------------------------------------------
 * native_checker_skewness_stats_batch
 * -----------------------------------------------------------------------
 * stats_out = [max_skewness].
 * ----------------------------------------------------------------------- */
void native_checker_skewness_stats_batch(const double *face_centres,
                                         const double *cell_centres,
                                         const long *owner,
                                         const long *neighbour,
                                         int n_internal,
                                         double *stats_out)
{
    stats_out[0] = 0.0;
    if (n_internal <= 0) {
        return;
    }

    double max_skew = 0.0;
    for (int i = 0; i < n_internal; ++i) {
        const double *po = cell_centres + 3 * owner[i];
        const double *pn = cell_centres + 3 * neighbour[i];
        const double *fc = face_centres + 3 * i;
        double dx = pn[0] - po[0];
        double dy = pn[1] - po[1];
        double dz = pn[2] - po[2];
        double d2 = dx * dx + dy * dy + dz * dz;
        if (d2 <= 1e-60) {
            continue;
        }
        double fx = fc[0] - po[0];
        double fy = fc[1] - po[1];
        double fz = fc[2] - po[2];
        double t = (fx * dx + fy * dy + fz * dz) / d2;
        double px = po[0] + t * dx;
        double py = po[1] + t * dy;
        double pz = po[2] + t * dz;
        double sx = fc[0] - px;
        double sy = fc[1] - py;
        double sz = fc[2] - pz;
        double skew = sqrt(sx * sx + sy * sy + sz * sz) / sqrt(d2);
        if (skew > max_skew) {
            max_skew = skew;
        }
    }
    stats_out[0] = max_skew;
}

/* -----------------------------------------------------------------------
 * native_checker_face_geometry_batch
 * -----------------------------------------------------------------------
 * face_indices is a flattened vertex-index array.
 * face_offsets has shape (n_faces + 1).
 * centres_out/normals_out have shape (n_faces, 3); areas_out has (n_faces,).
 * ----------------------------------------------------------------------- */
void native_checker_face_geometry_batch(const double *points,
                                        int n_points,
                                        const long *face_indices,
                                        const long *face_offsets,
                                        int n_faces,
                                        double *centres_out,
                                        double *normals_out,
                                        double *areas_out)
{
    (void)n_points;
    for (int fi = 0; fi < n_faces; ++fi) {
        long begin = face_offsets[fi];
        long end = face_offsets[fi + 1];
        long n_v = end - begin;
        double cx = 0.0, cy = 0.0, cz = 0.0;
        for (long k = begin; k < end; ++k) {
            const double *P = _pt(points, face_indices[k]);
            cx += P[0];
            cy += P[1];
            cz += P[2];
        }
        if (n_v > 0) {
            double inv = 1.0 / (double)n_v;
            cx *= inv;
            cy *= inv;
            cz *= inv;
        }
        centres_out[3 * fi + 0] = cx;
        centres_out[3 * fi + 1] = cy;
        centres_out[3 * fi + 2] = cz;

        normals_out[3 * fi + 0] = 0.0;
        normals_out[3 * fi + 1] = 0.0;
        normals_out[3 * fi + 2] = 0.0;
        areas_out[fi] = 0.0;
        if (n_v < 3) {
            continue;
        }

        const double *P0 = _pt(points, face_indices[begin]);
        double ax = 0.0, ay = 0.0, az = 0.0;
        for (long j = begin + 1; j < end - 1; ++j) {
            const double *P1 = _pt(points, face_indices[j]);
            const double *P2 = _pt(points, face_indices[j + 1]);
            double e1[3] = {P1[0] - P0[0], P1[1] - P0[1], P1[2] - P0[2]};
            double e2[3] = {P2[0] - P0[0], P2[1] - P0[1], P2[2] - P0[2]};
            double cr[3];
            _cross3(e1, e2, cr);
            ax += cr[0];
            ay += cr[1];
            az += cr[2];
        }
        double mag = sqrt(ax * ax + ay * ay + az * az);
        areas_out[fi] = 0.5 * mag;
        if (mag > 0.0) {
            normals_out[3 * fi + 0] = ax / mag;
            normals_out[3 * fi + 1] = ay / mag;
            normals_out[3 * fi + 2] = az / mag;
        }
    }
}

/* -----------------------------------------------------------------------
 * native_checker_cell_centres_from_face_centres_batch
 * -----------------------------------------------------------------------
 * Aggregate face centres per owner/neighbour cell and divide by face count.
 * centres_out has shape (n_cells, 3).
 * ----------------------------------------------------------------------- */
void native_checker_cell_centres_from_face_centres_batch(const double *face_centres,
                                                        const long *owner,
                                                        int n_faces,
                                                        const long *neighbour,
                                                        int n_internal,
                                                        int n_cells,
                                                        double *centres_out)
{
    if (n_cells <= 0) {
        return;
    }
    long *counts = (long *)calloc((size_t)n_cells, sizeof(long));
    if (counts == NULL) {
        return;
    }
    for (int ci = 0; ci < n_cells; ++ci) {
        centres_out[3 * ci + 0] = 0.0;
        centres_out[3 * ci + 1] = 0.0;
        centres_out[3 * ci + 2] = 0.0;
    }

    for (int fi = 0; fi < n_faces; ++fi) {
        long c = owner[fi];
        if (c < 0 || c >= n_cells) {
            continue;
        }
        centres_out[3 * c + 0] += face_centres[3 * fi + 0];
        centres_out[3 * c + 1] += face_centres[3 * fi + 1];
        centres_out[3 * c + 2] += face_centres[3 * fi + 2];
        counts[c] += 1;
    }
    int n_int_use = n_internal < n_faces ? n_internal : n_faces;
    for (int fi = 0; fi < n_int_use; ++fi) {
        long c = neighbour[fi];
        if (c < 0 || c >= n_cells) {
            continue;
        }
        centres_out[3 * c + 0] += face_centres[3 * fi + 0];
        centres_out[3 * c + 1] += face_centres[3 * fi + 1];
        centres_out[3 * c + 2] += face_centres[3 * fi + 2];
        counts[c] += 1;
    }

    for (int ci = 0; ci < n_cells; ++ci) {
        if (counts[ci] > 0) {
            double inv = 1.0 / (double)counts[ci];
            centres_out[3 * ci + 0] *= inv;
            centres_out[3 * ci + 1] *= inv;
            centres_out[3 * ci + 2] *= inv;
        }
    }
    free(counts);
}

typedef struct {
    long a;
    long b;
    long c;
    long index;
} SurfaceFaceKey;
