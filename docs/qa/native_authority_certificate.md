# Actual source/output authority evidence

`core/evaluator/actual_source_output_certificate.py` is the measured producer
for surface authority evidence. It reads the source file bytes, recomputes the
source hash, validates exact output vertex coordinates and an explicit
output-face-to-source-face bijection, and compares caller-supplied feature,
patch, and physical-group labels. It also recomputes connected-component
bijection. Missing declarations, moved coordinates, non-bijective mappings,
or group mismatches reject the certificate.

The certificate is evidence only. It does not route a mesher or turn the
current native Tri clone route into an independent product. A release matrix
row must use its hashes together with the strict volume audit, surface
validity, positive boundary-layer, and repeatability evidence.

For the known native Poly small-target card, the bounded probe is:

```bash
PYTHONPATH=. python3 scripts/probe_native_poly_target_cells.py \
  tests/benchmarks/cube.stl --target 50 100 \
  --output-root /tmp/autotessell-poly-target-probe
```

The probe reports a truthful failure if generation does not finish; it never
converts a timeout or a source clone into a release pass.

The Poly boundary certificate `autotessell/native-poly-boundary-authority/v1` binds the raw source digest, strict written artifact digest, Gate4 surface topology, explicit source patch/group payloads, and the measured source-bound output patch. It is fail-closed when the caller omits feature or provenance measurements.
