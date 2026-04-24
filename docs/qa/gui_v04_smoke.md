# AutoTessell v0.4 GUI 수동 스모크 체크리스트

beta100 기준 — 사용자가 "GUI 가 현재 코드 기능을 제대로 불러오는지" 확인하기 위한
짧은 (15 분) 수동 QA 체크리스트.

실행:

```bash
cd /home/younglin90/work/claude_code/AutoTessell
python3 desktop/qt_main.py
```

각 항목 PASS 시 체크 + 선택적으로 `docs/qa/screenshots/v04-smoke-NN.png` 저장.

---

## 입력 / 분석

- [ ] **S1.** `tests/stl/01_easy_cube.stl` drag-drop → 뷰포트에 큐브 표시.
- [ ] **S2.** `_show_geometry_hint` 로그 (`[INFO] 지오메트리 분석 — ...`) + KPI
  (Cells / Tier / Time) 노출.
- [ ] **S3.** right column JobPane 의 status_card 가 "idle" / "파일 로드됨" 상태 표시.

## 전략 선택

- [ ] **S4.** mesh_type 라디오 (auto / tet / hex_dominant / poly) 4 상태 전환 가능.
  Log 에 선택 반영 (내부 `_mesh_type` 변수 업데이트).
- [ ] **S5.** Quality segmented (draft / standard / fine) 전환 + 설명 라벨 변경.
- [ ] **S6.** 엔진 콤보에서 `native_tet` / `native_hex` / `native_poly` 선택 시 "엔진
  파라미터" 섹션이 GenericEngineParamPanel 로 자동 갱신.
  - native_hex 선택 시 `adaptive`, `n_levels`, `refinement_distance_factor`,
    `snap_iterations` 슬라이더 노출.
  - native_poly 선택 시 `smooth_iters`, `smooth_relax` 노출.

## y⁺ 패널 (beta100 신규)

- [ ] **S7.** 사이드바 "y⁺ 자동 BL 두께" 섹션 가시.
- [ ] **S8.** STL drop 후 특성 길이 스핀박스가 bbox 대각선으로 자동 갱신.
- [ ] **S9.** "계산하기" 클릭 → 결과 라벨 (`첫 층 두께: X.XXe-XX m`) + 클립보드에 값 복사.
- [ ] **S10.** 로그에 `[INFO] y⁺ → bl_first_thickness = ... m (다음 Run 부터 자동 적용)`.

## 실행 & 결과

- [ ] **S11.** native_tet draft 실행 → success=True, polyMesh 생성, 셀 수 KPI 갱신.
- [ ] **S12.** native_hex draft 실행 → success=True, Hex 비율 표시.
- [ ] **S13.** native_poly draft 실행 → success=True, polyMesh 생성.
- [ ] **S14.** Stop 버튼 → 서브프로세스 종료 + UI "idle" 복구.

## 결과 뷰

- [ ] **S15.** 뷰포트 품질 색상화 드롭다운 (Aspect / Skewness / Non-ortho) 3 모드 동작.
- [ ] **S16.** Quality 탭 히스토그램이 Build 완료 직후 자동 갱신.
- [ ] **S17.** Export pane 활성화 + STEP/IGES/STL 선택 포맷 export 동작.

---

## 알려진 제한

- Phase 2 BL metrics (degenerate prisms, max aspect ratio) 는 아직 리포트/GUI 에
  표시되지 않음 (beta76 plan 진행 중).
- `flow_velocity` / `turbulence_model` GUI 입력 미노출 — orchestrator default (1 m/s
  / kEpsilon) 사용. 필요 시 CLI `auto-tessell run --flow-velocity ...`.

## 완료 조건

- [ ] S1~S17 전 항목 PASS.
- [ ] FAIL 시 GitHub issue 생성 (beta100 regression 라벨) + 재현 스크린샷.
- [ ] `docs/qa/` 에 실행 환경 기록 (OS, Python, PySide6 버전).
