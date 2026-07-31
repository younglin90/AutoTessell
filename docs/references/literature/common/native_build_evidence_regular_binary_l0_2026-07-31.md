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

## Clean-install replay

Release staging uses the dedicated fail-closed command after `cmake --install`:

```bash
python scripts/native_build_evidence.py verify-install \
  --source-root . \
  --stage-root /absolute/stage/prefix
```

It requires a regular staging directory plus regular installed manifest and
contract files.  It then runs the full eight-module ABI, hash, source identity,
and non-symlink binary verification against that installed prefix.
