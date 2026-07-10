---
description: Python coding conventions and error-handling policy for Auto-Tessell
paths: ["**/*.py"]
---

## Coding Style

- Formatting & typing: **black + ruff + mypy strict**. All three must pass.
- Logging: **structlog** with JSON output — no bare `print` in library code.
- Agent-to-agent I/O: **Pydantic models**, JSON-schema validated at the boundary.
- Library policy (native-first): external mesh libraries are **reference-only**.
  **Any new external dependency requires a written "reference → self-implementation
  plan"** before it is added.

## Error Handling

- On a tier failure, **reset that tier's `work_dir`** and try the **next tier** —
  never abort the whole pipeline on a single tier's failure.
- A tier's internal exception is **caught and returned as a failed `TierAttempt`**,
  not propagated up to kill the pipeline.
- **No automatic Generator↔Evaluator retry loop.** On FAIL, the Evaluator prints its
  recommendation and prompts the user (`y/N`); the user decides whether to retry.
