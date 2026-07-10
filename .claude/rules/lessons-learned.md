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
