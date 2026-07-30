# First-party native wheel distribution profile

This distribution profile builds AutoTessell's eight independent native
pybind11 modules and the Python application. The resulting wheel remains
licensed under `GPL-3.0-or-later`; this profile is not a license change.

Included native modules:

- `native_metrics`
- `native_bl`
- `native_polymesh`
- `native_snap`
- `native_surface_padding`
- `native_hex_quality`
- `native_tet_predicates`
- `native_tet_qopt`

`native_tet_predicates` compiles the project-local public-domain Shewchuk
predicate source and uses Boost.Multiprecision headers under the Boost Software
License 1.0. Boost is a build-only header dependency; it is not vendored and no
Boost runtime library is linked into the wheel. The other seven modules depend
only on pybind11, Python, and the C++ standard library.

The wheel profile forcibly disables `cinolib_hex`, `robusthex`, `ftetwild`,
and `cfmesh_native`. It does not compile, link, package, or modify their source
trees. Those optional adapters remain outside the future MIT-core candidate
boundary.

Every binary wheel must be published with the same-version source archive.
That source archive is the corresponding-source offer for the GPL wheel and
contains the Python sources, eight binding sources, predicate source, CMake
configuration, `LICENSE`, `NOTICE`, and licensing manifests needed to rebuild
the wheel. Release evidence must record both artifact hashes.

The package `NOTICE` describes optional source-tree integrations as well as
distributed components. For this profile, the exclusions above are
authoritative: optional adapter notices do not mean those adapters are present
in the wheel.

This profile does not make the project-wide license gate pass. Gate 13 remains
`UNVERIFIED` while the distribution dependency inventory contains unresolved
license assertions. Version unification, release-workflow publication, and the
legacy Windows installer are separate release blockers outside this build card.
