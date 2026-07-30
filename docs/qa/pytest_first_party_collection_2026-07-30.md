# First-party pytest collection contract

## Card

`PYTEST-FIRST-PARTY-COLLECTION-1` makes a bare repository-root `pytest`
collection start from the project-owned `tests/` tree.

## Baseline

Before this card, `pytest --collect-only -q` recursively discovered root-level
trees. On the card baseline it reported 4,070 collected items, then failed on
`backend/tests` with `ImportPathMismatchError` because its `tests.conftest`
module name collided with the root `tests/conftest.py`.

`pytest tests --collect-only -q` was the intended first-party command and
collected 3,981 root tests without collection errors.

## Change and scope

The canonical root configuration is `pyproject.toml`. Its documented
`[tool.pytest.ini_options].testpaths = ["tests"]` setting makes a no-argument
root run use the same explicit first-party root.

No `--ignore`, `skip`, `xfail`, collection hook, source-code change, or
third-party edit was added. Direct commands that explicitly name another tree
retain pytest's normal explicit-path behavior; this contract only defines
bare-root collection. External/vendor/backend trees are therefore not counted
in this root first-party test command.

`tests/test_pytest_collection_config.py` verifies both the declared config and
the child-process contract: bare-root and explicit `tests` collection have
identical nodeids and counts, and every collected nodeid begins with `tests/`.
That equality proves the configuration does not omit a test reachable through
the explicit first-party root.

## Research and provenance

The official pytest configuration documentation states that no-argument
collection starts from `testpaths` when it is configured and documents
`[tool.pytest.ini_options]` in `pyproject.toml`:

- <https://docs.pytest.org/en/stable/reference/customize.html>
- <https://docs.pytest.org/en/latest/explanation/goodpractices.html>

Pytest is MIT licensed:

- <https://raw.githubusercontent.com/pytest-dev/pytest/main/LICENSE>

This card uses only the documented configuration option and standard-library
subprocess/TOML parsing. It copies no pytest implementation and adds no
dependency.
