# AutoTessell 다음 단계 계획
**작성일:** 2026-04-19
**기반 commit:** `8a8c6d7` (Codex working tree 미커밋 쌓임)
**직전 세션:** `docs/plans/codex-gui-verification-session-summary.md`

---

## Context — 현재 어디 와 있나

**지난 Codex 세션 결과:**
- Task 1A~3B 전부 구현 (GUI visual regression + 엔진 정책 리빌드 + 프리셋↔슬라이더 동기 + signal 감사 + 공통 QSS + Esc mixin)
- 테스트 148 → **171 passed**, 8 skipped
- 8개 baseline PNG 생성 (`tests/fixtures/screenshots/baselines/`)
- `desktop/qt_app/widgets/dialog_mixin.py` 신설
- **미커밋 working tree** 상태로 종료

**Baseline 01_empty_mainwindow.png 육안 확인 결과 (시각 검증 직접 수행):**
- 타이틀·사이드바·메뉴·뷰포트·우측 3탭·하단 Tier strip 전부 제대로 렌더됨 ✓
- Korean 텍스트 렌더링 정상 (Malgun Gothic 기대대로 등록됨) ✓
- 기본 UI 레이아웃 3-컬럼 일관 ✓

**남은 이슈 (육안 + 로그로 확인):**
1. ⚠️ **사이드바가 viewport 높이보다 길어 잘림** — baseline 01에서 "L2 엔진: auto" 행이 최하단, 실행 버튼이 안 보임. 스크롤 필요하지만 실기계 확인 필요
2. ⚠️ **뷰포트 KPI 오버레이 안 보임** — PyvistaQt 오프스크린 native abort 때문에 fallback으로 정적 viewer. 오버레이는 PyvistaQt 레이어 위에 얹음. 실기계에서만 확인 가능
3. ⚠️ **WildMesh 튜닝 패널 baseline 없음** — tier=wildmesh 선택 상태에서만 표시되므로 별도 시나리오 필요
4. ⚠️ **정책 wildmesh_only 모드 baseline 없음** — 🔒 마커 렌더 확인 필요
5. ⚠️ **report_pdf.py Glyph 10003 (✓) missing** — Malgun Gothic에 체크마크 없음. PDF 리포트의 PASS/FAIL 마커 깨짐
6. ⚠️ **미커밋 변경사항** — Codex 세션이 6 tasks 구현했는데 한 번도 commit 안 함

---

## 목표

**이번 세션 outcome:**
1. Codex의 작업을 **태스크 단위 6 커밋**으로 나눠 정리 + push
2. 잔여 시각 이슈 3건 수정 (1~3번)
3. baseline PNG 4장 추가 (wildmesh 튜닝, 정책 차단, 파일 로드 후, 실행 중)
4. 테스트 171 → 180+ passed

**이번 세션 범위 밖:** Compare Mode, 온보딩, 테마 전환, main_window 분리

---

## Phase 1 — 커밋 + 배포 위생 (최우선, 30분)

Codex가 모든 작업을 한 작업트리에 쌓았음. 핸드오프 규칙 "한 태스크 = 한 커밋" 을 복원.

### 1A. 미커밋 작업 **6 커밋으로 분리**

Codex가 건드린 파일 목록:
```
M  .gitignore
M  pyproject.toml
M  tests/conftest.py
M  tests/test_qt_app.py
M  desktop/qt_app/main_window.py
M  desktop/qt_app/batch_dialog.py
M  desktop/qt_app/history_dialog.py
M  desktop/qt_app/error_recovery.py
?? desktop/qt_app/widgets/dialog_mixin.py
?? tests/test_gui_visual.py
?? tests/fixtures/screenshots/
?? docs/plans/
```

**커밋 순서:**

1. **커밋 1 (Task 1A 일부)**: visual 테스트 인프라
   - `tests/test_gui_visual.py` 신규
   - `tests/fixtures/screenshots/baselines/` 8 PNG
   - `.gitignore` (actual/ 제외)
   - `pyproject.toml` (pytest visual marker)
   - `tests/conftest.py` (visual marker 관련 변경)
   - 메시지: `test(qt-gui): Task 1A — visual regression infra (8 baselines)`

