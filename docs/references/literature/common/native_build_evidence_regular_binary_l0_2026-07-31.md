# Native build evidence regular-binary guard — L0

## Gap

The build-evidence scanner previously resolved extension paths before recording
them.  A symlink named like a native module inside a build directory could
therefore be accepted as an ordinary build artifact, even when its target lived
outside that directory.  Its hash and ABI could still look valid, but the
clean-build provenance chain would be weaker than the release gate requires.

## Correction

`find_binary()` now preserves the candidate path and rejects symbolic-link
extension binaries before ABI import or manifest generation.  A focused test
creates a link to an outside binary and requires the exact fail-closed error.

## Scope

This is release-evidence hardening only: no C++ source, native algorithm,
Python route/default, mesh output, or third-party dependency changes.  Regular
CMake-produced extension files retain the same manifest and ABI workflow.
