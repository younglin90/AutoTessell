---
description: Hard-won guardrails from past bugs — read before touching workers, Windows I/O, or fallback logic
paths: ["**"]
---

## Guardrails

- **pytetwild / fTetWild segfault in fork-spawned worker pools** — isolate the call in
  a subprocess. Bench scripts force it **OFF** at worker entry; main / CLI / GUI keep it
  **ON** (the crash only happens under fork, not in the main process).
- **Windows console is cp949** and cannot encode em-dash (—), degree (°), or middle dot
  (·) — reconfigure `stdout`/`stderr` to UTF-8 at process start, and pass
  `encoding="utf-8"` to every `Path.write_text` / `read_text` so file I/O never inherits
  cp949.
- **UNC paths (`\\wsl.localhost\…`) break `npm install` and electron-builder** because
  cmd.exe rejects a UNC current directory — map a drive letter or use a local clone. The
  *running* Electron app tolerates UNC: it spawns Python with `shell:false`,
  `cwd=%TEMP%`, and `PYTHONPATH=<repo>`, so no cmd.exe UNC-cwd is involved.
- **WildMesh / flow default**: a single closed genus-0 surface defaults to **internal**
  flow (bbox domain), not external — don't assume a lone watertight body means a wind
  tunnel.
- **`mesh_type` is a preference, not an absolute contract** — cross-family fallback is
  allowed as a last resort so that garbage input still yields *some* volume mesh.
- **`generate_native_tet` called twice in one pytest process on a heavy mesh (10k+
  cells) can crash the interpreter** with a non-deterministic Windows access violation
  — a different native stack trace each run (seen in both `aabb.py` and
  `mean_curvature.py`), the signature of native-heap corruption, not a Python logic
  bug. It did not reproduce in a bare `python -c` script calling the function twice —
  looks specific to pytest's process/threading setup. Root cause not found; the
  practical fix is a module-scoped fixture so a test file only calls it once and shares
  the result across assertions (see `tests/test_native_tet_dual_torus_limit.py`).
- **Windows Bash-tool `python3` and WSL `python3` are different interpreters with
  different installed packages** — `igl`/`pyacvd` (used by L2 remesh) exist in the WSL
  venv but not the Windows one. A test that silently no-ops or takes a fallback path
  under Windows may be exercising a completely different code path than production.
  When a card touches `igl`/`pyacvd`/other WSL-only deps, verify via `wsl.exe -d ubuntu`
  or note explicitly which environment was used.
