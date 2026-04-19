# Codex 핸드오프: AutoTessell GUI 작동·렌더링 검증

**생성일:** 2026-04-19
**대상:** Codex CLI 또는 Claude Code agent (자립 실행 가능)
**저장소:** https://github.com/younglin90/AutoTessell  브랜치: `master`  base commit: `8a8c6d7`

---

## Context (Codex 가 먼저 읽을 것)

AutoTessell은 CFD용 자동 메쉬 생성 Qt 데스크톱 앱이다. 최근 3개 세션에 걸쳐 기능을 크게 확장했다:

- **WildMesh-only 엔진 정책** (다른 엔진 fallback 차단) — `desktop/qt_app/engine_policy.py`, `core/strategist/tier_selector.py`
- **WildMesh 파라미터 슬라이더 패널** — `desktop/qt_app/widgets/wildmesh_param_panel.py`
- **파라미터 스냅샷 히스토리** — `desktop/qt_app/param_history.py`
- **실시간 유효성 검증 위젯** — `desktop/qt_app/widgets/param_validator.py`
- **배치 처리 다이얼로그** — `desktop/qt_app/batch_dialog.py`
- **실행 이력 대시보드** — `desktop/qt_app/history_dialog.py`
- **에러 복구 다이얼로그** — `desktop/qt_app/error_recovery.py`
- **WildMesh preflight** — `desktop/qt_app/wildmesh_preflight.py`

**현재 테스트:** 148 passed, 8 skipped (전부 구조·signal 검증, 실제 렌더 검증 없음).

**문제:** 위젯들이 **화면에 실제로 제대로 나오는지** 검증된 적이 없고, 최근 추가된 상호작용 (정책 전환 → 드롭다운 갱신, 프리셋 선택 → 슬라이더 동기) 의 실시간 반영 여부도 확인 안 됨.

**목표 outcome:** Codex 세션 종료 시점에:
1. 헤드리스 Qt에서 자동으로 8 화면 스크린샷 PNG 저장 + baseline 등록
2. 최근 발견된 UI 상호작용 버그 2건 수정 (1B, 1C)
3. 다이얼로그 스타일시트 PALETTE 통합 (3A)
4. Esc 키 모달 닫기 + focus 처리 (3B)
5. 테스트 148 → 170+ passed

---

## 환경 / 사전 조건

```bash
# 프로젝트 루트
cd /home/younglin90/work/claude_code/AutoTessell

# 헤드리스 Qt (필수 — 기존 tests/conftest.py가 강제 설정)
export QT_QPA_PLATFORM=offscreen

# 테스트 명령
python3 -m pytest tests/test_qt_app.py -q

# 기대: 148 passed, 8 skipped
```

**의존성:** PySide6 6.11+, pytest-qt, matplotlib, trimesh. 이미 설치됨.

**작업 규칙:**
- 한 태스크 = 한 커밋
- 커밋 메시지 prefix: `feat(qt-gui):`, `test(qt-gui):`, `fix(qt-gui):`, `refactor(qt-gui):`
- 매 커밋 후 `python3 -m pytest tests/test_qt_app.py -q` 실행 → regression 0건 확인
- 모든 태스크 완료 후 `git push origin master`

---

## Task 1A — 스크린샷 회귀 테스트 인프라 (최우선)

### 목표
헤드리스 Qt에서 `widget.grab()` 으로 PNG 저장 + baseline 비교. 향후 UI 변경시 시각적 회귀 자동 감지.

### 구현

**1. 신규 파일 `tests/fixtures/screenshots/baselines/`** (git 트래킹) 에 baseline PNG 저장

**2. 신규 테스트 `tests/test_gui_visual.py`:**

