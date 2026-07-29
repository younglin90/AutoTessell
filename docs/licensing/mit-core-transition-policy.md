# MIT native-core transition policy

AutoTessell is currently distributed under GPL-3.0-or-later.  This note is a
development boundary for a future permissively licensed native core; it does
not change the current license or grant a relicensing right.

## Boundary

- Keep GPL components, including the cfMesh/OpenFOAM integration, outside a
  future MIT core.  They may remain optional adapters that are built, invoked,
  packaged, and documented separately.
- Keep AGPL components, including AlgoHex integrations, outside that core and
  do not copy their source, generated output, or implementation-derived code
  into native-core modules.
- New native C++ algorithms intended for the MIT core must be independently
  implemented, provenance-recorded, and free of GPL/AGPL implementation
  dependencies.  Papers and permissively licensed libraries may inform the
  design, but their license terms must be checked before reuse.
- Do not label a module MIT, publish a mixed package as MIT, or replace the
  repository license until a file-level provenance and dependency audit has
  verified the boundary.

## Practical workflow

For each candidate native engine, retain a small evidence record covering the
algorithm source, implementation author, direct dependencies, generated-code
inputs, and verification tests.  Route GPL/AGPL functionality through explicit
adapter interfaces so the future core can be built and tested without it.
