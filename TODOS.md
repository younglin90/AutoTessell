# AutoTessell TODOs

## GUI

### [x] 로그 우클릭 메뉴 탐색성 개선
**What:** `JobPane` 로그 박스에 우클릭 메뉴(Copy/Save/Clear)가 있지만 힌트가 없어 발견하기 어려움.
**Why:** 툴팁이나 힌트 텍스트가 없으면 CFD 엔지니어가 긴 로그를 수동으로 복사해야 함.
**How:** `log_box` 위에 `"우클릭으로 복사/저장"` 레이블 또는 `setToolTip()` 추가.
**Status:** ✅ 완료 — setToolTip + 힌트 레이블 추가됨

### [x] 뷰포트 품질 색상화 고도화
**What:** 품질 표시 버튼이 aspect_ratio만 표시하던 것을 skewness / non-orthogonality 선택 가능하도록 업그레이드.
**Why:** CFD에서 skewness가 가장 중요한 메트릭인 경우 많음.
**How:** 품질 버튼을 QToolButton 드롭다운으로 교체 — Aspect / Skewness / Non-ortho 선택.
**Status:** ✅ 완료 — `_QUALITY_METRICS` dict + QToolButton MenuButtonPopup + `_on_quality_metric_selected`

### [x] 인터랙티브 품질 히스토그램
**What:** Export PNG 대신 Quality 탭 내에 matplotlib FigureCanvas 임베드.
**Why:** 사용자가 매번 Export하지 않고 메시 로드 즉시 분포 확인 가능.
**How:** `right_column.py` QualityPane에 `_HistogramCanvas` 서브위젯 추가 + `mesh_stats_computed` Signal로 자동 갱신.
**Status:** ✅ 완료 — `_HistogramCanvas.update_histograms(aspect_data, skew_data)` 구현, main_window 연결

## 버그 수정 (QA 감사 결과)

### [x] tier_pipeline.py — mousePressEvent monkey-patch 제거
**Status:** ✅ 완료 — `_TierNode.node_clicked` Signal + `mousePressEvent` 오버라이드로 수정

### [x] mesh_viewer.py — _on_mesh_loaded monkey-patch 제거
**Status:** ✅ 완료 — `InteractiveMeshViewer.mesh_ready` Signal emit + `MeshViewerWidget` signal connect

### [x] drop_zone.py — mousePressEvent monkey-patch 제거
**Status:** ✅ 완료 — `DropZone.clicked` Signal + `mousePressEvent` 오버라이드 추가

### [x] pipeline_worker.py — InterruptedError 시 UI stuck 버그
**Status:** ✅ 완료 — `InterruptedError` 핸들러에서 `finished.emit(PipelineResult(success=False))` 추가

### [x] _QualityBar resizeEvent — fill 비율 재계산 버그
**Status:** ✅ 완료 — `_fill_ratio` 저장 + `resizeEvent`에서 `w * _fill_ratio` 사용

### [x] mesh_viewer.py — foam_file.touch() 예외 미처리
**Status:** ✅ 완료 — 중첩 try/except로 PermissionError 방지

### [x] main_window.py — QThread.terminate() 서브프로세스 미정리
**Status:** ✅ 완료 — `terminate()` 제거, `requestInterruption()` 단독 사용

### [x] conftest.py — QApplication 세션 픽스처 없어 위젯 GC 충돌
**Status:** ✅ 완료 — `_qt_application` session-scoped autouse fixture + `QT_QPA_PLATFORM=offscreen`
