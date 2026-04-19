# AutoTessell 다음 단계 (Phase 3) 계획
**작성일:** 2026-04-19
**기반 commit:** `8a8c6d7`
**직전 세션들:**
- `docs/plans/codex-gui-verification-session-summary.md` (Session 1)
- `docs/plans/codex-next-steps-session-summary.md` (Session 2)

---

## Context — 지금 어디 와 있나

**Codex가 두 세션 연속 돌려서 쌓은 성과:**
- 테스트: 148 → 171 → **180 passed**, 8 skipped
- Baseline PNG: 0 → 8 → **12**장
- Glyph missing 경고: 85 → 1 → **0**건
- 신규 인프라: visual regression + offscreen fixture + Esc mixin + 공통 QSS + signal 감사

**실제 baseline 육안 확인 (직접 PNG 열어봄):**
- `01_empty_mainwindow.png`: UI 레이아웃 정상, 한글 렌더 OK ✓
- `10_engine_policy_wildmesh_only_dropdown.png`: 🔒 정책 차단 마커 + WildMesh만 활성 ✓
- `11_wildmesh_fine_preset_slider_sync.png`: epsilon=0.0003, edge=0.020, quality=5, iter=120 슬라이더 동기화 ✓

**Codex 세션의 공통 미해결 이슈 (양 세션 연속 스킵):**
1. ❌ **태스크 단위 커밋 분리 안 됨** — 2 세션 분량 작업이 미커밋 working tree에 쌓임
2. ❌ **`git push origin master` 안 됨**
3. ❌ **실기계 WSL X11/Windows 육안 검증 안 됨** — PyVistaQt 오버레이·메시로드·Tier 팝업·단축키

**현재 working tree 상태:**
```
 M .gitignore                       (외부 dir 제외)
 M desktop/qt_app/batch_dialog.py   (Esc mixin + selection signal)
 M desktop/qt_app/error_recovery.py (Esc mixin + QSS)
 M desktop/qt_app/history_dialog.py (Esc mixin + QSS)
 M desktop/qt_app/main_window.py    (정책 리빌드 + 프리셋 동기 + QSS helper + Esc)
 M desktop/qt_app/report_pdf.py     (체크마크 glyph fix)
 M pyproject.toml                   (visual marker)
 M tests/conftest.py                (offscreen PyVistaQt fixture)
 M tests/test_qt_app.py             (Task 1B/1C/1D/3A/3B 테스트)
?? TESTING.md                       (Codex visual marker 문서화)
?? desktop/qt_app/widgets/dialog_mixin.py  (신규)
?? docs/plans/                      (4개 plan/summary)
?? tests/fixtures/screenshots/      (12 baseline PNG + .gitignore)
?? tests/test_gui_visual.py         (신규)
```

---

## 목표

**이번 세션 outcome:**
1. **2 세션 분량 미커밋 작업을 태스크 단위 6 커밋으로 분리 + push** (가장 중요)
2. **실기계 육안 검증** (Windows 또는 WSL X11) — 체크리스트 10개 항목
3. **B-Tier 시작 — Compare Mode** (두 메쉬 나란히 diff)

**이번 세션 범위 밖:** `main_window.py` 분리, 온보딩 Wizard, 라이트/다크 테마

---

## Phase 1 — 커밋 + 배포 정리 (CRITICAL, 30분)

**Iron rule:** 이 Phase 안 끝내면 Phase 2~3로 넘어가지 않는다. 세션이 하나 더 쌓이면 bisect/revert 불가능해진다.

### 1A. 태스크 단위 6 커밋으로 분리

**커밋 구성 (원래 7개를 6개로 통합 — docs는 별도):**

**커밋 1 — `test(qt-gui): visual regression infra + 12 baselines`**
```
A .gitignore                                          (tests/fixtures/screenshots/actual 제외 + 외부 dir)
A pyproject.toml                                      (visual marker)
A TESTING.md                                          (visual marker 문서화)
A tests/conftest.py                                   (offscreen PyVistaQt autouse fixture)
A tests/test_gui_visual.py                            (신규)
A tests/fixtures/screenshots/baselines/01~12.png      (12 PNG)
A tests/fixtures/screenshots/.gitignore               (actual/ 제외)
```

**커밋 2 — `fix(qt-gui): engine policy switch rebuilds dropdown + data role`**
```
M desktop/qt_app/main_window.py
  - _make_engine_combo_model (신규)
  - _rebuild_engine_combo_model (신규)
  - Qt.UserRole data 저장 (data role bug fix)
  - _on_set_engine_policy가 rebuild 호출
M tests/test_qt_app.py
  - test_engine_policy_switch_rebuilds_dropdown
```

