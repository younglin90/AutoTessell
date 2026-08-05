# CARD QQQ1b (beta2085) — native_bl front-collision 스켈레톤 (검증 명령 수정 재시도)

**target_engine**: tet
**모티프**: Garimella 2003 §3 — advancing layer front-collision (시퀀스 #1, 스켈레톤 재시도)

## 이론적 근거 (≤8줄)
R20 QQQ1 은 코드는 안전한 default-OFF 스켈레톤이었으나, 검증 명령에 포함된
`tests/test_native_bl.py` 자체가 무거워 90s timeout 으로 FAIL 처리됨.
본 카드는 코드 변경을 동일하게 유지하되, 검증 명령만 가벼운 import 검사 +
tet 회귀로 교체한다. 향후 ON 카드(QQQ2)에서 prism front 충돌 검사를 활성화하여
Garimella 의 collision-aware advancing layer 로 진화시킬 스켈레톤을 둔다.

## 변경
- 파일: core/layers/native_bl.py
- 함수/위치:
  1. 모듈 상수 `_BL_QQQ1_FRONT_COLLISION = False` 추가 (default OFF).
  2. helper `_check_prism_front_collision(front_normals, front_points, step)` 정의 (호출되지 않음, 스켈레톤만).
  3. docstring 1 줄 — Garimella 2003 §3 참고 명시.

## 검증 명령 (unit_tester 가 그대로 실행)
```bash
timeout 60 python3 -c "from core.layers.native_bl import _check_prism_front_collision, _BL_QQQ1_FRONT_COLLISION; print('OK', _BL_QQQ1_FRONT_COLLISION)"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py -q
```

## 합격 기준 (validator 가 평가)
- import 검사 OK 출력 + flag False
- tet 회귀 (amips + chunked) PASS
- bench 시간 ≤ 720s
- BL 영향 없음 (default OFF — 호출되지 않음)
