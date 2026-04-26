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
| R5    | LLL1 | tet    | FAIL    | -0.021 | Sliver collapse worst-mq 0.076→0.055 (fid=100040), violates ≥0.071 guard |
| R6    | MMM1 | tet    | PASS    | +0.001 | Flip cycle 2회 반복 (Joe 1995), tet worst=0.076 stable, best 0.236→0.237 |
| R7    | NNN1 | tet    | FAIL    | -     | Missing `import os` in mesher.py line 1964 (dry-run skeleton bug) |
| R8    | NNN1b | tet   | FAIL    | skip  | silent except: QualitySnapshot.q_per_tet 무 attribute (log 0건) |
| R9    | NNN1c | tet   | PASS    | =0.0  | Steiner dry-run read-only (n_sliver=681/2808/810), mq 0.055 stable |
| R10   | NNN2  | tet   | FAIL    | -     | QualitySnapshot dataclass subscript bug: ["min"] → .min_q 수정필요 |
| R11   | NNN2b | tet   | PASS    | =0.0  | Steiner insertion (n_inserted=200@fid=100040), tet worst 0.055 stable, Δmq=+0.007 best |
| R12   | NNN3 | tet   | PASS    | =0.0  | Steiner cycle 2 (n_inserted_iter2=200@fid=100040), tet worst 0.055 stable, mean +0.004 |
| R13   | NNN4 | tet   | PASS    | =0.0  | Steiner 후 interior AMIPS smoothing (n_iter=1, α=1.0), worst 0.055 stable, best +0.001 |
| R14   | PPP1 | poly  | PASS    | =0.0  | Lp CVT 스켈레톤 (lp_p=2.0 default), poly grade A=5/5, tet metric stable |
| R15   | PPP2 | poly  | PASS    | =0.0  | Lp weighted centroid + voronoi(p=4) best-of-N candidate, poly A=5/5, bench 57.4s |
| R16   | PPP3 | poly  | PASS    | =0.0  | Voronoi +0.5 bonus score, voronoi(p=4)>voronoi(p=2)>hex_fallback 우선순위, bench 57.8s, chosen 2회 |

# AVOID (4회 reject 됨)
- smooth_amips_analytic / smooth_amips_multistage 호출 BSP 직후 (HHH1/III1/JJJ1 — worst-mq 악화 패턴). 동일 함수/위치 재시도 금지.
- collapse_short_edges KKK1 flip 후 (LLL1 — 동일 worst-mq 악화 패턴 0.076→0.055). vertex relocation collapse 금지.