**커밋 3 — `fix(qt-gui): preset selection syncs WildMesh slider panel`**
```
M desktop/qt_app/main_window.py
  - _on_preset_selected에서 preset.params 중 wildmesh_* 필터링해 panel.set_params()
M tests/test_qt_app.py
  - test_preset_wildmesh_fine_syncs_slider_panel
```

**커밋 4 — `refactor(qt-gui): unified dialog QSS + Esc dismiss`**
```
A desktop/qt_app/widgets/dialog_mixin.py
M desktop/qt_app/main_window.py                       (get_dialog_qss, get_table_qss helper)
M desktop/qt_app/batch_dialog.py                      (EscDismissMixin + get_dialog_qss)
M desktop/qt_app/history_dialog.py                    (동일)
M desktop/qt_app/error_recovery.py                    (동일)
M tests/test_qt_app.py
  - test_dialog_qss_uses_palette
  - test_esc_dismisses_batch_dialog (등)
```

**커밋 5 — `fix(qt-gui): report PDF glyph fix + BatchDialog selection`**
```
M desktop/qt_app/report_pdf.py                        (✓/✗ → [OK]/[FAIL])
M desktop/qt_app/batch_dialog.py                      (itemSelectionChanged 핸들러)
M tests/test_qt_app.py
  - test_report_pdf_no_glyph_missing_warning
  - test_batch_dialog_selection_enables_remove
```

**커밋 6 — `test(qt-gui): signal audit expansion + sidebar scroll verification`**
```
M tests/test_qt_app.py
  - test_signal_connections_completeness (PipelineWorker, HistoryDialog)
  - test_sidebar_uses_scroll_area
  - test_export_pane_signal_wired
```

**커밋 7 (마지막) — `docs: GUI 검증 Phase 1/2 + 다음 계획`**
```
A docs/plans/codex-handoff-gui-verification.md        (완료 기록 포함)
A docs/plans/codex-gui-verification-session-summary.md
A docs/plans/next-steps-2026-04-19.md                 (완료 기록 포함)
A docs/plans/codex-next-steps-session-summary.md
A docs/plans/next-steps-phase3-2026-04-19.md          (이 파일)
```

**기법:** `git add -p` 또는 `git stash` → 차례로 unstash 후 add/commit. 각 커밋 후 `python3 -m pytest tests/test_qt_app.py tests/test_gui_visual.py -q` 실행해 180 passed 유지.

### 1B. Push
```bash
git log --oneline 8a8c6d7..HEAD
# 기대: 7 커밋, 태스크 단위로 분리됨
git push origin master
```

### 완료 조건
- `git status --porcelain | grep -v "^??"` empty
- `git log --oneline 8a8c6d7..HEAD` 7 커밋
- origin/master 7 커밋 앞

---

## Phase 2 — 실기계 육안 검증 (30분)

Codex는 offscreen만 돌림. 실제 OpenGL 컨텍스트가 있는 환경에서만 확인 가능한 것들이 남아 있음.

### 사전 조건
- WSL: `DISPLAY=:0` 에서 X11 forwarding 동작 확인
- 또는 Windows 실기계 (NSIS 인스톨러 빌드판 사용)

### 2A. QA 체크리스트 v2 — 10 항목

`.gstack/qa-reports/qa-manual-2026-04-19.md` 에 결과 기록.

| # | 항목 | 검증 방법 | 기대 |
|---|------|----------|------|
| 1 | GUI 실행 | `python3 -m desktop.qt_app` | 메인 윈도우 정상 표시 |
| 2 | PyVistaQt 뷰포트 렌더 | 메인 윈도우의 중앙 3D 영역 | VTK 검정 배경 + 좌표축 |
| 3 | `sphere.stl` 드롭 | 드래그 → 뷰포트 | 구 메시 로드 + 지오메트리 힌트 로그 |
| 4 | KPI 오버레이 가시성 | 뷰포트 우상단 | `Cells / Tier / Time / Hex%` 박스 |
| 5 | 파이프라인 실행 (draft) | "실행" 클릭 | Tier 노드 순차 active + 완료시 mesh reload |
| 6 | Quality 탭 히스토그램 | 실행 후 | 3 subplot (aspect/skew/non-ortho) 렌더 |
| 7 | 엔진 정책 전환 | "엔진 정책 → WildMesh 전용" | 드롭다운 🔒 마커 즉시 반영 |
| 8 | Tier 노드 클릭 팝업 | 하단 strip 노드 클릭 | 읽기 전용 파라미터 다이얼로그 |
| 9 | 키보드 단축키 | Ctrl+N/O/S/E/B/H | 각 액션 실제 동작 |
| 10 | 에러 복구 다이얼로그 | 불량 STL 시도 | Esc 닫힘, 복구 액션 버튼 동작 |

