# Hex reader snapshot provenance L0 (2026-07-31)

`CORRECTNESS_KEEP`, default off. The explicit reader path streams source bytes
to a private `0700` directory and `0600` snapshot, hashes and fsyncs it, and
passes only that snapshot pathname to the current provenance reader. The
snapshot is removed on all result paths.

The transaction returns source-snapshot and canonical reader-payload SHA256
values but is always non-accepting: no candidate, mesh output, physical-group
claim, routing, or legacy reader/default change. Output-boundary to B-Rep
evidence remains deferred.