2. **커밋 2 (Task 1B)**: 엔진 정책 드롭다운 리빌드
   - `desktop/qt_app/main_window.py` 중 `_make_engine_combo_model`/`_rebuild_engine_combo_model`/`_on_set_engine_policy` 부분
   - `tests/test_qt_app.py` 중 `test_engine_policy_switch_rebuilds_dropdown`
   - 메시지: `fix(qt-gui): Task 1B — engine policy switch rebuilds dropdown model`

3. **커밋 3 (Task 1C)**: 프리셋 → 슬라이더 동기화
   - `main_window.py` `_on_preset_selected` 부분
   - `test_qt_app.py` 관련 테스트
   - 메시지: `fix(qt-gui): Task 1C — preset selection syncs WildMesh slider panel`

4. **커밋 4 (Task 1D)**: signal 감사
   - `test_qt_app.py` 중 `test_signal_connections_completeness`, `test_export_pane_signal_wired`
   - 메시지: `test(qt-gui): Task 1D — signal/slot wiring completeness audit`

5. **커밋 5 (Task 3A)**: 다이얼로그 공통 QSS
   - `main_window.py` `get_dialog_qss`/`get_table_qss`
   - `batch_dialog.py`, `history_dialog.py`, `error_recovery.py` 스타일 변경
   - 메시지: `refactor(qt-gui): Task 3A — unified dialog QSS via PALETTE helper`

6. **커밋 6 (Task 3B)**: Esc mixin
   - `desktop/qt_app/widgets/dialog_mixin.py` 신규
   - `batch_dialog.py`/`history_dialog.py`/`error_recovery.py` 상속 추가
   - `main_window.py` 단축키/Tier 다이얼로그 변경
   - 메시지: `feat(qt-gui): Task 3B — unified Esc-dismiss on all modal dialogs`

7. **커밋 7 (docs)**: 핸드오프 문서 + summary
   - `docs/plans/codex-handoff-gui-verification.md` 완료 기록
   - `docs/plans/codex-gui-verification-session-summary.md` 신규
   - `docs/plans/next-steps-2026-04-19.md` (이 파일)
   - 메시지: `docs: GUI 검증 세션 기록 + 다음 계획`

**방법:** `git add -p` 로 hunk 단위 선택. 너무 복잡하면 `git stash` 후 차례로 재적용.

### 1B. 외부 디렉토리 제외 확인
`AlgoHex/`, `Feature-Preserving-Octree-Hex-Meshing/`, `HOHQMesh/`, `VoroCrust/`, `bin/`, `pdmt/`, `voro/`, `tessell-mesh/build_make/_deps/*`, `installer/staging/`, `octree.vtk` 전부 untracked. `.gitignore` 에 명시 추가해서 실수로 커밋 방지.

### 1C. Push
```bash
git log --oneline 8a8c6d7..HEAD  # 커밋 7개 확인
git push origin master
```

**완료 조건:** origin/master에 7 커밋 추가, `git status` 깔끔.

---

## Phase 2 — 시각 이슈 수정 (30분)

### 2A. 사이드바 스크롤 확인 + 고정 레이아웃 검증
**문제:** baseline 01에서 사이드바가 viewport 높이보다 길어 잘림.

**조사:**
- `desktop/qt_app/main_window.py` `_build_sidebar()` — QScrollArea 감싸져 있는지 확인
- 감싸져 있다면 스크롤 동작하지만 baseline PNG는 정적 캡처라 상단만 보임 → 문제 아님
- 안 감싸져 있으면 실제 잘림 → QScrollArea 추가

**조치:**
- QScrollArea 확인되면 baseline는 OK (설명 주석 추가)
- 없으면 QScrollArea로 감싸기

**테스트:** `test_sidebar_uses_scroll_area` — sidebar widget의 parent chain에 QScrollArea 존재 검증

### 2B. report_pdf 체크마크 glyph missing 해결
**문제:** Malgun Gothic에 `\N{CHECK MARK}` (✓, U+2713) 없음.

**옵션:**
- **옵션 A:** 체크마크를 ASCII-range 문자로 교체 (`[OK]`, `[FAIL]`)
- **옵션 B:** matplotlib에 `Symbola` 또는 DejaVu Sans 등 Unicode 지원 폰트를 특정 Text object에만 적용
- **옵션 C:** 텍스트 대신 matplotlib 도형 (Circle + 내부 마크) 그리기

