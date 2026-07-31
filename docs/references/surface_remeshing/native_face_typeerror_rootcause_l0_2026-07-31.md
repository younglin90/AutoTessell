# NATIVE-FACE-TYPEERROR-ROOTCAUSE-L0

Date: 2026-07-31
State: `DEFER / CORRECTNESS_KEEP`; no production repair.

## Historical signal

The campaign ledger recorded three direct `native_face_remesh` calls as
`native operation failed: TypeError`.  The surviving public error is emitted by
the direct native-face operation boundary in
`core/preprocessor/native_remesh/face.py`: its broad exception handler preserves
the exception class but intentionally does not expose an implementation
traceback.  No historical traceback, failing input, or environment lockfile was
stored with that earlier result.

## Current reproduction

On the current `master` baseline, canonical icosphere direct calls with the
historical-style one-iteration and protected-edge configurations complete three
identical repeats each without a `TypeError`.  The existing native-face suite
also passes (`13 passed in 4.03 s`).  Therefore the historical TypeError cannot
be assigned to a first-party source line without inventing evidence.

The focused L0 regression also injects a sentinel `TypeError` at the direct
native operation boundary.  The public contract returns an explicit rejected
result with unchanged source arrays and
`native operation failed: TypeError`; it does not silently repair, accept, or
route elsewhere.

## Decision

No source-preserving one-path fix is proven.  This card deliberately changes no
native-face implementation, routing/default/fallback selection, threshold,
geometry, topology, or dependency.  Status remains `DEFER` until one of the
following supplies a reproducible `(vertices, faces, config, environment,
traceback)` tuple:

1. the original direct-call input and traceback;
2. a current canonical or corpus reproducer; or
3. a clean-environment failure whose exact originating first-party line is
   captured before the public boundary intentionally converts it to a rejected
   result.

No external code is used or copied.
