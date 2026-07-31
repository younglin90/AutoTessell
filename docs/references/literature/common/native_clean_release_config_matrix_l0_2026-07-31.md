# Native clean Release configuration matrix — L0

The current evidence covers one declared configuration row only. It does not
claim Windows, macOS, alternate compilers, Debug, or multi-config support.

| Key | Required evidence value |
| --- | --- |
| OS | CMake `CMAKE_SYSTEM_NAME`, non-empty, recorded only |
| compiler | CMake ID and version, non-empty |
| language | C++23 |
| build type | `Release` |
| install profile | `AUTOTESSELL_INSTALL_FIRST_PARTY_NATIVE=ON` |
| external adapters | cfMesh, cinolib, fTetWild, RobustHex: all `OFF` |

`native_build_evidence.py` writes this canonical configuration into the build
manifest. Verification rejects missing keys, any non-Release build, a disabled
install profile, or any enabled external adapter. The actual OS is recorded as
evidence, not presented as a portability guarantee.
