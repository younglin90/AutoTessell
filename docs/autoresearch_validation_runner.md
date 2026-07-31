# Validation runner

`python scripts/autoresearch_validation_runner.py manifest.json --evidence evidence.json`

Manifest: `{ "concurrency": 1, "jobs": [{"name":"x","command":["python","-c","..."],"timeout_seconds":10}] }`.

`concurrency` must be an integer in range `1..2`. Zero, negative, fractional,
boolean, string, or larger values write `UNVERIFIED` evidence with no jobs run;
the runner never creates a zero-permit semaphore.

Only zero-exit jobs are `PASS`; timeout, execution error, and invalid input are
`UNVERIFIED` or `ERROR` and make aggregate status non-PASS. Timeout evidence
contains the exact command, `status` and `result_status` of `TIMEOUT`, elapsed
seconds, and termination result `TERM` or `KILL`. Evidence output directories
are created when absent.
