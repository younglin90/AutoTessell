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
| R40 | UUU2 | tet | PASS | =0.0 | self-intersect detect 활성 (Hu 2018 §3.1 시퀀스 #2), flag=True + 1회 호출 @mesher line 196, log-only (cleanup 미적용), tet C/D stable, bench 57.0s, n_si=0 |
| R41 | UUU3 | tet | PASS | =0.0 | self-intersect repair candidates skeleton (Hu 2018 §3.1 시퀀스 #3), _si_repair_candidates helper + _UUU3_REPAIR_CANDIDATES=False, default OFF, tet C/D stable, bench 57.6s |
| R42 | UUU4 | tet | PASS | =0.0 | self-intersect repair candidates 활성 (Hu 2018 §3.1 시퀀스 #4), flag=True + 1회 호출 @mesher line 204, log-only (candidate 미적용), tet C/D stable, bench 57.4s, n_candidates=0 |
| R43 | WWW1 | hex | PASS | =0.0 | octree 2:1 balance skeleton (Marechal 2009 시퀀스 #1), _balance_octree_2to1_nodes helper + _WWW1_OCTREE_BALANCE=False (default OFF), hex A=5/5 stable, bench 58.3s |
| R44 | UUU5 | tet | PASS | =0.0 | face split helper skeleton (Hu 2018 §3.1 시퀀스 #5), _apply_face_split + _UUU5_FACE_SPLIT=False (default OFF), tet C/D stable, bench 57.4s |
| R45 | WWW2 | hex | PASS | =0.0 | octree 2:1 balance 활성 (Marechal 2009 시퀀스 #2), _WWW1_OCTREE_BALANCE=True + node helper 26-이웃 재통과, hex A=5/5 stable, bench 57.5s |
| R46 | TTT6 | poly | PASS | =0.0 | BL thickness_factor skeleton (Loseille 2013 시퀀스 #6), default 1.0 (default OFF), poly A=5/5 stable, bench 58.6s |
| R48 | TTT7c | poly | PASS | -0.6s | BL step ×0.95 보수 축소 (stitch margin), poly A=5/5 stable, bench 58.0s, prism 156~1584 |
| R49 | UUU6 | tet | PASS | =0.0 | face split helper 활성 (Hu 2018 §3.1 시퀀스 #6), _UUU5_FACE_SPLIT=True + max_split=20 guard, tet C/D stable, bench 58.0s (no-op, n_si=0) |
| R50 | WWW3 | hex | PASS | =0.0 | surface refine skeleton (snappy castellated 시퀀스 #3), default OFF, hex A=5/5 stable, bench 58.3s |
| R51 | WWW4 | hex | PASS | =0.0 | surface refine 활성 (snappy castellated 시퀀스 #4), _WWW3_SURFACE_REFINE=True + double-balance, hex A=5/5 stable, bench 58.4s (stable), no cell increase |
| R52   | WWW5  | hex    | PASS    | =0.0  | octree cell templating skeleton (Marechal 2009 §4 시퀀스 #5), default OFF, bench 58.2s, hex grade A=5 stable |
| R54   | UUU7  | tet    | PASS    | =0.0  | face split Laplacian cleanup (Hu 2018 §3.1 시퀀스 #7), 1-pass smoothing + envelope guard, tet C/D stable, bench 57.4s |
| R55   | WWW6  | hex    | PASS    | =0.0  | octree templating 활성 (Marechal 2009 시퀀스 #6), _WWW5_TEMPLATING=True + type 식별 log only, hex A=5/5 stable, bench 59.1s |
| R56   | VVV1  | tet    | PASS    | =0.0  | Stellar 4-op queue skeleton (Klingner 2008 §3 시퀀스 #1), default OFF, tet C/D stable, bench 57.9s |
| R57   | VVV2  | tet    | PASS    | =0.0  | Stellar queue 활성 (Klingner 2008 §3 시퀀스 #2, log only), _VVV1_STELLAR_QUEUE=True, _build_op_queue 1 호출, tet C/D stable, bench 57.9s |
| R58   | TTT9  | poly   | PASS    | =0.0  | polyDualMesh cell merge skeleton (시퀀스 #9), _TTT9_CELL_MERGE=False default OFF, poly A=5/5 stable, bench 59.4s |
| R59   | VVV3b | tet    | PASS    | =0.0  | Stellar swap-only apply (32+44 worst-first), triple monotone guard, Klingner 2008 §3.2 시퀀스 #3, n_app=34 (fid=100030), accepted=True, tet C/D stable, bench 59.3s |
| R60 | VVV4 | tet | FAIL | timeout | local cavity Steiner insert hang (>90s pytest), no time cap / top-K limit, reverted |
| R61 | VVV4b | tet | FAIL | timeout | top-K + 0.2s budget still hung pytest >90s — guard not effective on test mesh size, reverted |
| R62 | VVV5 | tet | FAIL | -0.027 | flip_edges_54 (Klingner Table 1, 5→4 ring removal), n_app=424, worst_mq 0.082→0.055 (threshold: ≥0.067), regressed |

# AVOID (3 회 reject)
- flip_edges_54 default-ON, post-VVV3b call without per-flip min_q strict guard (VVV5 — worst 0.082→0.055). 재시도 시 per-flip post.min ≥ pre.min_q 강제.
- Steiner cavity insertion (VVV4 / VVV4b) — scipy Delaunay rebuild can not be wall-time bounded inside call. 신규 Steiner 카드 금지 until non-Delaunay 구현.
| R63 | PPP9 | poly | FAIL | regression | n_lloyd default 2→4 broke test_native_poly_lloyd_signature_accepts_n_lloyd, also param sweep violation. continuous score 부분만 유지하려면 별도 카드. 전체 reverted |
| R64 | PPP9b | poly | FAIL* | -0.027 | continuous tie-break score (Yu 2014 §4), chosen=voronoi=6 success, BUT validator reverted on tet worst_mq 0.082→0.055 — likely false-FAIL: card cannot affect tet (only voronoi.py touched), baseline fid confusion |

# VALIDATOR-FIX REQUIRED
- worst_mq baseline must be per-fid (not global min). 0.082 was fid=100030, 0.055 was fid=100040 — different test cases. Comparing post.fid=100040 worst vs pre.fid=100030 worst yields false regression. R65 planner must instruct validator to pin baseline by fid.
| R65 | PPP9b-redo | poly | PASS | n/a | re-applied PPP9b after R64 false-FAIL (per-fid baseline confusion), continuous score tiebreak, chosen=voronoi_clipped=3, bench 59.2s |
| R66 | VVV5b | tet | PASS | n_flip54=12+76+53+79=220 across fids | flip_edges_54 strict per-flip guard (Klingner 5-4), fid=100027 mq=0.082, fid=100030 mq=0.095, fid=100040 mq=0.055, bench 66.3s, BL fail=0, commit f56fe0f |
| R77 | WWW7 | hex | PASS | n/a | feature edge snap (nFeatureSnapIter style), dihedral>30° segs, top_k=200, quality guard per-cell, hex A=5/5 stable, BL fail=0, bench 70.5s |
| R116 | TET_TIMING2 | tet | OBS | n/a | post-PERF3/4 timing snapshot: top-3 = VVV13=7496ms, VVV12=5009ms, VVV10=3432ms (sum across 10 runs, bench 85.7s, 22/22 PASS) |
| R132 | TET_TIMING3 | tet | OBS | n/a | post-perf-chain timing: top-3 = VVV13=7276ms, VVV12=4396ms, VVV3b=3152ms, total bench 82.0s |
| R181 | BETA2246_VVV9B_OFFPLANE_STEINER | tet | PASS | =0.0 | Klingner coplanar Steiner skeleton: SVD off-plane helper (default OFF). zero behavior change, regression 35/35 PASS, bench 59.1s, commit 5c44137 |
| R182 | BETA2247_VVV9C_OFFPLANE_DIAG | tet | PASS | =0.0 | diagnostic hook for off-plane sliver candidates (log-only, gate OFF). VVV12 try-block: call _count_offplane_sliver_candidates after _n_sliver_pre, append n_offplane_candidates + flatness_thresh to sliver_split log. zero behavior change, regression 35/35 PASS, bench 564.6s, worst_mq 0.2068, BL_OK 20/20, commit 4a83fc9 |
| R184 | BETA2249_VVV9D_OFFPLANE_DRYRUN_WIRE | tet | PASS | =0.0 | dry-run wire for off-plane Steiner evidence collection (gate=False, caller discard). mesher.py:2908-2929 + stellar.py:1005-1115, mesh state truly unchanged, regression 35/35 PASS, bench 563.1s, worst_mq 0.2069, BL_OK 20/20, commit 9e4e8fb |
| R185 | BETA2250_VVV9E_DRYRUN_ON | tet | PASS | =0.0 | gate flip True (mesher.py:2909), evidence log emit native_tet_vvv9d_dryrun per-fid (n_offplane_candidates, n_inserted_dr, wall_ms), mesh unchanged (helper discard), regression 35/35 PASS (exact match R184), bench ≤580s estimated, worst_mq 0.2069 ±0.005, BL_OK 20/20, commit PENDING |
| R188 | BETA2253_VVV9F3_PERTURB_TOPK_HELPER | tet | PASS | =0.0 | weight matrix sampling (Cheng-Dey 1999 §4 Algo 4.1 step 1), _perturb_weights_topK(n_samples, alpha) → W[K,N] (K candidates), skeleton helper, no caller, mesh unchanged, regression 35/35 PASS, bench 580.0s, worst_mq 0.2069, BL_OK 20/20, commit dc1fdf7 |
| R189 | BETA2254_VVV9F4_SELECT_BEST | tet | PASS | =0.0 | best-of-K weight argmax (Cheng-Dey 1999 §4 Algo 4.1 step 2), _select_best_weight_assignment(pts, tets, weight_matrix, alpha) → (best_idx, best_min_q), skeleton helper, no caller, mesh unchanged, regression 31/31 PASS, bench ~580s, worst_mq 0.2069, BL_OK 20/20, commit 62d0a3a |
| R190 | BETA2256_VVV9F6_DRYRUN_ON | tet | PASS | =0.0 | gate flip True (mesher.py dryrun_on + sliver-gated evidence emit native_tet_vvv9f_dryrun per-fid), mesh unchanged (evidence-only), regression 35/35 PASS, bench ~580s, worst_mq 0.2069 ±0.005, BL_OK 20/20, commit 66bc2e0 |
| R192 | BETA2257_VVV9H1_KLINGNER_EDGE_CONTRACT_CANDIDATES | tet | PASS | =0.0 | Klingner 2008 §4.1 edge contraction skeleton: _klingner_edge_contract_candidates(pts, tets, q_max, l_max_factor, max_candidates) → list[tuple[int,int,float]] (candidate enumeration only, no apply/caller/default OFF), regression 35/35 PASS, bench 59.1s, worst_mq 0.2069 ±0.005, BL_OK 5/5, commit PENDING |
| R193 | BETA2258_VVV9H2_DIAG_HOOK | tet | PASS | =0.0 | diagnostic hook in VVV12 (gate OFF, log only). mesher.py:2954-2976, _klingner_edge_contract_candidates helper + sliver-pre guard, log emit native_tet_vvv9h_diag per-fid (n_candidates, n_safe, n_quality_improving), mesh unchanged (evidence discard), regression 35/35 PASS, bench 59.1s, worst_mq 0.2069 ±0.005, BL_OK 5/5, commit 8a2f3e5 |
| R194 | BETA2259_VVV9H3_DIAG_ON | tet | PASS | =0.0 | gate flip True (mesher.py:2955 _VVV9H_DIAG=False→True), evidence collection enabled (sliver-pre gated). log emit native_tet_vvv9h_diag per-fid, mesh unchanged (helper discard), regression 35/35 PASS, bench 61.78s, worst_mq 0.2069 ±0.005 (stable), BL_OK 5/5, commit PENDING |
| R197 | BETA2262_VVV9H6_APPLY_DRYRUN_ON | tet | PASS | =0.0 | gate flip True (mesher.py:2980 _VVV9H_APPLY_DRYRUN=False→True), evidence log emit native_tet_vvv9h_apply per-fid (n_apply_accepted, pre/post_min_q_star), mesh unchanged (helper discard), regression 35/35 PASS, bench 59.1s, worst_mq 0.208 ±0.005, BL_OK 5/5, commit 1b70852 |
| R198 | BETA2263_VVV9H7_APPLY_HARDEN_AFFECTED | tet | PASS | =0.0 | Klingner §4.1 helper hardening: star-local quality measure (pre_mask/post_mask, O(deg) not O(T)), strict neg-vol equality guard (post_n_neg≠pre_n_neg rejected), stats extended (pre_min_q_star, post_min_q_star), caller mesher.py unchanged, mesh unchanged (evidence-only dryrun), regression 35/35 PASS, bench 59.1s (stable, -0.5s expected from star recompute), worst_mq 0.208 ±0.005 (stable), BL_OK 5/5, commit PENDING |
| R200 | BETA2265_VVV9I1_ENVELOPE_PROJECT_HELPER | tet | PASS | =0.0 | fTetWild §3 envelope point projection helper, _envelope_point_projection(pts, envelope_pts, eps, lock_ids=None) → dry-run dict (n_violated, n_snapped, max_d, applied=False), skeleton-only (no caller, default OFF), envelope-bounded point snap with KDTree query, regression 31/31 PASS (67s), worst_mq 0.208±0.005 maintained, BL_OK 5/5, commit PENDING |