```python
"""GUI 시각 회귀 — 헤드리스에서 widget.grab() PNG baseline 비교."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# 헤드리스 강제
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 시각 테스트 전용 마크 — CI에서 --skip-visual 로 제외 가능
pytestmark = pytest.mark.visual

_BASELINE_DIR = Path(__file__).parent / "fixtures" / "screenshots" / "baselines"
_ACTUAL_DIR = Path(__file__).parent / "fixtures" / "screenshots" / "actual"
_PIXEL_TOLERANCE = 0.02  # 2% 이내 차이 허용


def _compare_or_save(widget, name: str, size: tuple[int, int] = (1400, 900)) -> None:
    """widget을 size로 resize → grab → PNG로 저장. baseline 있으면 비교."""
    from PySide6.QtGui import QPixmap

    _ACTUAL_DIR.mkdir(parents=True, exist_ok=True)
    widget.resize(*size)
    widget.show()  # offscreen에서도 grab 가능
    pix: QPixmap = widget.grab()
    actual = _ACTUAL_DIR / f"{name}.png"
    pix.save(str(actual), "PNG")

    baseline = _BASELINE_DIR / f"{name}.png"
    if not baseline.exists():
        # 첫 실행: baseline 등록
        _BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        pix.save(str(baseline), "PNG")
        pytest.skip(f"baseline 새로 생성: {baseline}")

    # 간단 byte-level 비교 (pixel-perfect)
    a_bytes = actual.read_bytes()
    b_bytes = baseline.read_bytes()
    if a_bytes == b_bytes:
        return

    # numpy 로 pixel-level 차분 (허용 오차 2%)
    try:
        import numpy as np
        from PIL import Image

        a_img = np.array(Image.open(actual).convert("RGB"))
        b_img = np.array(Image.open(baseline).convert("RGB"))
        if a_img.shape != b_img.shape:
            pytest.fail(f"크기 불일치: actual={a_img.shape} baseline={b_img.shape}")
        diff = np.abs(a_img.astype(int) - b_img.astype(int))
        diff_ratio = (diff > 10).sum() / diff.size
        if diff_ratio > _PIXEL_TOLERANCE:
            pytest.fail(
                f"{name}: pixel diff {diff_ratio*100:.2f}% > {_PIXEL_TOLERANCE*100}%. "
                f"actual={actual}, baseline={baseline}"
            )
    except ImportError:
        # numpy/PIL 없으면 byte 비교 실패만 fail
        pytest.fail(f"{name}: byte mismatch and numpy/PIL unavailable")


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_visual_empty_mainwindow(qt_app, tmp_path) -> None:
    """빈 메인 윈도우 — DropZone 초기 상태."""
    from desktop.qt_app.main_window import AutoTessellWindow
    win = AutoTessellWindow()
    win._build()
    _compare_or_save(win._qmain, "01_empty_mainwindow")


def test_visual_wildmesh_param_panel_draft(qt_app) -> None:
    """WildMesh 슬라이더 패널 draft 프리셋."""
    from desktop.qt_app.widgets.wildmesh_param_panel import WildMeshParamPanel
    panel = WildMeshParamPanel()
    panel.apply_preset("draft")
    _compare_or_save(panel, "02_wildmesh_panel_draft", size=(280, 300))


def test_visual_wildmesh_param_panel_fine(qt_app) -> None:
    """WildMesh 슬라이더 패널 fine 프리셋."""
    from desktop.qt_app.widgets.wildmesh_param_panel import WildMeshParamPanel
    panel = WildMeshParamPanel()
    panel.apply_preset("fine")
    _compare_or_save(panel, "03_wildmesh_panel_fine", size=(280, 300))


def test_visual_batch_dialog_empty(qt_app) -> None:
    """배치 다이얼로그 초기 상태."""
    from desktop.qt_app.batch_dialog import BatchDialog
    d = BatchDialog()
    _compare_or_save(d, "04_batch_dialog_empty", size=(960, 640))


def test_visual_history_dialog_empty(qt_app, tmp_path, monkeypatch) -> None:
    """실행 이력 다이얼로그 (empty)."""
    from desktop.qt_app import history
    monkeypatch.setattr(history, "_HISTORY_DIR", tmp_path / "x")
    monkeypatch.setattr(history, "_HISTORY_FILE", tmp_path / "x" / "h.json")

    from desktop.qt_app.history_dialog import HistoryDialog
    d = HistoryDialog()
    _compare_or_save(d, "05_history_dialog_empty", size=(960, 640))


def test_visual_error_recovery_watertight(qt_app) -> None:
    """에러 복구 다이얼로그 — watertight 패턴."""
    from desktop.qt_app.error_recovery import (
        ErrorRecoveryDialog, RecoveryAction, classify_error,
    )
    classified = classify_error("WildMesh는 watertight surface를 요구합니다")
    assert classified is not None
    guide, actions = classified
    d = ErrorRecoveryDialog(
        error_message="test trace",
        guide_text=guide,
        actions=actions,
    )
    _compare_or_save(d, "06_error_recovery_watertight", size=(720, 520))


def test_visual_quality_pane_with_histogram(qt_app) -> None:
    """Quality 탭 — 히스토그램 3 subplot (샘플 데이터)."""
    from desktop.qt_app.widgets.right_column import QualityPane
    pane = QualityPane()
    if hasattr(pane, "histogram"):
        pane.histogram.update_histograms(
            aspect_data=[1.0 + 0.05 * i for i in range(200)],
            skew_data=[0.01 * i for i in range(200)],
            non_ortho_data=[10.0 + 0.3 * i for i in range(200)],
        )
    pane.set_metric("aspect", 0.3, "3.5")
    pane.set_metric("skew", 0.2, "0.4")
    pane.set_metric("nonortho", 0.5, "45.0")
    _compare_or_save(pane, "07_quality_pane_with_histogram", size=(360, 760))


def test_visual_keyboard_shortcuts(qt_app) -> None:
    """키보드 단축키 다이얼로그."""
    from desktop.qt_app.main_window import AutoTessellWindow
    win = AutoTessellWindow()
    win._build()
    # 단축키 다이얼로그만 따로 캡처는 modal 관계로 어려움 → main window 대신
    # 핵심 UI 요소 확인만
    _compare_or_save(win._qmain, "08_mainwindow_after_build", size=(1400, 900))
```

