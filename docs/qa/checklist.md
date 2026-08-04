# AutoTessell Qt GUI — 수동 QA 체크리스트

> 이 문서는 **Windows 실기계에서 직접 확인해야 하는 기능**들의 체크리스트입니다.
> WSL headless 환경에서는 자동 테스트(`tests/test_qt_app.py`, 83 passed)가 커버하지만,
> 실제 Qt 윈도우·드래그앤드롭·PyVista 인터랙션은 수동 검증이 필요합니다.

## 전제

1. Windows에서 AutoTessell NSIS 인스톨러 설치 완료 (`AutoTessell-0.3.5-Setup.exe`)
2. `auto-tessell-gui` 실행 또는 시작 메뉴에서 AutoTessell 아이콘 클릭
3. 샘플 파일: `installer/staging/benchmarks/sphere.stl`, `cylinder.stl`

---

## 1. 시작 화면 (30초)

- [ ] 메인 윈도우가 1400×900 이상으로 뜨고, 타이틀 "AutoTessell" 표시
- [ ] 좌측 사이드바: 입력 파일 드롭존, 품질 레벨(Draft/Standard/Fine), 엔진 선택
- [ ] 중앙: 빈 PyVista 뷰포트 (다크 배경 #0d1117)
- [ ] 우측 3탭: Job / Quality / Export
- [ ] 하단 Tier Pipeline Strip: 6개 원형 노드 (1~6) + Resume/Stop/다시실행 버튼
- [ ] 상태바 하단에 "Ready" 배지

## 2. DropZone — 드래그앤드롭 + 클릭 (1분)

- [ ] DropZone 영역 위에 마우스 올리면 테두리 색 변경 (hover)
- [ ] `sphere.stl` 파일을 윈도우 탐색기에서 드래그 → DropZone에 드롭
  - [ ] 드롭 순간 테두리 색 파란색으로 변경
  - [ ] 드롭 후 파일 경로가 라벨에 표시됨
  - [ ] 뷰포트에 구 메시 프리뷰 로드 (회색 와이어프레임 또는 solid)
- [ ] DropZone을 **클릭** → 파일 다이얼로그 열림
  - [ ] 다이얼로그에서 `cylinder.stl` 선택 → 뷰포트 갱신
  - [ ] 취소 버튼 → 기존 파일 유지

## 3. 뷰포트 인터랙션 (2분)

`sphere.stl` 로드된 상태에서:

- [ ] 왼쪽 마우스 드래그 → 회전
- [ ] 우측 마우스 드래그 또는 휠 → 줌
- [ ] 가운데 드래그 → 팬
- [ ] 툴바 버튼:
  - [ ] "와이어프레임" 토글 → 메시가 와이어로 전환
  - [ ] "점" 토글 → 정점 표시
  - [ ] "X/Y/Z/ISO" 뷰 버튼 → 카메라 방향 전환
- [ ] **품질 표시** 드롭다운 버튼:
  - [ ] 버튼 우측 "▾" 화살표 클릭 → 메뉴 열림
  - [ ] 메뉴에 "Aspect / Skewness / Non-ortho" 3개 항목 표시
  - [ ] "Skewness" 선택 → 버튼 텍스트 "품질: Skewness ▾"로 변경
  - [ ] 버튼 클릭 (토글 on) → 메시가 RdYlGn 컬러맵으로 색상화
  - [ ] 색상바(scalar bar) 타이틀 "Skewness" 표시
  - [ ] 다시 클릭 (토글 off) → 일반 렌더로 복귀

## 4. 파이프라인 실행 — Draft (1분)

- [ ] 좌측 사이드바에서 품질 "Draft" 선택, 엔진 "auto"
- [ ] 출력 디렉토리: 기본값 (`input_dir/output` 또는 지정)
- [ ] "실행" 버튼 클릭
- [ ] Tier Pipeline Strip에서 노드가 순서대로 active → done 전환 (~3초)
  - [ ] 1번 Preprocess → 활성 (파란 펄스)
  - [ ] 2~4번 순차 활성화
  - [ ] 6번 Validate → done
- [ ] Job 탭 로그에 진행 메시지 출력
- [ ] 완료 후:
  - [ ] 상태 배지 "Completed" (녹색)
  - [ ] Tier 노드 전부 done (녹색 체크)
  - [ ] 뷰포트에 볼륨 메시 표시 (내부 셀 색상화)
  - [ ] Quality 탭 활성화 + 히스토그램 2개 subplot 표시 (Aspect + Skewness)
  - [ ] Export 탭 활성화

## 5. Quality 탭 (1분)

- [ ] 6개 checkMesh 바 (Max aspect, Max skew, Max non-ortho, Min area, Min vol, Neg vols) 값 표시
- [ ] 셀 구성 바 (Hex/Prism/Poly/Tet) 비율 + 숫자 표시 (sphere는 100% Tet)
- [ ] 합격 기준 4개 행 전부 ✓ 녹색
- [ ] **히스토그램** (matplotlib 임베드):
  - [ ] 좌측 서브플롯: "Aspect Ratio" 분포 (청색)
  - [ ] 우측 서브플롯: "Skewness" 분포 (주황색)
  - [ ] 배경 #161a20 다크, 눈금 색 #818a99
  - [ ] 윈도우 리사이즈 시 플롯 크기 따라감

## 6. 로그 우클릭 메뉴 (30초)

- [ ] Job 탭 로그박스 위에 힌트 "💡 우클릭으로 복사·저장" 표시
- [ ] 로그박스 마우스 오버 → 툴팁 "우클릭 → 로그 복사 / 파일로 저장 / 지우기"
- [ ] 로그 위 우클릭 → 컨텍스트 메뉴:
  - [ ] "복사" → 클립보드에 전체 로그 복사 (텍스트 에디터 붙여넣기로 검증)
  - [ ] "저장..." → 파일 다이얼로그 → `.txt` 저장 → 파일 열어서 로그 내용 확인
  - [ ] "지우기" → 로그박스 비워짐
- [ ] 로그 검색 필드에 "진행" 입력 → 해당 단어 포함 줄만 표시
- [ ] 필터 chip "ERR" 클릭 → ERR 레벨 메시지만 표시 (sphere draft는 없을 수 있음)
- [ ] "ALL" chip 클릭 → 전체 복원

## 7. Tier 노드 클릭 → 파라미터 팝업 (1분)

- [ ] Tier Pipeline Strip에서 3번 노드 (Volume) 클릭
- [ ] 다이얼로그 열림 — 제목 "Tier 3 파라미터 (읽기 전용)"
- [ ] 서브타이틀에 읽기 전용 안내 라벨
- [ ] Tier 이름, 엔진, 상태, 현재 선택 엔진, 품질 레벨 표시
- [ ] 관련 파라미터 기본값 나열 (tetwild: epsilon, edge_length 등)
- [ ] "닫기" 버튼 → 다이얼로그 종료

## 8. 중단 — requestInterruption (30초)

- [ ] Fine 품질 선택 (snappyHexMesh, 30분+ 예상)
- [ ] "실행" 클릭 후 Tier 3번(Volume) active 상태 진입 대기
- [ ] 하단 Tier Strip의 "Stop" 버튼 클릭
  - [ ] 로그에 "[INFO] 파이프라인 중단" 표시
  - [ ] 상태 배지 "Cancelled" (주황색)
  - [ ] active였던 Tier 노드가 "skipped" (점선 테두리, 45% 투명)으로 전환
  - [ ] 이미 done이었던 노드는 done 유지
  - [ ] 서브프로세스 (snappyHexMesh.exe) 종료 확인 (작업 관리자)
- [ ] "다시 실행" 버튼 클릭 → 파이프라인 재시작

## 9. Export (2분)

파이프라인 성공 후 Export 탭에서:

- [ ] **포맷 라디오**:
  - [ ] OpenFOAM polyMesh (기본 선택)
  - [ ] VTU, CGNS, Nastran, Fluent, Gmsh
- [ ] **압축** 체크박스 (ZIP)
- [ ] "저장" 버튼 클릭
  - [ ] OpenFOAM 선택 시: 지정 경로에 `constant/polyMesh/` 생성, `points/faces/owner/neighbour/boundary` 파일 존재
  - [ ] VTU 선택 시: `.vtu` 파일 생성 → ParaView에서 열어서 메시 확인
  - [ ] ZIP 체크 시: `.zip` 파일 생성 → 압축 해제해서 구조 확인
- [ ] **스크린샷** (툴바 카메라 버튼 또는 메뉴):
  - [ ] PNG 저장 → 뷰포트 그대로 WYSIWYG 캡처
  - [ ] 품질 컬러맵이 on이면 PNG에도 색상화 반영
- [ ] **ParaView 상태 저장** (.pvsm):
  - [ ] OpenFOAM 케이스면 OpenFOAMReader 기반 `.pvsm` 생성
  - [ ] VTU면 XMLUnstructuredGridReader 기반
  - [ ] ParaView에서 File → Load State로 열어서 로드 확인

## 10. 프로젝트 저장/복원 (1분)

- [ ] 메뉴 "파일 → 프로젝트 저장" → JSON 파일 지정 저장
- [ ] JSON 내용 확인: 입력파일/출력경로/품질레벨/엔진/전처리 옵션 포함
- [ ] "파일 → 새 프로젝트" → 모든 상태 초기화
- [ ] "파일 → 프로젝트 열기" → 저장한 JSON 로드
  - [ ] 입력 파일 경로 복원 (DropZone 라벨)
  - [ ] 출력 경로 복원
  - [ ] 품질 레벨 복원 (세그먼트 버튼)
  - [ ] 엔진 콤보 복원
  - [ ] 누락된 경로 있으면 QMessageBox.warning 표시

## 11. 에러 시나리오 (1분)

- [ ] 불량 STL (watertight 아님) 드롭 → L1/L2/L3 수리 진행 로그
- [ ] STEP 파일 드롭 → cadquery/gmsh 테셀레이션 자동 실행
- [ ] 존재하지 않는 경로 입력 → 친절한 에러 메시지
- [ ] OpenFOAM 미설치 상태 + Fine 품질 선택 → 실행 전 경고 다이얼로그

## 12. 성능/안정성 (5분)

- [ ] 대형 STL (50만 면 이상) 드롭 → 뷰포트 로딩 ~5초, UI 반응성 유지
- [ ] Fine 품질로 snappyHexMesh 실행 (~30분) → 진행률 지속 업데이트, UI 얼지 않음
- [ ] 파이프라인 실행 중 품질 표시 토글 → 블록 없이 동작
- [ ] 윈도우 최소화 → 복원 → 뷰포트/레이아웃 정상
- [ ] 메모리 사용량 모니터링 (작업 관리자) — 500MB 이하 유지 (sphere 기준)

---

## 자동 테스트 커버리지 (참고)

`tests/test_qt_app.py` — 83 passed, 8 skipped (WSL headless 기준):

| 영역 | 자동 커버 | 이 체크리스트 필요 |
|------|----------|---------------------|
| 클래스/시그널 구조 | ✅ 83 tests | — |
| DropZone.clicked Signal | ✅ QTest.mouseClick | 실제 드래그앤드롭 UI (#2) |
| _TierNode click → tier_clicked | ✅ QTest | UI 펄스 애니메이션 (#7) |
| TierPipelineStrip 버튼 | ✅ QTest | 시각적 상태 전환 (#8) |
| QualityPane.set_metric | ✅ 직접 호출 | 바 채움 애니메이션 (#5) |
| _HistogramCanvas.update_histograms | ✅ 데이터 주입 | matplotlib 렌더 품질 (#5) |
| PipelineWorker end-to-end | ✅ sphere.stl draft | Fine 품질, 실제 볼륨 파이프라인 (#4, #8) |
| Stop → finished emit | ✅ requestInterruption | 서브프로세스 종료 확인 (#8) |
| _on_pipeline_finished → Cancelled 배지 | ✅ 소스 검증 | 실제 배지 색상 (#8) |
| mesh_ready Signal 연결 | requires_display | 실제 PyVista 메시 로드 (#3) |
| _on_quality_metric_selected | requires_display | 드롭다운 메뉴 → 실제 색상화 (#3) |

---

## 체크리스트 채점

- **12개 섹션 모두 통과** → 배포 가능 (P0 없음)
- **1개 실패** → 해당 항목 `TODOS.md`에 P1으로 기록 + 이슈 재현 단계 문서화
- **2개+ 실패** → 배포 보류, 근본 원인 조사 (`/investigate`)

체크리스트 결과는 매 릴리스마다 `docs/qa-runs/YYYY-MM-DD.md`로 기록 권장.
