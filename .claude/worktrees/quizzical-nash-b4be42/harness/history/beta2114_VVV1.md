# CARD VVV1 (beta2114) — Stellar 4-op iterative coordinator (skeleton)

**target_engine**: tet
**모티프**: Klingner & Shewchuk 2008 §3 — Stellar 4-op iterative coordinator (시퀀스 #1, 스켈레톤)

## 이론적 근거

- 현 native_tet 후처리 (NNN/RRR/UUU) 는 sequential pass — collapse / split / swap / smooth 가
  서로 단절된 단계로 한 번씩 적용되어 상호작용 잠재력 미활용.
- Klingner & Shewchuk 의 Stellar 는 priority queue 기반 4-op iterative: 최저 품질 셀을 dequeue
  → 4-op 중 best ΔQ 선택 → 적용 → neighbor re-enqueue. paper-worthy 메쉬 개선의 표준 패턴.
- 본 카드 (VVV1) 는 **스켈레톤** 만: operations queue 자료구조 + 후보 식별 helper 정의,
  실제 호출 경로 없음 (`_VVV1_STELLAR_QUEUE = False`).
- 다음 카드 VVV2 에서 mesher 메인 루프 통합 + flag ON.
- novelty 3, rigor 3, impact 3 → 합 9.

## 변경

- 파일: `core/generator/native_tet/stellar.py` (신규 ≤80줄)
- 함수:
  1. 모듈 상수 `_VVV1_STELLAR_QUEUE: bool = False`
  2. `_build_op_queue(pts: np.ndarray, tets: np.ndarray) -> list[dict]` — 셀별 품질 계산
     후 (quality, tet_idx, candidate_ops) dict 리스트 생성, quality 오름차순 정렬.
  3. `_apply_op_queue(pts, tets, queue, max_ops: int = 50) -> tuple[np.ndarray, np.ndarray, int]`
     — skeleton: queue iterate, 각 op dispatch placeholder (collapse/split/swap/smooth 분기 `pass`
     + `n_applied` 카운터), 즉시 입력 그대로 반환.
- 호출처 추가 없음 (skeleton 만).

## 검증 명령

```bash
timeout 60 python3 -c "from core.generator.native_tet.stellar import _build_op_queue, _apply_op_queue, _VVV1_STELLAR_QUEUE; print('OK', _VVV1_STELLAR_QUEUE)"
timeout 90 python3 -m pytest tests/test_native_tet_amips.py -q
```

## 합격 기준

- 회귀 PASS (test_native_tet_amips 100%)
- bench 시간 ≤ 720s (스켈레톤이라 영향 없음 기대)
- mq / 합격률 동등 (skeleton, default OFF)
- BL 합격 분포 동등