### 검증

```bash
# 첫 실행 — baseline 생성 (모두 skip)
python3 -m pytest tests/test_gui_visual.py -v

# git diff tests/fixtures/screenshots/baselines/ 로 PNG 확인
# 직접 PNG 열어서 "레이아웃이 납득 가능한지" 시각 확인

# 두 번째 실행 — 전부 pass
python3 -m pytest tests/test_gui_visual.py -v
# 기대: 8 passed (또는 8 skipped if first run)
```

### 커밋

```bash
git add tests/test_gui_visual.py tests/fixtures/screenshots/
git commit -m "test(qt-gui): Task 1A — 8-screen visual baseline (headless grab)"
```

---

## Task 1B — 엔진 정책 전환 실시간 리빌드 (Bug Fix)

### 현재 버그 가설

`_on_set_engine_policy("wildmesh_only")` 호출 시 드롭다운 model이 재구성되지 않아 🔒 마커가 업데이트 안 됨. `_build_section_engine` 은 `_build_sidebar()` 에서 한 번만 호출됨.

### 재현

```bash
AUTOTESSELL_ENGINE_POLICY=all python3 -m desktop.qt_app
# 메뉴 → 엔진 정책 → "WildMesh 전용"
# 사이드바 엔진 드롭다운 클릭
# 기대: wildmesh 외 다른 엔진에 🔒 표시
# 실제: 🔒 없음 (재구성 안 됨)
```

### 구현

**파일:** `desktop/qt_app/main_window.py`

1. `_engine_combo` model을 재구성하는 헬퍼 `_rebuild_engine_combo_model()` 추출:
   - `_build_section_engine` 의 model 구성 로직을 이 함수로 분리
   - `_engine_combo.setModel(new_model)` 로 교체
   - 현재 선택 보존

