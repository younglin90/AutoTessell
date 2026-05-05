# CARD RRR1 (beta2089) — quality histogram percentile helper (스켈레톤)

**target_engine**: tet
**모티프**: Klingner 2008 §3.5 — quality histogram-based smoothing (시퀀스 #1, 스켈레톤)

## 이론적 근거
- native_tet worst_mq=0.208 (fTetWild 0.20 수준) 도달했으나 grade C(2)/D(3) — best mq=0.237 도 C/D.
- grade 평가는 mean_non_ortho / mean_skew 등 평균 metric 의존. worst 만 개선해도 grade 도약 불가.
- 본 카드: tet quality 의 percentile (p50/p90/p95/p99) 계산 helper 추가, default OFF (스켈레톤).
- 다음 카드 RRR2: 상위 5% (p95↑) 만 targeted Klingner smoothing 으로 mean 분포 개선.
- novelty 1, rigor 2, impact 2 → 합 5.

## 변경
- 파일: core/generator/native_tet/quality.py
- 함수: `_quality_percentiles` (신규, 모듈 말미 추가)
- 핵심 변경:
  1. 모듈 상수 `_RRR1_QUALITY_HISTOGRAM = False` 추가 (default OFF).
  2. helper `_quality_percentiles(pts, tets) -> dict` 정의 — `{"shape_q":{"p50","p90","p95","p99"}, "aspect":{...}, "min_dihedral_deg":{...}}`.
  3. 기존 `snapshot()` 등 호출 경로에서 이 helper 를 호출하지 않음 (스켈레톤, RRR2 에서 활성).

## 검증 명령 (unit_tester 가 그대로 실행)
```bash
timeout 60 python3 -c "from core.generator.native_tet.quality import _quality_percentiles; print('OK')"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py -q
```

## 합격 기준 (validator 가 평가)
- 회귀 PASS (호출 경로 미연결, 동일 결과)
- bench 시간 ≤ 720s (기존 59s + 여유)
- helper import 성공 + 임의 (pts, tets) 입력 시 dict 반환 (스모크)
- BL 영향 없음 (스켈레톤)
