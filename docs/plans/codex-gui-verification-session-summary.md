# Codex GUI Verification Session Summary

**작성일:** 2026-04-19  
**기준 commit:** `8a8c6d7`  
**상태:** 구현 완료, 미커밋 working tree

## 완료한 작업

1. **GUI 시각 회귀 테스트 인프라 추가**
   - `tests/test_gui_visual.py` 추가.
   - Headless Qt `widget.grab()` 기반 PNG 캡처/비교 구현.
   - `tests/fixtures/screenshots/baselines/` 아래 baseline PNG 8개 생성.
   - `tests/fixtures/screenshots/actual/`은 생성물로 보고 `.gitignore`에 추가.
   - `visual` pytest marker와 `--skip-visual` 옵션 추가.

2. **엔진 정책 전환 UI 버그 수정**
   - `AutoTessellWindow._make_engine_combo_model()` 추가.
   - `AutoTessellWindow._rebuild_engine_combo_model()` 추가.
   - `_on_set_engine_policy()`에서 정책 저장 후 엔진 드롭다운을 즉시 재구성하도록 변경.
   - `wildmesh_only` 전환 시 차단 엔진에 `정책 차단` 마커와 disabled 상태가 즉시 반영됨.

3. **WildMesh 프리셋 → 슬라이더 동기화 버그 수정**
   - `_on_preset_selected()`에서 `preset.params` 중 `wildmesh_*` 키를 필터링해 `WildMeshParamPanel.set_params()`에 전달.
   - `WildMesh Draft`, `WildMesh Standard`, `WildMesh Fine (Feature Preserving)` 프리셋이 슬라이더 상태와 동기화됨.

4. **Signal/slot 연결 감사 테스트 추가**
   - DropZone click/drop, tier pipeline, WildMesh params, ExportPane save signal 연결을 테스트로 검증.
   - PySide6 `QObject.receivers()`가 `SignalInstance` 대신 `"2signalSignature"` 문자열을 요구하므로 테스트 헬퍼에 반영.

5. **다이얼로그 스타일 공통화**
   - `get_dialog_qss()`, `get_table_qss()`를 `desktop/qt_app/main_window.py`에 추가.
   - `BatchDialog`, `HistoryDialog`, `ErrorRecoveryDialog`의 하드코딩 QSS 일부를 PALETTE 기반 helper 사용으로 교체.

6. **Esc 키 모달 닫기 공통화**
   - `desktop/qt_app/widgets/dialog_mixin.py` 추가.
   - `EscDismissMixin`을 `BatchDialog`, `HistoryDialog`, `ErrorRecoveryDialog`에 적용.
   - 메인 윈도우의 단축키 다이얼로그와 Tier 파라미터 다이얼로그도 mixin 기반 임시 QDialog 클래스로 변경.

7. **핸드오프 문서 완료 기록 갱신**
   - `docs/plans/codex-handoff-gui-verification.md` 하단의 완료 기록을 실제 결과로 채움.

## 변경된 주요 파일

- `.gitignore`
- `pyproject.toml`
- `tests/conftest.py`
- `tests/test_qt_app.py`
- `tests/test_gui_visual.py`
- `tests/fixtures/screenshots/baselines/*.png`
- `desktop/qt_app/main_window.py`
- `desktop/qt_app/batch_dialog.py`
- `desktop/qt_app/history_dialog.py`
- `desktop/qt_app/error_recovery.py`
- `desktop/qt_app/widgets/dialog_mixin.py`
- `docs/plans/codex-handoff-gui-verification.md`

## 검증 결과

```bash
python3 -m pytest tests/test_qt_app.py tests/test_gui_visual.py -q
# 171 passed, 8 skipped, 1 warning

timeout 120 python3 -m pytest tests/test_qt_app.py -k "wildmesh or preset or history or batch" -q
# 39 passed

timeout 120 python3 -m pytest tests/test_qt_app.py -m slow -q
# 4 passed

python3 -m pytest tests/test_qt_app.py 2>&1 | grep -c "Glyph.*missing"
# 1
```

## 예상 외 이슈와 처리

- Headless/offscreen 환경에서 PyVistaQt `QtInteractor` 초기화가 Python 예외가 아니라 native abort를 유발했다.
- 신규 main-window GUI 테스트와 visual baseline 생성에서는 `mesh_viewer.PYVISTAQT_AVAILABLE=False`를 monkeypatch해 정적 viewer fallback을 강제했다.
- 기존 워크트리에는 작업 전부터 추적되지 않은 대형 외부 디렉터리와 `.claude/scheduled_tasks.lock` 삭제 상태가 있었다. 이번 작업은 관련 GUI/test/docs 파일만 수정했다.

## 다음 권장 작업

1. 실제 디스플레이 환경에서 baseline PNG 8개를 눈으로 확인한다.
2. 변경 파일만 선별해 커밋한다. 기존 미추적 외부 디렉터리는 커밋 대상에서 제외한다.
3. 원래 핸드오프 규칙을 따르려면 task 단위로 커밋을 나눌 수 있다. 현재는 한 번에 구현된 미커밋 상태다.
