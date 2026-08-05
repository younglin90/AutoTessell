# Native extension explicit-build precedence — Cycle 36

## Card

- ID: `COMMON-NATIVE-LOADER-PRIORITY-CYCLE36`
- State before implementation: `MEASURED`
- Promotion target: `L1_PASS / CORRECTNESS_KEEP`
- Scope: first-party Python loaders only; no native kernel, routing, mesh, or gate change

## Baseline defect

Several first-party loaders prepend build directories and then call
`importlib.import_module`.  This is insufficient when an older module with the
same name is already cached in `sys.modules`.  It can also leave the repository
build ahead of `AUTOTESSELL_EXT_BUILD_DIR` when both paths are already present.
The result is a stale ABI being used during fresh-build verification.

`native_snap` already has an explicit path-stable load for this case.  Other
loaders independently repeat weaker search-path logic.

## Hypothesis

A single first-party import primitive can make an explicit build candidate win
over both `sys.path` order and a stale module-name cache.  Loading an explicit
candidate through a path-derived package alias preserves the extension's final
module component while avoiding the stale top-level cache.

## Frozen acceptance

1. A cached repository fixture exposing ABI marker `1` must not mask an explicit
   fixture exposing marker `2`; the loader must return marker `2` and the exact
   explicit file path.
2. An explicit candidate that raises during import must not fall through to the
   cached repository fixture.
3. An explicit directory without the requested module retains the existing
   repository/PYTHONPATH fallback behavior.
4. Optional loaders keep returning `None` on unavailable or invalid native
   modules.  Mandatory surface padding keeps raising its existing `RuntimeError`.
5. Existing native loader, evaluator, hex, tet, writer, and reader focused tests
   pass.  Ruff, strict mypy for changed files, and `git diff --check` pass.
6. No change under `vendor/dependencies/`; no mesh output, routing, threshold, or native
   ABI contract changes.

## Rollback

Any stale-ABI selection, fallback semantic change, exception-contract change,
or focused regression kills the card.  Acceptance thresholds will not be
relaxed after measurement.

## Provenance

Implementation is an independent standard-library design using Python's public
`importlib` machinery.  No external source code or dependency is used.

## Result

- State: `L1_PASS / CORRECTNESS_KEEP`
- Central primitive: `core/utils/native_extensions.py::import_native_extension`
- Migrated duplicate loaders: evaluator metrics, hex quality, tet flip metrics,
  tet QOPT, polyMesh writer, polyMesh reader, mandatory surface padding.
- `native_snap` retained its existing equivalent exact-path implementation.
- Subprocess fixtures: stale ABI marker `1` / explicit marker `2` selected `2`;
  broken explicit candidate did not fall through; absent candidate retained the
  cached fallback; optional broken candidate returned `None`.
- Real binary cache test: all eight first-party modules were first imported
  from the repository build, then loaded from the fresh explicit directory.
  Every returned module path was the explicit directory and every module object
  differed from the stale object.
- Fresh build: GCC 13.3, C++23, Release, warnings-as-errors, first-party-only;
  eight modules built successfully.  No optional adapter or third-party source
  was configured.
- Focused regression: `174 passed, 1 deselected` using the fresh explicit build.
  The one deselected writer assertion also fails unchanged on `master`: the
  parser now returns the already-supported boundary `type` field.  It is not a
  loader regression.
- Loader regression: `5 passed`.
- Black, Ruff, and strict mypy: central primitive and new regression tests pass.
  Migrated legacy modules retain their pre-existing project-wide strict-mypy
  debt; the import-only changes add no new typed interface.
- `git diff --check`: pass.
- Mesh output, routing, acceptance thresholds, native ABI, and `vendor/dependencies/`:
  unchanged.