### 2B. 실기계 스크린샷 캡처
각 항목 스크린샷을 `docs/qa-reports/screenshots-2026-04-19/` 저장. Phase 1B 이후 commit + push.

### 2C. 발견 이슈 처리
- 저위험 (색상·폰트): 즉시 fix commit
- 고위험 (동작 안 됨): `docs/plans/` 에 신규 계획 파일 작성해 다음 세션에서 처리

---

## Phase 3 — B-Tier 시작: Compare Mode (90분)

사용자가 이전 세션에서 "파라미터 스윕 다음 자연스러운 단계"로 우선순위 1번 지적했던 기능.

### 시나리오
사용자가 배치 처리로 같은 STL을 epsilon=[0.001, 0.0005] 두 가지로 돌렸다. 각 case 디렉토리의 polyMesh 를 비교하고 싶음. 지금은:
- 각 case 뷰포트 로드 → 품질 탭 확인 → 수동 메모 → 전환
- 매번 재로드, 직접 비교 불가

Compare Mode면:
- 두 case 폴더 선택 → 좌/우 분할 뷰
- 동시 카메라 동기
- 하단 히스토그램 오버레이 (A/B 곡선)
- 통계 테이블 (min/max/median 대비)

### 3A. 신규 파일 `desktop/qt_app/compare_dialog.py`

```python
class CompareDialog(EscDismissMixin, QDialog):
    """두 polyMesh 나란히 비교.

    구성:
    - 상단: A 경로 선택 | B 경로 선택 (QLineEdit + "⋯" 버튼)
    - 중단: 좌/우 mesh_viewer 2 인스턴스 (수평 splitter)
    - 카메라 동기 체크박스
    - 하단: 히스토그램 overlay (3 메트릭, A=파랑 + B=주황)
    - 통계 테이블 (4행 × 4열: metric | A | B | diff)
    """
```

### 3B. `main_window.py` 메뉴 추가
"도구" 메뉴 (신설) → "메시 비교…" (Ctrl+D) → `_on_open_compare_dialog()`

### 3C. 카메라 동기
각 `InteractiveMeshViewer` 의 camera `position/focal_point/view_up` 을 Signal로 노출 → 반대편 viewer camera에 mirror.

### 3D. 히스토그램 오버레이
`_HistogramCanvas.update_histograms()` 를 확장해 `compare_mode=True`, `data_a` / `data_b` 둘 다 받기. 각 subplot에 A=파랑/B=주황 alpha 0.55 hist.

### 3E. 테스트
- `test_compare_dialog_loads_two_cases` (mock 두 case_dir)
- `test_compare_dialog_camera_sync` (A camera 변경 → B 동기)
- `test_compare_dialog_histogram_overlay`
- Visual baseline `13_compare_dialog_two_cases.png`

### 완료 조건
- 180 → 185+ passed
- Ctrl+D로 다이얼로그 열림
- sphere.stl 두 번 다른 epsilon으로 배치 처리 → Compare Mode에서 정상 비교

---

## Phase 4 — 기술부채 (선택, 45분)

### 4A. `_TIER_ALIASES` 중복 제거
**파일:** `core/generator/pipeline.py:60~107`

현재:
```python
_TIER_ALIASES: dict[str, str] = {
    "2d": "tier0_2d_meshpy",
    ...
    # 정규 이름 자체도 재등록 (line 77~91)
    "tier0_2d_meshpy": "tier0_2d_meshpy",  # 불필요
    ...
}
```

**수정:** registry 기반 동적 생성:
```python
_SHORT_TO_CANONICAL = {
    "2d": "tier0_2d_meshpy",
    "hex": "tier_hex_classy_blocks",
    ...
}
_TIER_ALIASES = {
    **{name: name for name in _TIER_REGISTRY},  # 정규 이름 자체
    **_SHORT_TO_CANONICAL,                       # 짧은 이름 별칭
}
```

**테스트:** 모든 canonical name 및 기존 short name 전부 resolve 되는지 회귀 테스트.

### 4B. Signal 감사 범위 완전성 (Task 1D 확장)
`test_signal_connections_completeness` 에:
- `ViewportChromeOverlay.view_mode_changed` / `screenshot_requested`
- `MeshViewerWidget.mesh_stats_computed`
- `_HistogramCanvas` canvas signals

