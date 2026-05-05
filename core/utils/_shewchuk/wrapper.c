/*****************************************************************************/
/*  wrapper.c - Thin C ABI wrapper for Shewchuk predicates.                  */
/*                                                                           */
/*  Exposes only three symbols for ctypes:                                   */
/*    shewchuk_init()       - initialize epsilon/splitter                    */
/*    orient3d_sign()       - returns -1, 0, or +1                          */
/*    insphere_sign()       - returns -1, 0, or +1                          */
/*                                                                           */
/*  Public domain — bundled for AutoTessell.                                 */
/*****************************************************************************/

/* Pull in the Shewchuk implementation */
#include "predicates.c"

/**
 * shewchuk_init - Must be called once before using predicates.
 * Calls exactinit() from predicates.c to compute epsilon/splitter.
 */
void shewchuk_init(void)
{
    exactinit();
}

/**
 * orient3d_sign - Adaptive exact orientation test.
 *
 * Convention: returns +1 if d is above the plane through a,b,c
 * (i.e., det(b-a, c-a, d-a) > 0 in the standard right-hand convention),
 * which is OPPOSITE to the raw Shewchuk orient3d() sign.
 *
 * AutoTessell uses det(b-a, c-a, d-a) as the canonical orient3d, so we
 * negate the Shewchuk result to match.
 *
 * @param pa  pointer to double[3]
 * @param pb  pointer to double[3]
 * @param pc  pointer to double[3]
 * @param pd  pointer to double[3]
 *
 * Returns:
 *   +1 if det(b-a, c-a, d-a) > 0
 *   -1 if det(b-a, c-a, d-a) < 0
 *    0 if coplanar
 */
int orient3d_sign(double *pa, double *pb, double *pc, double *pd)
{
    /* Shewchuk orient3d = det(a-d, b-d, c-d) = -det(b-a, c-a, d-a).
       Negate to obtain the AutoTessell convention. */
    double v = orient3d(pa, pb, pc, pd);
    if (v > 0.0) return -1;
    if (v < 0.0) return  1;
    return 0;
}

/**
 * insphere_sign - Adaptive exact insphere test.
 *
 * Convention: matches AutoTessell predicates_exact.insphere():
 * returns +1 if pe is inside the circumsphere of the tet pa,pb,pc,pd
 * when the tet has positive orientation det(b-a, c-a, d-a) > 0.
 *
 * The raw Shewchuk insphere() requires a tet with positive Shewchuk
 * orient3d (det(a-d, b-d, c-d) > 0), which is the negative of our
 * convention.  Therefore we call insphere with vertices reordered
 * (swap pa<->pb to flip orientation) and negate the result.
 *
 * @param pa ... pe  pointers to double[3]
 * Returns:
 *   +1 if pe is inside the circumsphere
 *   -1 if outside
 *    0 if cospherical
 */
int insphere_sign(double *pa, double *pb, double *pc, double *pd, double *pe)
{
    /* Our orient convention: det(b-a, c-a, d-a) > 0 = positive.
       Shewchuk orient convention: det(a-d, b-d, c-d) > 0 = positive.
       These have opposite signs, so pa,pb,pc,pd with our positive
       orientation have Shewchuk negative orientation.

       Shewchuk insphere() assumes its OWN positive orientation.
       If we pass pa,pb,pc,pd with our positive (their negative) orientation,
       the insphere result is negated relative to what we want.

       Fix: negate the result, or equivalently swap two vertices (e.g. pb<->pc)
       to convert from our-positive to Shewchuk-positive tet.
       We swap pb and pc here.
    */
    double v = insphere(pa, pc, pb, pd, pe);
    if (v > 0.0) return  1;
    if (v < 0.0) return -1;
    return 0;
}
