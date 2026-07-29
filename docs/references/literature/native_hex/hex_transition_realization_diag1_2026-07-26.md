# HEX-OCT-ADAPTIVE-TRANSITION-REALIZATION-DIAG1 — mixed-level 실현 감사

## 목적과 범위

이 카드는 실제 transition repair를 구현하지 않고, 현재 octree cell builder가
혼합 refinement level 요청을 실제 mixed-level cell과 transition face로
실현하는지 확인한다.

- 대상 함수: `core/generator/native_hex/octree.py::_build_nlevel_cells`
- 입력: 전체 inside인 4×4×4 fine grid
- 요청 level: 한 2×2×2 블록은 level 1, 나머지 56개 fine cell은 level 2
- 실행: `scripts/diag_hex_transition_realization1.py`
- 실험 flag: `AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION=1`
- 기본값: OFF. 기본 native_hex 경로에는 영향을 주지 않는다.

## 결과

| 항목 | 요청 | opt-in builder 출력 |
|---|---:|---:|
| level 종류 | 1, 2 | 1, 2 |
| level별 cell | level 1: 8, level 2: 56 | level 1: 1, level 2: 56 |
| builder cell 수 | 혼합 cell 기대 | 57 |
| transition cell | 관측 필요 | 1 |
| transition face direction | 관측 필요 | 3 |
| coarse→fine interface face | 관측 필요 | 12 |
| face incidence | 1/2만 허용 | `{1:87, 2:132}` |
| generic template | transition class 기대 | `t21:1, uniform:56` |

입력 level grid 자체는 `{1: 8, 2: 56}`으로 명확히 혼합되어 있다. 그러나
opt-in 출력 metadata는 coarse cell 1개와 fine cell 56개로 구성된다. coarse
cell에는 3개의 transition 방향과 12개의 fine interface face가 생성되며,
모든 face incidence는 1 또는 2다.

## 판정

`realization=observed`, 단 production 승격은 보류한다.

실험 flag를 켜면 현재 builder는 synthetic mixed-level 요청을 transition
connectivity로 실현한다. 반면 flag를 기본 ON으로 두고 실제 형상에 적용한
통합 회귀에서는 native_hex 영구 gate 5개가 실패했다. cylinder wall fidelity
와 boundary skew, fine negative-volume, adaptive cell budget이 악화되었고,
builder cell 수도 cylinder `2463`, sphere `2684`, gear `4542`로 기존
baseline과 크게 달라졌다. 따라서 이번 변경은 production fix가 아니라
default-OFF 실험 레인으로만 유지한다.

원인 조건은 finest-level 우선 순회의 `block_sz == 1` 분기에서 확인됐다.
기본 OFF 레인에서는 기존 동작을 유지하고, opt-in 레인에서만
`level_3d == target_lev` 확인을 적용한다.

이 결과만으로 coarse-block 병합 조건의 수정안을 승인하거나 transition
template을 새로 넣지는 않는다. 특히 현재 단계에서는 다음을 구분한다.

1. level grid 계산/요청이 혼합되는가: **예**
2. opt-in mixed-level cell connectivity가 출력되는가: **예**
3. coarse→fine interface incidence가 1/2로 유효한가: **예**
4. transition template/provenance가 writer까지 전달되는가: **아니오**

## 재현성과 검증

- 진단 스크립트 2회 결과가 동일했다.
- realization 전용 테스트와 기존 provenance 테스트: `4 passed`.
- 기본 OFF native_hex 관련 회귀: `57 passed`.
- 새 Python 파일 `py_compile` 통과.
- production 기본 경로·surface mesh·writer contract는 기존 동작을 유지한다.

## 다음 단계

다음 카드는 `HEX-OCT-TRANSITION-QUALITY-1`이다. opt-in mixed-level output에
대해 transition cell의 signed volume, face warpage, local skew, boundary
face-set, writer drop을 측정해야 한다. 이 카드가 통과하기 전에는
`AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION`을 기본 ON으로 바꾸지 않는다.
