# CARD RRR3 (beta2091) — targeted AMIPS 임계+iter 강화

**target_engine**: tet
**모티프**: Klingner 2008 §3.5 — targeted AMIPS 강화 (시퀀스 #3)

## 이론적 근거
- RRR2 의 p5<0.05 single-pass stable PASS. 더 많은 worst tet 포착 + iter 증가로 mean 향상 여지.
- 임계 q<0.05 → q<0.10: worst tet pool 확장 (sliver 외곽 포함).
- n_iter 1 → 2: AMIPS gradient descent 두 번 (Klingner 2008 표준).
- 단조 가드 (post_min>=pre_min, post_mean>=pre_mean) 그대로 — 회귀 방지.
- novelty 1, rigor 2, impact 2 → 합 5.

## 변경
- 파일: core/generator/native_tet/mesher.py
- 위치: RRR2 블록 (line 2171–2226)
- 핵심 변경:
  1. line 2183: `if p5 >= 0.05:` → `if p5 >= 0.10:`
  2. line 2184: skip log `reason="p5>=0.05"` → `reason="p5>=0.10"`
  3. line 2186: `worst_mask = q_per_tet < 0.05` → `worst_mask = q_per_tet < 0.10`
  4. line 2205: `n_iter=1,` → `n_iter=2,`
  5. log 추가: `q_thresh=0.10, n_iter=2` 명시 (관측용).

## 검증 명령
```bash
timeout 120 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s (현 59.4s 대비 충분 여유)
- tet worst_mq ≥ 0.077 (현 0.082, 단조 가드 보장)
- tet mean_mq 단조 (RRR2 대비 동등 또는 향상)
- BL 합격 분포 동등