**추천:** 옵션 A (가장 안정). PDF 리포트 신뢰도 최우선, 장식 최소.

**파일:** `desktop/qt_app/report_pdf.py:_write_page` 에서 "✓"/"✗" 사용처 찾아 교체.

**테스트:** `test_report_pdf_no_glyph_missing` — `warnings.catch_warnings()` 로 Glyph missing 경고 0건 확인.

### 2C. baseline PNG 4장 추가

Codex가 생성한 8장에 더해, 다음 시나리오 baseline 필요:

| # | 시나리오 | 방법 |
|---|----------|------|
| 09 | tier=wildmesh 선택 후 WildMesh 튜닝 패널 표시 | `_engine_combo` 를 "wildmesh" 아이템 index로 설정 후 grab |
| 10 | 정책 wildmesh_only 활성화 후 드롭다운 | `engine_policy.set_mode("wildmesh_only")` + `_rebuild_engine_combo_model()` 후 grab |
| 11 | "WildMesh Fine" 프리셋 선택 후 슬라이더 상태 | `_preset_combo` setCurrentIndex + panel grab |
| 12 | 파일 드롭 후 지오메트리 힌트 표시 | `win.set_input_path(sphere.stl)` 후 grab |

**파일:** `tests/test_gui_visual.py` 4개 테스트 함수 추가.

---

## Phase 3 — 헤드리스 테스트 인프라 개선 (20분)

### 3A. PyVistaQt offscreen fixture 정리

**현재 상황:** `QtInteractor` 가 offscreen에서 native abort. Codex가 각 visual test에서 개별 monkeypatch로 우회 (`mesh_viewer.PYVISTAQT_AVAILABLE = False`). 중복 + 실수 여지.

**조치:** `tests/conftest.py` 에 autouse fixture 추가:

```python
@pytest.fixture(autouse=True)
def _force_static_viewer_in_offscreen(monkeypatch):
    """offscreen Qt에서 PyVistaQt QtInteractor가 abort하므로 정적 뷰어로 강제."""
    import os
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        try:
            from desktop.qt_app import mesh_viewer
            monkeypatch.setattr(mesh_viewer, "PYVISTAQT_AVAILABLE", False, raising=False)
        except Exception:
            pass
```

기존 테스트들에서 개별 monkeypatch 제거 가능하면 제거.

### 3B. `visual` pytest marker 문서화

`pyproject.toml` 에 추가된 `visual` marker 의미를 `TESTING.md` (없으면 신규) 또는 `tests/conftest.py` 주석에 명시.

### 3C. Signal 감사 범위 확장

Codex가 `test_signal_connections_completeness` 에 일부만 포함. 더 확장:
- `PipelineWorker.progress` / `progress_percent` / `quality_update` / `intermediate_ready` 연결
- `HistoryDialog` 상태 필터 combo signal
- `BatchDialog` 테이블 selection changed

---

## Phase 4 — 장기 백로그 (이번 세션 범위 밖)

### B1. Compare Mode
두 polyMesh 나란히 + 히스토그램 오버레이. 신규 `compare_dialog.py`, mesh_viewer 2 인스턴스.

### B2. `main_window.py` 분리
3300+ 줄 → `widgets/sidebar.py`, `widgets/menubar.py`, `main_window.py` 조립만. TierParamEditor 클래스 별도.

### B3. 온보딩 Wizard
첫 실행 감지 + sample STL 자동 로드 + 4-step 투어.

### C1. `_TIER_ALIASES` 동적 생성
`core/generator/pipeline.py` registry에서 자동 생성. 중복 제거.

### C2. `# pragma: no cover` 제거 가능한 경로 테스트 추가
`_on_save_current_as_preset`, `_on_open_history_dialog` 같은 것들.

### C3. 라이트/다크 테마 토글
`theme.py` 신규, `PALETTE` 2배, `~/.autotessell/gui_config.json`.

---

## Phase 5 — 추가 발굴 필요 (검증 후 상세화)

이번 세션에서 **실기계 WSL X11** 로 GUI 실제 실행해보면서 발견할 이슈들을 여기 수집.

