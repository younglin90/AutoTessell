# HEX-OCT-TRANSITION-WRITER-1 — writer drop와 boundary 재분류 원인 감사

## 목적

`HEX-OCT-TRANSITION-QUALITY-1`에서 관측한 writer cell drop과
boundary face-set 변경이 generic writer 자체의 비결정적 오류인지, 아니면
writer 직전 mesh가 이미 degenerate face를 포함하고 있어 정상적인 filtering이
발생한 것인지 분리했다.

writer를 수정하지 않고 `transition_quality.py`에 generic writer의 공개된
face-cleaning 조건을 그대로 재현하는 report-only 검사를 추가했다.
`bbox_diag`로 계산한 `area_eps`, 중복 정점 제거, 3점 미만/면적 0 face,
cell face 수 4 미만 조건을 builder output에 적용하고, 다음을 비교했다.

- 예측 drop cell ID와 실제 writer drop 수
- drop cell이 가진 내부 face 중 한쪽 owner만 제거되는 face 수
- 실제 writer boundary face key의 추가/삭제 수
- 구체적인 cell/face/vertex 좌표 증거

## 결과

| 형상 | 예측 drop / 실제 drop | drop으로 노출 예측 / 실제 boundary 추가 | boundary 삭제 | boundary face 수 변화 |
|---|---:|---:|---:|---:|
| cylinder | 18 / 18 | 60 / 60 | 44 | 3699 → 3715 (`+16`) |
| sphere | 0 / 0 | 0 / 0 | 0 | 변경 없음 |
| gear | 8 / 8 | 23 / 23 | 19 | 4738 → 4742 (`+4`) |

두 real shape 모두 `writer_drop_prediction_matches_actual=True`였다. 따라서
writer가 임의로 cell을 선택해 boundary를 바꾼 것이 아니라, 예측된
degenerate cell 제거가 그대로 boundary key 변경을 만들었다.

## 구체적 사례

### cylinder

첫 drop은 builder cell `145`, face `5`, vertex key
`[1113, 1134, 1135, 1114]`이다. 네 정점은 중복 ID가 아니지만 snap 후 좌표가
다음처럼 두 쌍씩 완전히 겹친다.

```text
1113 = (-0.4, 0.05, -0.5)
1134 = (-0.4, 0.10, -0.5)
1135 = (-0.4, 0.10, -0.5)
1114 = (-0.4, 0.05, -0.5)
```

따라서 `n_unique_vertices=4`여도 face area는 `0.0`이고 writer threshold는
약 `3.0e-24`다. 이 face 하나가 cell 145 전체를 drop시키는 writer 조건과
정확히 일치한다. 그 cell과 같은 owner를 갖는 내부 face 60개가 writer 뒤에
boundary가 되었고, 기존 boundary face 44개는 cell 제거/재구성 결과에서
사라졌다.

### gear

첫 drop은 cell `329`, face `3`, vertex key
`[1937, 1938, 2225, 2224]`다. 좌표는

```text
(-0.8048189878463747, 0.5748707056045532, 0.30000001192092896)
(-0.8048189878463745, 0.5748707056045532, 0.30000001192092896)
(-0.7473319178463742, 0.5748707056045532, 0.30000001192092896)
(-0.7473319178463743, 0.5748707056045532, 0.30000001192092896)
```

역시 두 쌍이 겹쳐 face area가 0이고, 8/8 drop 및 23/23 boundary 추가가
재현된다. gear는 이와 별도로 builder 단계에서 emitted signed-volume 음수
5개도 이미 존재한다.

## 판정

`HEX-OCT-TRANSITION-WRITER-1`은 **측정 완료, writer 무죄**다. generic writer의
drop은 현재 공개된 degenerate-face 계약과 일치하며, boundary-set 변경은
그 drop으로 인한 owner 재분류의 결과다. writer의 filtering을 완화하거나
drop을 숨기는 수정은 표면/위상 불변식에 반하므로 제안하지 않는다.

남은 원인은 writer 이전, 특히 mixed-level transition face가 iterative snap
또는 wall-fit 이후 두 쌍의 정점을 같은 위치로 보내는 upstream 단계다. 다음
카드는 `HEX-OCT-TRANSITION-SNAP-ROOTCAUSE-1`로, builder 직후 → iterative
snap 후 → wall-fit 후 → skew-relax 후 각 단계의 zero-area face와 boundary
set을 분리 측정한다. 이 카드가 닫히기 전에는 transition repair를 구현하지
않는다.

## 검증

- writer drop 진단을 포함한 targeted tests: `3 passed`
- 기존 native_hex 파일군의 기본 OFF 회귀: 직전 `113 passed`
- writer, snap, quality gate 동작 변경: 없음
- 커밋/스테이징: 없음
