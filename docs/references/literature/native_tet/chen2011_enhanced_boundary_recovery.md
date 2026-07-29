# Chen et al. 2011 - enhanced Steiner-point-suppression boundary recovery

**Authors:** Jianjun Chen, Dawei Zhao, Zhengge Huang, Yao Zheng, Shuming Gao  
**Venue:** *Computers & Structures* 89(5-6), 455-466 (2011)  
**DOI:** `10.1016/j.compstruc.2010.11.016`  
**Status:** FULL_READ (user-supplied `chen2011.pdf`, pp. 457-459 visually
checked on 2026-07-28).

## Relevant mechanism

The paper recovers missing faces by classifying each penetration tetrahedron
against the missing constraint triangle and inserting Steiner points at the
actual intersections. The five classes are the number of tetrahedron edges
that penetrate the missing face: zero, one, two, three, or four. The zero-edge
class already has a tetrahedron face that is a subface of the constraint and
requires no decomposition. One and two edge classes use fixed decompositions.
Three-edge cases have four S/Z patterns (`S2Z1`, `S1Z2`, `S3Z0`, `S0Z3`), and
four-edge cases have six patterns (`SSSS`, `ZSSS`, `ZZSS`, `ZSZS`, `ZZZS`,
`ZZZZ`). Some patterns introduce an interior centroid only after the cut
polyhedron has been shown convex, which is the paper's positive-volume
argument.

S/Z is a shared-face conformity rule, not an independent quality choice. When
two intersection points lie on one triangular face, the adjacent tetrahedron
must use the opposite S/Z face triangulation. With one inserted point, the face
decomposition is unique. This follows directly from Fig. 4 and its adjacent
paragraph. Any port must retain a per-shared-face decision ledger; choosing a
template independently per tetrahedron would make a nonconforming internal
face.

## Consequence for AutoTessell

`TET-CHEN-CASE1-L0` was too broad: it combined the paper's first (zero-edge,
no-decomposition) class with the later S/Z compatibility condition. They are
not one executable template. Split the work as follows:

1. `TET-CHEN-PENETRATION-CLASSIFY-L0`: exact/read-only triangle-tetrahedron
   intersection classification and intersection-point ownership, including
   rejection of coplanar and non-unique cases.
2. `TET-CHEN-ONEEDGE-SPLIT-L0`: one-edge child-tet template with explicit
   orientation, parent-volume, external-cavity-boundary, and recovered-face
   checks.
3. `TET-CHEN-SZ-CONFORMITY-L0`: two adjacent penetration tetrahedra sharing a
   two-point face; prove opposite decisions give the same shared triangulation
   and equal external cavity boundary, while same decisions reject/rollback.

The current `cdt_recovery.py` has only missing-*edge* discovery and accepts
candidate flips on improved missing-edge count. It does not compute a missing
triangle's penetration tetrahedra, intersection points, class, shared-face
ledger, or source-face exterior recovery. Therefore no Chen template may be
called from it before the classifier card passes. This restriction protects the
exact source-surface boundary invariant.