- [ ] 사이드바 스크롤 실제 동작?
- [ ] 뷰포트 KPI 오버레이 실제 렌더?
- [ ] PyVistaQt 메시 로드 실제 동작?
- [ ] Tier 노드 클릭 파라미터 팝업?
- [ ] 배치/이력/에러 복구 다이얼로그 실제 크기·색상?
- [ ] 단축키 (Ctrl+N/O/S/E/B/H) 동작?

각 항목 확인 후 새 이슈면 Phase 1~3 비슷한 패턴으로 추가.

---

## 실행 순서 (추천)

| 순서 | Phase | 예상 시간 | 의존성 |
|------|-------|----------|--------|
| 1 | 1A + 1B (커밋 분리 + 외부 dir 정리) | 20분 | 없음 |
| 2 | 1C (push) | 2분 | 1 |
| 3 | 2B (glyph missing fix) | 10분 | 없음 |
| 4 | 3A (conftest autouse fixture) | 10분 | 2 |
| 5 | 2A (사이드바 스크롤 검증) | 10분 | 3 |
| 6 | 2C (baseline 4장 추가) | 15분 | 3,4 |
| 7 | 3B + 3C (문서 + signal 확장) | 10분 | 4,6 |
| 8 | 최종 push | 2분 | 7 |

**총: ~80분**. 이번 세션 끝나면 커밋 히스토리 깔끔 + baseline 12장 + 경고 0건.

---

## 검증

```bash
# 커밋 히스토리
git log --oneline 8a8c6d7..HEAD
# 기대: 7~9개 커밋, 태스크 단위 분리

# 테스트
python3 -m pytest tests/test_qt_app.py tests/test_gui_visual.py -q
# 기대: 180+ passed, 8 skipped

# Glyph 경고
python3 -m pytest tests/test_qt_app.py 2>&1 | grep -c "Glyph.*missing"
# 기대: 0

# Baseline 개수
ls tests/fixtures/screenshots/baselines/*.png | wc -l
# 기대: 12

# Working tree 깔끔
git status --porcelain | grep -v "^??"
# 기대: empty (untracked은 외부 dir만)
```

---

## 완료 조건 (Definition of Done)

- [ ] Phase 1 전부 완료: 7 커밋 origin/master 에 push
- [ ] Phase 2 전부 완료: 사이드바 검증 + glyph fix + 4 baseline 추가
- [ ] Phase 3 전부 완료: conftest fixture + signal 감사 확장
- [ ] 테스트 180+ passed
- [ ] `git status` working tree clean
- [ ] Baseline PNG 12장 git tracked
- [ ] 이 문서 하단에 "완료 기록" 섹션 추가

---

## 완료 기록 (세션 종료 시 작성)

<!-- 세션 끝나면 아래 채우기 -->

- 시작 commit: `8a8c6d7`
- 완료 commit: `미커밋 working tree (HEAD 8a8c6d7)`
- 최종 테스트: `180 passed, 8 skipped`
- Glyph missing 경고: `0 건`
- Baseline 개수: `12`
- 발견된 예상 외 이슈:
  - 엔진 콤보 모델이 `QStandardItem.setData(value)`로만 저장돼 `QComboBox.findData("wildmesh")`가 실패했다. `Qt.UserRole`에 명시 저장하도록 수정했고, `_rebuild_engine_combo_model()`의 선택 복원도 같은 role을 보도록 보정했다.
  - `QWidget.isVisible()`은 부모 top-level이 아직 show되지 않으면 false라 visual 테스트에서 `isHidden()` 기준으로 WildMesh 패널 표시 상태를 확인하도록 수정했다.
  - `grep -c "Glyph.*missing"`은 매치가 0개일 때 출력은 `0`이지만 exit code는 1이므로, 수치는 출력값 기준으로 기록했다.
- 다음 세션 이월 항목:
  - Phase 1의 태스크 단위 커밋 분리와 `git push origin master`는 아직 수행하지 않았다.
  - 실제 디스플레이/WSL X11에서 PyVistaQt 뷰포트 KPI 오버레이, 메시 로드, Tier 팝업, 단축키 동작은 별도 육안 검증이 필요하다.
