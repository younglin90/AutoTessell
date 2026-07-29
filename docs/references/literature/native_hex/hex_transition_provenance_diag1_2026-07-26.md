# HEX-TRANSITION-PROVENANCE-DIAG1 — builder-to-writer 계측 결과

## 범위

이번 카드는 octree 전이 셀의 품질을 고치는 작업이 아니라, 현재
`native_hex` 경로가 실제로 어떤 refinement level/template/provenance를
만들고 writer까지 전달하는지 확인하는 report-only 계측이다.

- 환경변수 `AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG=1`일 때만 활성화한다.
- 기본값은 OFF이며, cell connectivity·point 위치·품질 게이트를 변경하지 않는다.
- builder 안에서는 `grid_origin`, `target_level`, 인접 level에서 유도한
  generic transition pattern만 관찰한다. 이는 authoritative octree lineage,
  hanging-node valence, emitted template ID 또는 CAD patch provenance가 아니다.
- 실행: `scripts/diag_hex_transition_provenance1.py --max-cells 8000`

## 실측

fine pre-BL 경로에서 동일한 `max_cells=8000` 조건으로 cylinder, sphere, gear를
실행했다. `builder cells`는 octree builder 직후, `written cells`는
`write_generic_polymesh`가 받은 뒤의 cell 수다.

| 형상 | builder cells | written cells | metadata / unique origin | level histogram | generic template | transition cells / faces | feature segments / refined cells | writer 경계 |
| --- | ---: | ---: | --- | --- | --- | ---: | ---: | --- |
| cylinder | 6320 | 6320 | 6320 / 6320 | `{4: 6320}` | `{uniform: 6320}` | 0 / 0 | 64 / 61 | 손실 0 |
| sphere | 4224 | 4224 | 4224 / 4224 | `{4: 4224}` | `{uniform: 4224}` | 0 / 0 | 0 / 0 | 손실 0 |
| gear | 4920 | 4914 | 4920 / 4920 | `{4: 4920}` | `{uniform: 4920}` | 0 / 0 | 592 / 0 | 6개 cell drop |

세 형상 모두 이 실행 조건에서 builder가 내보낸 cell은 `target_level=4`뿐이며,
계측기가 유도한 transition cell/face는 0건이다. 따라서 현재 bench 결과만으로는
“adaptive octree transition cell이 출력되었다”거나 “transition-sheet 품질
문제가 이 mesh에서 발생했다”고 주장할 수 없다. octree 통계의 `n_coarse`/
`n_fine` 값은 기존 구현의 요약 카운터이며, 출력 cell별 level histogram과
동일한 의미가 아니다.

gear에서는 builder의 4920개가 generic writer 경계에서 4914개로 줄었다. 이
6개는 기존 writer의 degenerate-cell drop 경로에서 제거된 것으로 기록되며,
transition repair의 효과나 원인으로 해석하지 않는다.

## provenance 손실 지점

builder-side summary는 `mesher.py`의
`native_hex_transition_provenance_before_writer` 로그에 존재하지만,
`write_generic_polymesh`에는 최종 point/cell connectivity만 전달된다. writer
직후 로그에서 `writer_metadata_forwarded=False`가 확인되므로, 다음 필드는
현재 출력 cache에서 복구할 수 없다.

1. octree leaf lineage와 안정적인 source-cell ID
2. 면별 authoritative transition-chain ID와 hanging-node valence
3. cell별 실제 emitted transition-template identity
4. 영향을 받은 cell의 feature-edge/curve/corner provenance
5. 면별 authoritative boundary patch/source provenance

따라서 이전 `HEX-TRANSITION-DIAG1`의 `BLOCKED` 판정은 유지한다. 이번 계측은
막연한 “metadata가 없다”가 아니라, metadata가 **builder에서 관찰되지만
generic writer 경계에서 전달되지 않는다는 것**과, 현재 세 benchmark의 실제
출력에는 transition level 자체가 없다는 것을 분리해 확정했다.

## 결정론성과 회귀

- provenance census를 끈 실행과 켠 실행의 point/cell 배열은 동일했다.
- census를 두 번 실행한 결과의 summary와 cell 순서는 동일했다.
- 관련 native_hex 회귀 묶음: `55 passed`.
- 새 provenance 단위/진단 묶음: `4 passed`.
- 새·수정 Python 파일은 `py_compile`을 통과했다.
- WSL 환경에는 `black`과 `ruff`가 설치되어 있지 않아 해당 두 도구는 실행하지
  못했다.

이번 카드에서는 writer, octree 생성, transition repair, surface snap의
동작을 변경하지 않았고 커밋도 만들지 않았다. 기존 작업트리의 다른 WIP는
그대로 보존한다.

## 다음 카드

1. `HEX-OCT-ADAPTIVE-TRANSITION-REALIZATION-DIAG1`: mixed-level synthetic
   fixture 또는 직접적인 adaptive level fixture를 만들어 실제 transition
   template이 출력되는지 먼저 입증한다. 그 전에는 transition-sheet repair를
   구현하지 않는다.
2. `HEX-WRITER-DEGENERATE-DROP-DIAG1`: gear의 builder 6개 → writer 0개 drop을
   cell ID/부피/면 집합 수준에서 별도 감사한다.
3. 실제 transition fixture가 생긴 뒤에만 lineage/template/patch provenance를
   writer까지 전달하는 작은 계약을 설계한다.
