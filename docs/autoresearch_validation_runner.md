# Validation runner

`python scripts/autoresearch_validation_runner.py manifest.json --evidence evidence.json`

Manifest: `{ "concurrency": 2, "jobs": [{"name":"x","command":["python","-c","..."],"timeout_seconds":10}] }`.
Only zero-exit jobs are `PASS`; timeout, execution error, and invalid input are
`UNVERIFIED` or `ERROR` and make aggregate status non-PASS.
