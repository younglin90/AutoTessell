# CARD TTT9 (beta2116) — voronoi cell merging skeleton

**target_engine**: poly
**모티프**: OpenFOAM polyDualMesh — voronoi cell merging (시퀀스 #9, 스켈레톤)

## 이론적 근거
- Fluent Watertight cleanup: quality 낮은 voronoi cell (sliver-like / high-aspect)
  을 인접 cell 과 merge 하여 dual mesh robust 화.
- polyDualMesh 도 동일 전략 (degenerate dual cell consolidation).
- 본 카드는 스켈레톤: merge candidate 식별 helper 정의만, 호출 경로 X.
- 다음 카드 TTT10 에서 실제 merge 적용 + 토폴로지 재구성 활성화.
- novelty 2, rigor 2, impact 2 → 합 6.

## 변경
- 파일: core/generator/native_poly/voronoi.py
- 위치 1: 모듈 상수 `_TTT9_CELL_MERGE = False` (default OFF gate).
- 위치 2: helper `_find_merge_candidates(cells, quality_threshold) -> list[tuple[int,int]]`
  - cell quality score (volume / aspect proxy) 평가 → threshold 미만 cell 과
    인접 cell index pair 반환. 호출되지 않음 (skeleton).

총 변경 ≤ 40줄.

## 검증 명령
```bash
timeout 60 python3 -c "from core.generator.native_poly.voronoi import _find_merge_candidates, _TTT9_CELL_MERGE; print('OK', _TTT9_CELL_MERGE)"
timeout 90 python3 -m pytest tests/test_native_poly.py -q
```

## 합격 기준
- 회귀 PASS
- bench 시간 ≤ 720s
- 영향 없음 (스켈레톤, gate OFF)
- poly grade 분포 동등 (A=5 유지)
