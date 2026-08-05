# Repository structure

AutoTessell keeps the importable Python packages at the repository root because the
current wheel, CLI entry points, and native extension build already depend on those
stable package names. Supporting products and non-runtime material are grouped by
role below.

```text
AutoTessell/
├── auto_tessell_core/        C++23/pybind11 native build and first-party kernels
├── core/                     Python orchestration, engines, layers, evaluator
├── cli/                      auto-tessell command entry point
├── desktop/                  Qt application and local web API
├── products/web/
│   ├── api/                  optional SaaS API/worker product
│   ├── app/                  optional SaaS web application
│   └── reference-ui/         legacy/reference Next.js UI used by start_gui.sh
├── engines/legacy/
│   └── tessell_mesh/         legacy Tier0 C++ extension and fallback route
├── research/
│   └── quality-harness/      meshing experiments, plans, probes, and mutable evidence
├── vendor/
│   ├── dependencies/         vendored build dependencies (fTetWild, cfMesh)
│   └── reference/            local reference implementations and research checkouts
├── assets/models/            optional ML models and training datasets
├── tests/                    automated tests and benchmark fixtures
├── scripts/                  repeatable developer/release tooling
├── docs/                     plans, contracts, research, QA, and user documentation
└── installer/                Windows/Linux packaging material
```

## Naming rules

- Runtime Python package names remain stable until a package migration is planned;
  `core`, `cli`, and `desktop` are intentional product boundaries, not temporary
  scratch directories.
- `products/` contains deployable but optional web tracks and is excluded from the
  native wheel.
- `research/` is not a runtime dependency and may contain mutable experiment output.
- `engines/legacy/` identifies fallback implementations that are not part of the
  native-first release route.
- `vendor/` contains code owned by other projects or kept only for comparison.
- Build caches, virtual environments, and generated run output stay ignored in place;
  they are not source structure and must not be committed.

## Compatibility notes

`pyproject.toml` still packages `cli`, `core`, and `desktop`, while CMake still uses
`auto_tessell_core` as its source directory. The moved auxiliary paths are reflected
in launcher scripts, CMake options, package metadata, documentation, and release
exclusions. The legacy `tessell_mesh` route remains available until Tier0 is formally
retired; it is grouped under `engines/legacy/` to make that status explicit.
