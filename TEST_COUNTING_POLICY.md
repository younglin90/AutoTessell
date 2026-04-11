# AutoTessell Test Counting Policy

Date: 2026-04-08

## Rule

Do not hardcode total test counts in docs or comments.

Reason:

- The count changes frequently.
- Stale numbers create false confidence and doc drift.

## Allowed Wording

- "테스트 스위트 운영"
- "단위/통합/벤치마크 테스트 포함"
- "Run tests with pytest"

## Disallowed Wording

- Fixed totals such as `331+`, `458+`, `621 tests`, `89 tests`.

## Canonical Reporting Method

When a concrete number is needed, compute it at report time from CI or direct command output.

Recommended local command:

- `make test-count`