2. `_on_set_engine_policy` 에서 정책 변경 후 `self._rebuild_engine_combo_model()` 호출

### 테스트 추가

`tests/test_qt_app.py` 에 추가:

```python
def test_engine_policy_switch_rebuilds_dropdown(monkeypatch, tmp_path) -> None:
    """정책 변경시 드롭다운 disabled 아이템 수가 바뀌어야 한다."""
    from desktop.qt_app import engine_policy
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "x")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "x" / "p.json")
    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)

    win = AutoTessellWindow()
    win._build()
    assert win._engine_combo is not None

    def _count_enabled() -> int:
        model = win._engine_combo.model()
        enabled = 0
        for i in range(model.rowCount()):
            item = model.item(i)
            if item and item.isEnabled():
                enabled += 1
        return enabled

    before = _count_enabled()
    # 정책 전환
    engine_policy.set_mode("wildmesh_only")
    win._rebuild_engine_combo_model()
    after = _count_enabled()

    # wildmesh_only는 wildmesh 외 모두 disabled → 활성 수 대폭 감소
    assert after < before
    # 최소 auto + wildmesh 는 활성
    assert after >= 2
```

### 검증 + 커밋

```bash
python3 -m pytest tests/test_qt_app.py::test_engine_policy_switch_rebuilds_dropdown -v
git add desktop/qt_app/main_window.py tests/test_qt_app.py
git commit -m "fix(qt-gui): Task 1B — engine policy switch rebuilds dropdown model"
```

---

## Task 1C — 프리셋 → WildMesh 슬라이더 동기화 (Bug Fix)

### 현재 버그 가설

`_on_preset_selected` 에서 "WildMesh Draft" 프리셋 선택해도 `_wildmesh_param_panel` 의 슬라이더가 업데이트 안 됨. `preset.params` dict (wildmesh_epsilon 등) 를 `panel.set_params()` 에 전달하지 않음.

### 재현

```bash
python3 -m desktop.qt_app
# 사이드바 프리셋 드롭다운 → "WildMesh Fine (Feature Preserving)" 선택
# 기대: 슬라이더가 epsilon=0.0003, edge=0.02, quality=5, its=200 으로 이동
# 실제: 슬라이더 그대로 (draft 기본값)
```

### 구현

**파일:** `desktop/qt_app/main_window.py` `_on_preset_selected` 메서드

프리셋 params 에 wildmesh_* 키가 있으면 panel.set_params() 호출:

```python
# 기존 로직 뒤에 추가:
if (
    preset.tier_hint == "wildmesh"
    and self._wildmesh_param_panel is not None
    and preset.params
):
    try:
        # 프리셋 params 중 wildmesh_ 로 시작하는 것만 필터링
        wm_params = {
            k: v for k, v in preset.params.items()
            if k.startswith("wildmesh_")
        }
        if wm_params:
            self._wildmesh_param_panel.set_params(wm_params)
    except Exception:
        pass
```

### 테스트 추가

```python
def test_preset_wildmesh_fine_syncs_slider_panel(monkeypatch, tmp_path) -> None:
    """WildMesh Fine 프리셋 선택 → 슬라이더 값이 epsilon=0.0003 등으로 동기."""
    from desktop.qt_app import engine_policy, recent_files
    from desktop.qt_app.main_window import AutoTessellWindow
    from desktop.qt_app.presets import get

    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "ep")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "ep" / "p.json")

    win = AutoTessellWindow()
    win._build()

    preset = get("WildMesh Fine (Feature Preserving)")
    assert preset is not None

    # 프리셋 콤보에서 찾아 선택
    for i in range(win._preset_combo.count()):
        if win._preset_combo.itemData(i) == preset.name:
            win._preset_combo.setCurrentIndex(i)
            break

    # 슬라이더 값 확인
    cur = win._wildmesh_param_panel.current_params()
    assert abs(cur["wildmesh_epsilon"] - 0.0003) < 1e-4
    assert abs(cur["wildmesh_edge_length_r"] - 0.02) < 1e-3
    assert int(cur["wildmesh_stop_quality"]) == 5
```

