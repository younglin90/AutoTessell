# HEX-OCT-WALLFIT-FACE-AREA-GUARD-1 — opt-in face-area guard 실험

## 목적

`HEX-OCT-TRANSITION-WRITER-1`에서 확인한 upstream wall-fit의 zero-area
face 생성만 막는 최소 후보를 실험했다. `_wall_fit_snap`의 candidate
acceptance에 모든 incident face의 polygon area floor 검사를 추가했고,
실험 flag는 `AUTO_TESSELL_HEX_WALLFIT_FACE_AREA_GUARD=1`, 기본값은 OFF다.

기존 sign 보존, cell volume, 거리 감소, envelope 조건은 그대로 두고,
새 조건은 face가 0-area가 되면 candidate를 reject/backtrack하는 것뿐이다.

## opt-in mixed-level 결과

fine pre-BL, `max_cells=8000`, mixed-level realization과 face-area guard를
함께 켰다.

| 형상 | writer drop | boundary set | transition skew p95/max | transition warpage p95/max |
|---|---:|---|---:|---:|
| cylinder | 0 (기존 18) | 일치 (기존 불일치) | 2.150564 / 133.752485 | 1.0 / 1.0 |
| gear | 0 (기존 8) | 일치 (기존 불일치) | 3.279938 / 11.460936 | 0.888786 / 1.0 |

wall-fit OFF control도 cylinder/gear에서 drop `0/0`, boundary set 일치를
보였으므로, guard가 writer filtering을 우회한 것이 아니라 wall-fit 후보를
face-area 조건으로 보수화한 효과로 해석된다. 다만 skew/warpage는 여전히
높고 gear의 builder signed-volume 음수 5개 문제도 남아 있다.

## 판정

**부분 유효, production 승격 보류.** 이 guard는 writer drop 및 그에 따른
boundary 재분류를 막는 invariant 보조수단으로는 유망하지만, transition
quality repair가 아니다. 기본 OFF를 유지하며 다음 quality card에서
transition face의 국소 skew/warpage와 인접 셀의 품질을 동시에 개선하는
방향을 별도 검증해야 한다. face-area guard만으로 ECR/sheet/untangle
mechanism을 열지 않는다.

## 검증

- targeted transition/provenance/octree tests: `16 passed`
- 새 Python 파일 `py_compile`: 통과
- default OFF 경로: 기존 native_hex baseline과 동작 동일
- mixed-level guard control: cylinder/gear writer drop 0, boundary set equal
- 커밋/스테이징: 없음
