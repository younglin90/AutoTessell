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
| R17   | PPP4 | poly  | PASS    | =0.0  | Surface clipping skeleton (Yan & Wonka 2014 시퀀스 #1, Sutherland-Hodgman variant), default OFF, poly A=5/5, bench 57.6s |
| R18   | PPP5 | poly  | PASS    | =0.0  | Surface clipping ON (Yan & Wonka 2014 시퀀스 #2), voronoi_clipped chosen 4x, poly A=5/5, bench 58.7s |
| R19   | PPP6 | poly  | PASS    | =0.0  | Clipping max_cells 50→200 + degenerate guard, voronoi_clipped chosen 3x, poly A=5/5, bench 59.1s |
| R21   | QQQ1b | tet   | PASS    | =0.0  | BL prism collision skeleton (Garimella 2003 §3), default OFF, bench 59.2s, tet grade C/D stable |
| R24   | QQQ3  | tet   | PASS    | =0.0  | BL collision vectorize (Garimella 2003 시퀀스 #2), np.einsum + max_pairs=200 guard, bench 58.8s (-0.4s), tet C/D stable, prism collision efficient |
| R25   | QQQ4  | tet   | PASS    | =0.0  | BL local thickness skeleton (Loseille 2013 시퀀스 #3), default OFF, _local_thickness_factor helper, bench 58.8s (stable), tet C/D stable |
| R27   | RRR1  | tet   | PASS    | =0.0  | Quality percentiles skeleton (Klingner 2008 시퀀스 #1), _quality_percentiles helper, default OFF, bench 59.4s (stable), tet C/D stable |
| R28   | RRR2  | tet   | PASS    | =0.0  | Worst-percentile targeted AMIPS (Klingner 2008 시퀀스 #2), p5 < 0.05 시 interior lock + smooth_amips_analytic(n_iter=1, α=1.0), tet worst 0.082 stable, bench 59.4s (stable) |
| R29   | RRR3  | tet   | PASS    | =0.0  | Targeted AMIPS 임계+iter 강화 (Klingner 2008 시퀀스 #3), q<0.10 → q<0.05 (worst pool 확장) + n_iter 1→2, tet worst 0.082 stable, bench 58.8s (-0.6s) |
| R30   | SSS1  | tet   | PASS    | =0.0  | Envelope-bounded relocation skeleton (fTetWild §3.5 시퀀스 #1), default OFF, worst 0.127 stable, bench 59.2s (stable) |

# AVOID (4회 reject 됨)
- smooth_amips_analytic / smooth_amips_multistage 호출 BSP 직후 (HHH1/III1/JJJ1 — worst-mq 악화 패턴). 동일 함수/위치 재시도 금지.
- collapse_short_edges KKK1 flip 후 (LLL1 — 동일 worst-mq 악화 패턴 0.076→0.055). vertex relocation collapse 금지.
| R31   | SSS2  | tet   | FAIL    | -0.027 | Envelope-bounded relocation (fTetWild §3.5 시퀀스 #2), worst mq 0.082→0.055 (n_relocated=792, revert 2회), gate 강화 필요 |
| R32 | SSS3 | tet | FAIL | -0.027 | worst mq destabilized, need stronger guard or skip envelope relocation |
| R33 | TTT1 | poly | PASS | =0.0 | BL wall-adjacent helper skeleton (Garimella 2003 시퀀스 #1), default OFF, poly A=5/5, bench 59.7s (stable) |
| R35 | TTT2b | poly | PASS | =0.0 | BL wall-adjacent helper 호출 활성 (시그니처 일관 재시도 #1), _find_wall_adjacent_cells(3 arg) 정확 호출, poly A=5/5, bench 59.1s (stable), n_wall_adj 255~778 |
| R36 | TTT3 | poly | PASS | =0.0 | BL extrude prism helper skeleton (Garimella 2003 시퀀스 #3), default OFF, poly A=5/5, bench 58.7s (-0.4s), prism extrude BL 구조 준비 |
| R37 | TTT4 | poly | PASS | =0.0 | BL extrude prism 활성 (Garimella 2003 시퀀스 #4), flag=True + SVD outward normal 계산, poly A=5/5, bench 58.1s (-0.6s), n_prism_added 2~6/fid, total 35 prisms extruded |
| R38 | TTT5 | poly | PASS | =0.0 | BL extrude max_extrude 20→100 (Garimella 2003 시퀀스 #5), coverage 확장, poly A=5/5, bench 57.3s (-0.8s), n_prism_added total 234 |
| R39 | UUU1 | tet | PASS | =0.0 | self-intersect detect skeleton (Hu 2018 §3.1 시퀀스 #1), default OFF, tet C/D stable, bench 57.6s |