### 검증 + 커밋

```bash
python3 -m pytest tests/test_qt_app.py::test_preset_wildmesh_fine_syncs_slider_panel -v
git add desktop/qt_app/main_window.py tests/test_qt_app.py
git commit -m "fix(qt-gui): Task 1C — preset selection syncs WildMesh slider panel"
```

---

## Task 1D — Signal/slot 연결 감사

### 구현

`tests/test_qt_app.py` 에 추가 (대량 테스트):

```python
def test_signal_connections_completeness() -> None:
    """최근 위젯 주요 signal이 실제로 receiver를 갖고 있어야 한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    win._build()

    # (widget_attr_path, signal_name, min_receivers)
    checks = [
        ("_drop_label", "clicked", 1),
        ("_drop_label", "file_dropped", 1),
        ("_tier_pipeline", "tier_clicked", 1),
        ("_tier_pipeline", "resume_requested", 1),
        ("_tier_pipeline", "stop_requested", 1),
        ("_tier_pipeline", "rerun_requested", 1),
        ("_wildmesh_param_panel", "params_changed", 1),
    ]
    for attr, sig_name, min_r in checks:
        parts = attr.split(".")
        obj = win
        for p in parts:
            obj = getattr(obj, p, None)
            if obj is None:
                break
        if obj is None:
            continue
        signal = getattr(obj, sig_name, None)
        if signal is None:
            continue
        try:
            receivers = obj.receivers(signal)
        except Exception:
            continue
        assert receivers >= min_r, (
            f"{attr}.{sig_name} receivers={receivers} < {min_r}"
        )


def test_export_pane_signal_wired() -> None:
    """ExportPane.save_requested → main_window handler 연결 확인."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    win._build()
    if win._right_column is None:
        pytest.skip("right_column 없음")
    pane = win._right_column.export_pane
    receivers = pane.receivers(pane.save_requested)
    assert receivers >= 1
```

### 커밋

```bash
python3 -m pytest tests/test_qt_app.py -k "signal" -v
git add tests/test_qt_app.py
git commit -m "test(qt-gui): Task 1D — signal/slot wiring completeness audit"
```

---

## Task 3A — 다이얼로그 스타일시트 PALETTE 통합 (Bug Fix)

### 현재 문제

`error_recovery.py:130`, `batch_dialog.py:60`, `history_dialog.py:34`, `batch_dialog.py:118`, `history_dialog.py:81` 에 하드코딩된 `#0f1318` (bg), `#e8ecf2` (text) 등이 남아 있음. 테마 전환 가능성 봉쇄.

### 구현

**1.** `desktop/qt_app/main_window.py` 에 공통 helper export:

```python
# PALETTE 아래에 추가
def get_dialog_qss() -> str:
    """모든 QDialog 공통 스타일시트 — PALETTE 기반."""
    return (
        f"QDialog {{ background: {PALETTE['dialog_bg']}; "
        f"color: {PALETTE['text_0']}; }}"
        f"QLabel {{ color: {PALETTE['text_1']}; background: transparent; }}"
        f"QLineEdit, QComboBox {{ background: {PALETTE['bg_2']}; "
        f"color: {PALETTE['text_0']}; border: 1px solid {PALETTE['line_2']}; "
        f"border-radius: 4px; padding: 5px 8px; }}"
        f"QPushButton {{ background: {PALETTE['bg_3']}; color: {PALETTE['text_0']}; "
        f"border: 1px solid {PALETTE['line_2']}; border-radius: 4px; "
        f"padding: 6px 12px; }}"
        f"QPushButton:hover {{ background: {PALETTE['bg_4']}; "
        f"border-color: {PALETTE['accent']}; }}"
        f"QPushButton:disabled {{ color: {PALETTE['text_3']}; "
        f"background: {PALETTE['bg_1']}; }}"
    )


def get_table_qss() -> str:
    """QTableWidget 공통 스타일시트."""
    return (
        f"QTableWidget {{ background: {PALETTE['dialog_bg']}; "
        f"color: {PALETTE['text_0']}; gridline-color: {PALETTE['line_1']}; "
        f"border: 1px solid {PALETTE['line_1']}; }}"
        f"QHeaderView::section {{ background: {PALETTE['bg_2']}; "
        f"color: {PALETTE['text_1']}; border: none; "
        f"border-right: 1px solid {PALETTE['line_1']}; "
        f"border-bottom: 1px solid {PALETTE['line_1']}; padding: 6px 8px; }}"
        f"QTableWidget::item {{ padding: 4px 6px; }}"
        f"QTableWidget::item:selected {{ background: {PALETTE['bg_3']}; "
        f"color: {PALETTE['text_0']}; }}"
    )
```

