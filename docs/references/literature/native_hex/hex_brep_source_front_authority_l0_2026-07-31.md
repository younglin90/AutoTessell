# Hex B-Rep source-front authority L0 (2026-07-31)

## Scope

`CORRECTNESS_KEEP`, default off.  The disconnected adapter validates only an
already-read immutable `CadNativeTriangulation`; it does not read CAD bytes,
invoke OCP, build a candidate, alter a mesh, or emit an artifact.

## Contract

`AUTO_TESSELL_HEX_BREP_SOURCE_FRONT_AUTHORITY_L0=1` enables an explicit
`cad_brep` declaration.  Unknown or malformed declaration authority is
rejected before the triangulation payload is accessed.  The payload requires
read-only canonical arrays, complete face-ordinal coverage, exact orientation
and seam reconstruction, exact reader hashes, all B-Rep authority flags, and
physical groups exactly unavailable (`False` plus all `None`).

Every result remains non-accepting.  Source byte-to-reader-payload binding,
generated Hex boundary-to-B-Rep binding, and physical groups remain missing.
