# Attempts Catalog

| Round | CARD | Engine | Verdict | Δmq | 사유/요약 |
|-------|------|--------|---------|-----|----------|
| (R0)  | DDD1 | tet    | PASS    | n/a | BSP triangle insertion (beta2040) — pre-harness |
| (R0)  | EEE1 | tet    | PASS    | n/a | BSP 후 flip post (beta2050) — pre-harness |
| (R0)  | FFF1 | tet    | PASS    | n/a | BSP 한계 확장 (beta2060) — pre-harness |
| R1    | HHH1 | tet    | FAIL    | -0.021 | AMIPS multistage worst mq 악화 (0.076→0.055) |
| R2    | III1 | tet    | FAIL    | skip   | Parameter mismatch: lock_surface vs locked_vertex_ids |
| R3    | JJJ1 | tet    | FAIL    | -0.021 | Single-stage α=1.0 worst still 0.076→0.055, best 0.236→0.208 |
| R4    | KKK1 | tet    | PASS    | =0.0   | Flip-only post-BSP cycle, mq stable 0.076, tet grade C/D stable |

# AVOID (3회 reject 됨)
- smooth_amips_analytic / smooth_amips_multistage 호출 BSP 직후 (HHH1/III1/JJJ1 — worst-mq 악화 패턴). 동일 함수/위치 재시도 금지.