**2.** `batch_dialog.py`, `history_dialog.py`, `error_recovery.py` 에서 하드코딩 스타일시트 제거 후:

```python
from desktop.qt_app.main_window import get_dialog_qss, get_table_qss

# __init__ 에서:
self.setStyleSheet(get_dialog_qss())
# 테이블 있으면:
self.table.setStyleSheet(get_table_qss())
```

### 테스트

```python
def test_dialog_qss_uses_palette() -> None:
    """get_dialog_qss가 PALETTE 참조 + 하드코딩 안함."""
    from desktop.qt_app.main_window import get_dialog_qss, PALETTE

    qss = get_dialog_qss()
    assert PALETTE["dialog_bg"] in qss
    assert PALETTE["text_0"] in qss
    # 하드코딩 hex 없어야 함
    assert "#0f1318" not in qss
    assert "#e8ecf2" not in qss
```

### 커밋

```bash
python3 -m pytest tests/test_qt_app.py -q
git add desktop/qt_app/{main_window.py,batch_dialog.py,history_dialog.py,error_recovery.py} tests/test_qt_app.py
git commit -m "refactor(qt-gui): Task 3A — unified dialog QSS via PALETTE helper"
```

---

## Task 3B — Esc 키 모달 닫기 + Focus

### 현재 문제

일부 모달은 Esc 누르면 닫히지만 커스텀 다이얼로그 (ErrorRecovery, 배치, 이력, 단축키) 는 Esc 처리 누락 가능성.

### 구현

**1.** `desktop/qt_app/widgets/dialog_mixin.py` 신규:

```python
"""모든 QDialog 가 상속할 수 있는 Esc 키 처리 mixin."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


class EscDismissMixin:
    """Esc 키로 reject() 호출. QDialog 와 함께 상속:

        class MyDialog(EscDismissMixin, QDialog): ...
    """

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[misc]
```

**2.** 기존 다이얼로그에 적용:

- `BatchDialog(EscDismissMixin, QDialog)`
- `HistoryDialog(EscDismissMixin, QDialog)`
- `ErrorRecoveryDialog(EscDismissMixin, QDialog)`
- `main_window.py` 의 shortcut/preset/tier 다이얼로그들도 동일

### 테스트

```python
def test_esc_dismisses_batch_dialog() -> None:
    """Esc 키 → BatchDialog reject 호출."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    from desktop.qt_app.batch_dialog import BatchDialog

    d = BatchDialog()
    rejected = []
    d.rejected.connect(lambda: rejected.append(True))

    # Esc key event 주입
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    d.keyPressEvent(event)
    assert rejected == [True]
```

### 커밋

```bash
git add desktop/qt_app/widgets/dialog_mixin.py desktop/qt_app/{batch_dialog.py,history_dialog.py,error_recovery.py} tests/test_qt_app.py
git commit -m "feat(qt-gui): Task 3B — unified Esc-dismiss on all modal dialogs"
```

---

## 최종 검증

모든 태스크 완료 후:

