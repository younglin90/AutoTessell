# HEX-OCT-TRANSITION-QUALITY-1 — 혼합 레벨 전이 셀 품질 감사

## 목적과 범위

`AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION=1` 실험 레인에서만 생성되는
mixed-level 출력의 품질을 측정했다. 이번 카드는 repair, reject, reorder,
gate 완화를 하지 않는다.

새 report-only 유틸리티는
`core/generator/native_hex/transition_quality.py`에 있으며 다음을 동시에
기록한다.

- emitted cyclic face winding에 따른 signed volume과 기존 orientation-free
  volume baseline
- 전체 face와 transition-cell face의 Chen-style warpage
- 프로젝트 canonical OpenFOAM face skew
- builder boundary face key/면적과 generic writer 이후의 동일 항목
- builder cell 수와 writer가 제거한 cell 수
- face incidence histogram

builder-side metadata가 없으면 transition cell을 추측하지 않고 0으로
보고한다. 따라서 이 리포트는 topology 모양만 보고 provenance를 발명하지
않는다.

## 합성 fixture 결과

4×4×4 all-inside grid에서 `{level 1: 8, level 2: 56}`을 요청했다.

| 항목 | 결과 |
|---|---:|
| builder cell | 57 (`level 1: 1`, `level 2: 56`) |
| transition cell / 보고된 transition face | 1 / 3 |
| coarse→fine interface face | 12 |
| boundary face / face incidence | 87 / `{1:87, 2:132}` |
| negative emitted signed volume | 0 |
| orientation-free transition volume | 8.0 (부동소수점 오차 이내) |

합성 결과는 하니스가 실제 mixed-level 전이 셀을 놓치지 않는다는 것만
검증한다. 품질 gate 통과를 의미하지 않는다.

## 실제 형상 결과

fine, pre-BL, `max_cells=8000`, mixed-level realization opt-in으로 측정했다.
`builder → writer`는 동일 실행에서 기록했다.

| 형상 | transition cell / face | builder→writer | writer drop | builder boundary area → writer | boundary set |
|---|---:|---:|---:|---:|---|
| cylinder | 173 / 229 | 2463 → 2445 | 18 | 11.535 → 11.782881 (`+0.032722`) | 불일치 |
| sphere | 63 / 111 | 2684 → 2684 | 0 | 32.780 → 26.667228 (약 `-1.3e-9`) | 일치 |
| gear | 11 / 36 | 4542 → 4534 | 8 | 14.608957 → 14.321374 (`+0.004662`) | 불일치 |

| 형상 | transition skew p95 / max | transition warpage p95 / max | builder signed-volume 음수 | writer signed-volume 음수 |
|---|---:|---:|---:|---:|
| cylinder | 2.123554 / 133.752485 | 1.0 / 1.0 | 0 | 0 |
| sphere | 1.268530 / 1.620019 | 0.0 / 0.219133 | 0 | 0 |
| gear | 1.149741 / 1.422732 | 0.0 / 0.0 | 5 | 4 |

cylinder와 gear의 boundary set 변경 및 writer cell drop은 transition
connectivity가 generic writer 경계에서 보존되지 않는 구체적인 신호다.
gear는 writer 이전부터 emitted face winding 기준 음수 signed volume 5개가
있어, transition output을 기본 경로로 승격할 수 없다. sphere는 writer loss와
boundary key 변경은 없지만 transition face warpage/skew가 별도 품질
검토 대상이다.

## 판정

`HEX-OCT-TRANSITION-QUALITY-1`은 **측정 완료, production 승격은 기각**이다.
mixed-level connectivity가 존재한다는 synthetic realization 결과와 실제
품질 gate를 통과한다는 주장을 분리했다. `AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION`
은 계속 default-OFF로 둔다. 기본 native_hex 경로에는 새 품질 계산이
실행되지 않는다.

다음 후보는 transition repair가 아니라 먼저 `HEX-OCT-TRANSITION-WRITER-1`
(writer drop/boundary-set 불일치의 원인 분해)와 emitted face-winding
orientation contract 감사다. 이 두 계약이 닫히기 전에는 ECR, sheet,
untangle repair를 전이 셀에 포팅하지 않는다.

## 검증

- transition realization/quality 관련 targeted tests: `3 passed`
- 전체 native_hex 파일군: `113 passed in 141.77s`
- 새 Python 파일 `py_compile`: 통과
- 기본 mixed-level flag: OFF
- 생성 로직, 품질 gate, surface snap, writer 판정 로직: 이번 카드에서 변경하지 않음