---

## Phase 5 — 장기 백로그 (다음 세션)

### B2. `main_window.py` 3300+줄 분리
- `widgets/sidebar.py` — 사이드바 전체
- `widgets/menubar.py` — 메뉴바
- `widgets/tier_param_editor.py` — TierParamEditor
- `main_window.py` — 조립만

### B3. 온보딩 Wizard
- 첫 실행 감지 (`~/.autotessell/onboarded.flag`)
- 샘플 STL auto-load
- 4-step tour (drop → preset → run → export)

### C3. 라이트/다크 테마 토글
- `theme.py` 신규, `PALETTE` 2배
- `~/.autotessell/gui_config.json`
- 메뉴 "보기 → 테마"

---

## 실행 순서 (추천)

| 순서 | Phase | 예상 시간 | 의존성 |
|------|-------|----------|--------|
| 1 | **Phase 1 전부** (커밋 분리 + push) | 30분 | 없음 |
| 2 | Phase 2 (실기계 QA, 사용자가 직접 실행) | 30분 | 1 |
| 3 | Phase 3A~C (Compare Mode 기본 구조) | 45분 | 1 |
| 4 | Phase 3D~E (히스토그램 + 테스트) | 45분 | 3 |
| 5 | Phase 4 (선택) | 45분 | 1 |
| 6 | 최종 push | 2분 | 나머지 |

**총 권장: ~2.5시간**. 끝나면 커밋 히스토리 깔끔 + Compare Mode 동작 + 실기계 QA 증거.

---

## 검증 (Phase별)

### Phase 1
```bash
git log --oneline 8a8c6d7..HEAD | wc -l           # 7
git status --porcelain | grep -v "^??"            # empty
python3 -m pytest tests/test_qt_app.py tests/test_gui_visual.py -q   # 180 passed
```

### Phase 2
- `.gstack/qa-reports/qa-manual-2026-04-19.md` 작성됨
- `docs/qa-reports/screenshots-2026-04-19/*.png` 10+장

### Phase 3
```bash
python3 -m pytest tests/test_qt_app.py -k compare -q   # 4+ passed
find tests/fixtures/screenshots/baselines -name "13_*.png"   # 1 match
```

---

## 완료 조건 (Definition of Done)

- [ ] Phase 1: 7 커밋 origin/master 에 push, working tree clean
- [ ] Phase 2: 10 항목 QA 결과 문서 + 스크린샷
- [ ] Phase 3: Compare Mode 메뉴 + 다이얼로그 + 카메라 동기 + 히스토그램 overlay
- [ ] 테스트 185+ passed
- [ ] Baseline PNG 13+장
- [ ] 이 문서 하단 "완료 기록" 섹션 추가

---

## Codex 실행 팁

**핸드오프 시:**
```bash
codex exec "docs/plans/next-steps-phase3-2026-04-19.md 를 읽고 Phase 1부터 순서대로 실행해줘. 각 커밋은 개별 진행하고 매 커밋 후 테스트 통과 확인. Phase 2는 실기계 필요하니까 Codex는 스킵하고 Phase 3로 넘어가."
```

**또는 Claude Code:**
1. 이 파일 읽고 Phase 1만 먼저 (commit 분리)
2. 사용자가 Phase 2 수행
3. 결과 공유 후 Phase 3 시작

---

## 완료 기록 (세션 종료 시 작성)

<!-- 세션 끝나면 아래 채우기 -->

- 시작 commit: `8a8c6d7`
- 완료 commit: `미커밋 working tree (HEAD 8a8c6d7)`
- 최종 테스트: `185 passed, 8 skipped`
- Baseline 개수: `13`
- Compare Mode: `기본 구현 완료`
  - `desktop/qt_app/compare_dialog.py` 신규.
  - `도구 → 메시 비교…` 메뉴와 `Ctrl+D` 단축키 추가.
  - 두 case/mesh 경로 선택, 좌우 viewer, 카메라 동기 체크박스, A/B histogram overlay, metric diff table 구현.
  - `tests/test_qt_app.py -k compare` 기준 4개 테스트 통과.
  - visual baseline `13_compare_dialog_two_cases.png` 추가.
- 실기계 QA: `미수행`
- 다음 세션 이월 항목:
  - Phase 1의 태스크 단위 커밋 분리와 `git push origin master`.
  - 실제 디스플레이/WSL X11에서 PyVistaQt Compare Mode 카메라 동기, 실제 polyMesh 로딩, KPI overlay 육안 검증.
  - Compare Mode의 실제 PyVista camera callback 기반 양방향 동기화 고도화.
