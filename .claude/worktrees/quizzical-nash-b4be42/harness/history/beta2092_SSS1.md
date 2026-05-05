# CARD SSS1 (beta2092) — envelope-bounded surface vertex relocation skeleton

**target_engine**: tet
**모티프**: fTetWild §3.5 — envelope-bounded surface vertex relocation (시퀀스 #1, 스켈레톤)

## 이론적 근거
- 현재 모든 surface vertex 가 lock — Hausdorff 보존되지만 boundary tet quality 향상 한계.
- envelope-bounded relocation: surface vertex 를 ε-envelope 안에서 tangential 자유 이동.
- normal 방향 이동은 envelope 위반 가능 → tangent 평면 projection 으로 제한.
- 이동 후보 → `envelope.contains_points` 로 검증 → True 채택, False revert.
- 본 카드(SSS1)는 **스켈레톤** — helper 정의 + 모듈 상수 OFF, 호출처 미연결.
- 다음 카드(SSS2)에서 mesher smoothing 단계에 wire 하고 활성화.
- novelty 3 (fTetWild envelope-bounded relocation 자체 구현) + rigor 3 (envelope contains 검증) + impact 3 (boundary mq 향상 잠재) → 합 9, paper-worthy.

## 변경
- 파일: core/generator/native_tet/envelope_relocate.py (신규 단일 파일)
- 핵심 변경:
  1. 모듈 상수 `_SSS1_ENVELOPE_RELOCATE = False` 정의.
  2. `_tangent_project(pt, normal, target)` — normal 성분 제거 후 tangent 이동량 계산.
  3. `_envelope_bounded_relocate(pts, surface_idx, target_pts, vertex_normals, envelope) -> np.ndarray` — surface vertex 마다 tangent projection 후보 생성, `envelope.contains_points` 검증, 통과 시 채택, 실패 시 원위치 유지. ≤80줄.

## 검증 명령 (unit_tester 가 그대로 실행)
```bash
timeout 60 python3 -c "from core.generator.native_tet.envelope_relocate import _envelope_bounded_relocate, _SSS1_ENVELOPE_RELOCATE; print('OK', _SSS1_ENVELOPE_RELOCATE)"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py -q
```

## 합격 기준 (validator 가 평가)
- import 및 회귀 PASS.
- bench 시간 ≤ 720s (skeleton 무영향).
- grade 분포 / worst_mq 동등 (호출처 미연결, OFF).
- BL 영향 없음.