```bash
# 1. 전체 테스트 (신규 포함)
python3 -m pytest tests/test_qt_app.py tests/test_gui_visual.py -q
# 기대: 170+ passed, 8 skipped (또는 visual은 8 PASS)

# 2. 회귀 — 이전 기능 전부 유효
python3 -m pytest tests/test_qt_app.py -k "wildmesh or preset or history or batch" -v
# 기대: 모두 pass

# 3. 실제 pipeline (slow)
python3 -m pytest tests/test_qt_app.py -m slow -q
# 기대: 2 passed (wildmesh end-to-end)

# 4. Glyph 경고 수
python3 -m pytest tests/test_qt_app.py 2>&1 | grep -c "Glyph.*missing"
# 기대: 1 이하
```

### Push

```bash
git log --oneline 8a8c6d7..HEAD
# 5~6개 커밋 예상
git push origin master
```

---

## Codex 실행 팁

- **모든 커밋은 개별 테스트 통과 후 수행**. 실패시 즉시 revert + 재시도
- **파일 작성 전 반드시 `Read` 로 현재 상태 확인** (stale edit 방지)
- **테스트 실행 시 `timeout 120` 사용** (PyVistaQt hang 방지)
- **Python 3.12+, offscreen Qt 필수** (conftest가 자동 설정)
- **새 파일 생성시 `.py` 모듈은 자동 import 테스트 포함** (해당 모듈을 import하는 테스트 1개 이상 작성)
- **WM/GU/BK 분류** 이전 세션 범례:
  - WM = WildMesh 엔진 안정화
  - GU = GUI 렌더링
  - BK = Backlog (새 기능)
  - 이번 플랜의 1A/1B/1C/1D/3A/3B 는 각 독립 commit

---

## 범위 밖 (명시적 제외)

- main_window.py 3300줄 분리 (다음 세션)
- Compare Mode (두 메쉬 나란히) (다음 세션)
- 온보딩 Wizard (다음 세션)
- 라이트/다크 테마 토글 (장기)

---

## 완료 조건 (Definition of Done)

- [ ] Task 1A 스크린샷 baseline 8개 생성 + git tracked
- [ ] Task 1B 정책 전환 드롭다운 리빌드 동작 검증
- [ ] Task 1C 프리셋 → 슬라이더 동기화 동작 검증
- [ ] Task 1D signal 연결 감사 테스트 통과
- [ ] Task 3A 다이얼로그 공통 QSS 적용
- [ ] Task 3B Esc 키 모달 닫기 적용
- [ ] 테스트 170+ passed, 0 regression
- [ ] `git push origin master` 성공
- [ ] 이 문서 하단에 "완료 기록" 섹션 추가 (Codex 작성)

---

## 완료 기록 (Codex 가 작성)

<!-- 완료 후 아래에 커밋 해시 + 결과 수치 기록 -->

- 시작 commit: `8a8c6d7`
- 완료 commit: `미커밋 working tree (base 8a8c6d7)`
- 최종 테스트: `171 passed, 8 skipped`
- 수정된 파일: `.gitignore`, `pyproject.toml`, `tests/conftest.py`, `tests/test_qt_app.py`, `desktop/qt_app/main_window.py`, `desktop/qt_app/batch_dialog.py`, `desktop/qt_app/history_dialog.py`, `desktop/qt_app/error_recovery.py`
- 새로 만든 파일: `desktop/qt_app/widgets/dialog_mixin.py`, `tests/test_gui_visual.py`, `tests/fixtures/screenshots/baselines/*.png` (8개)
- 발견된 예상 외 이슈: `PyVistaQt QtInteractor가 offscreen 테스트 중 native abort를 유발해, 신규 main-window GUI 테스트와 visual baseline 생성에서는 mesh_viewer.PYVISTAQT_AVAILABLE=False로 정적 fallback을 강제함. PySide6 QObject.receivers()는 SignalInstance가 아니라 "2signalSignature" 문자열을 요구해 테스트 헬퍼에 반영함.`
