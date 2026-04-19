"""배치 처리 다이얼로그 — job queue 테이블 + 직렬 실행."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from desktop.qt_app.batch import BatchJob, BatchSummary, JobStatus, make_parameter_sweep

_STATUS_COLORS = {
    JobStatus.PENDING: "#5a6270",
    JobStatus.RUNNING: "#4ea3ff",
    JobStatus.SUCCESS: "#22c55e",
    JobStatus.FAILED: "#ef4444",
    JobStatus.CANCELLED: "#f59e0b",
}

_STATUS_LABELS = {
    JobStatus.PENDING: "대기",
    JobStatus.RUNNING: "실행 중",
    JobStatus.SUCCESS: "성공",
    JobStatus.FAILED: "실패",
    JobStatus.CANCELLED: "취소",
}


class BatchDialog(QDialog):
    """배치 처리 다이얼로그.

    사용자 플로우:
    1. "파일 추가"로 여러 STL 선택 (또는 파라미터 스윕 설정)
    2. 프리셋 + 출력 루트 디렉토리 지정
    3. "실행" → 테이블의 각 job이 순차 실행, 실시간 상태 갱신
    4. 완료 후 요약 메시지박스
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("배치 처리")
        # 표준 LARGE 다이얼로그 크기 (main_window.DIALOG_LARGE)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(
            "QDialog { background: #0f1318; color: #e8ecf2; }"
            "QLabel { color: #b6bdc9; background: transparent; }"
            "QLineEdit, QComboBox { background: #161a20; color: #e8ecf2; "
            "border: 1px solid #323a46; border-radius: 4px; padding: 5px 8px; }"
            "QPushButton { background: #21262d; color: #e8ecf2; "
            "border: 1px solid #30363d; border-radius: 4px; "
            "padding: 6px 12px; } "
            "QPushButton:hover { background: #2d333b; border-color: #4ea3ff; } "
            "QPushButton:disabled { color: #5a6270; background: #101318; }"
        )

        self._jobs: list[BatchJob] = []
        self._running_idx: int = -1
        self._worker: object | None = None
        self._cancel_requested: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # ── 공통 설정 ──────────────────────────────────────────
        cfg_frame = QFrame()
        cfg_frame.setStyleSheet(
            "QFrame { background: #161a20; border: 1px solid #262c36; border-radius: 4px; }"
        )
        cfg_layout = QVBoxLayout(cfg_frame)
        cfg_layout.setContentsMargins(12, 10, 12, 10)
        cfg_layout.setSpacing(6)

        # 출력 루트
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("출력 루트:"))
        self.output_root_edit = QLineEdit()
        self.output_root_edit.setPlaceholderText("~/meshes/batch/")
        self.output_root_edit.setText(str(Path.home() / "autotessell_batch"))
        out_row.addWidget(self.output_root_edit, stretch=1)
        out_browse = QPushButton("⋯")
        out_browse.setFixedWidth(36)
        out_browse.clicked.connect(self._pick_output_root)
        out_row.addWidget(out_browse)
        cfg_layout.addLayout(out_row)

        # 프리셋
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("프리셋:"))
        self.preset_combo = QComboBox()
        self._populate_preset_combo()
        preset_row.addWidget(self.preset_combo, stretch=1)
        cfg_layout.addLayout(preset_row)

        layout.addWidget(cfg_frame)

        # ── Job 테이블 ─────────────────────────────────────────
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "파일", "프리셋", "출력", "상태", "시간(s)", "셀수",
        ])
        self.table.setStyleSheet(
            "QTableWidget { background: #0f1318; color: #e8ecf2; "
            "gridline-color: #262c36; border: 1px solid #262c36; }"
            "QHeaderView::section { background: #161a20; color: #b6bdc9; "
            "border: none; border-right: 1px solid #262c36; "
            "border-bottom: 1px solid #262c36; padding: 6px 8px; }"
            "QTableWidget::item { padding: 4px 6px; }"
            "QTableWidget::item:selected { background: #1c2129; color: #e8ecf2; }"
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.table, stretch=1)

        # ── Job 관리 버튼 ──────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_add = QPushButton("파일 추가…")
        btn_add.clicked.connect(self._add_files)
        btn_row.addWidget(btn_add)

        btn_sweep = QPushButton("파라미터 스윕…")
        btn_sweep.clicked.connect(self._add_sweep)
        btn_row.addWidget(btn_sweep)

        btn_remove = QPushButton("선택 제거")
        btn_remove.clicked.connect(self._remove_selected)
        btn_row.addWidget(btn_remove)

        btn_clear = QPushButton("모두 제거")
        btn_clear.clicked.connect(self._clear_all)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── 진행바 ─────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setStyleSheet(
            "QProgressBar { background: #161a20; border: 1px solid #262c36; "
            "border-radius: 4px; text-align: center; color: #e8ecf2; "
            "height: 20px; }"
            "QProgressBar::chunk { background: #4ea3ff; border-radius: 3px; }"
        )
        self.progress.setFormat("%v / %m 완료")
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # ── 실행 버튼 ──────────────────────────────────────────
        run_row = QHBoxLayout()
        run_row.addStretch()
        self.cancel_btn = QPushButton("중단")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        run_row.addWidget(self.cancel_btn)

        self.run_btn = QPushButton("▶  배치 실행")
        self.run_btn.setStyleSheet(
            "QPushButton { background: #4ea3ff; color: #05111e; "
            "border: 1px solid #4ea3ff; border-radius: 4px; "
            "padding: 8px 20px; font-weight: 600; }"
            "QPushButton:hover { background: #6ab4ff; border-color: #6ab4ff; }"
            "QPushButton:disabled { background: #1c2129; color: #5a6270; "
            "border-color: #323a46; }"
        )
        self.run_btn.clicked.connect(self._on_run)
        run_row.addWidget(self.run_btn)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.reject)
        run_row.addWidget(close_btn)
        layout.addLayout(run_row)

    # ------------------------------------------------------------------
    # 프리셋 로드
    # ------------------------------------------------------------------

    def _populate_preset_combo(self) -> None:
        from desktop.qt_app import presets as _p

        self.preset_combo.clear()
        for preset in _p.all_presets():
            self.preset_combo.addItem(preset.name, preset.name)

    def _current_preset(self):
        from desktop.qt_app import presets as _p

        name = self.preset_combo.currentData()
        return _p.get(name) if name else None

    # ------------------------------------------------------------------
    # Job 관리
    # ------------------------------------------------------------------

    def add_jobs(self, jobs: list[BatchJob]) -> None:
        """외부에서 job 주입 가능 (테스트 + 프로그래매틱)."""
        self._jobs.extend(jobs)
        self._refresh_table()

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "배치 처리할 파일들 선택", "",
            "Mesh files (*.stl *.step *.stp *.iges *.igs *.obj *.ply);;All files (*)",
        )
        if not paths:
            return
        preset = self._current_preset()
        if preset is None:
            QMessageBox.warning(self, "프리셋 없음", "프리셋을 먼저 선택하세요.")
            return
        root = Path(self.output_root_edit.text() or str(Path.home()))
        for p in paths:
            pth = Path(p)
            self._jobs.append(BatchJob(
                input_path=pth,
                output_dir=root / f"{pth.stem}_case",
                quality_level=preset.quality_level,
                tier_hint=preset.tier_hint,
                params=dict(preset.params),
                preset_name=preset.name,
            ))
        self._refresh_table()

    def _add_sweep(self) -> None:
        """파라미터 스윕 다이얼로그 — 단일 파일 × 파라미터 값 리스트."""
        from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout

        # 미니 sub-dialog
        d = QDialog(self)
        d.setWindowTitle("파라미터 스윕 설정")
        d.setMinimumWidth(480)
        v = QVBoxLayout(d)

        v.addWidget(QLabel("입력 파일 (단일):"))
        input_row = QHBoxLayout()
        input_edit = QLineEdit()
        input_edit.setReadOnly(True)
        input_row.addWidget(input_edit, stretch=1)
        input_browse = QPushButton("⋯")
        input_browse.setFixedWidth(36)
        input_row.addWidget(input_browse)
        v.addLayout(input_row)

        def _pick():
            p, _ = QFileDialog.getOpenFileName(
                d, "입력 파일 선택", "",
                "Mesh files (*.stl *.step *.stp *.iges *.igs *.obj *.ply)",
            )
            if p:
                input_edit.setText(p)
        input_browse.clicked.connect(_pick)

        v.addWidget(QLabel("파라미터 키 (예: epsilon, edge_length):"))
        key_edit = QLineEdit("epsilon")
        v.addWidget(key_edit)

        v.addWidget(QLabel("값 목록 (쉼표 구분, 예: 0.001, 0.002, 0.005):"))
        vals_edit = QLineEdit("0.001, 0.002, 0.005")
        v.addWidget(vals_edit)

        ok_row = QHBoxLayout()
        ok_row.addStretch()
        ok_btn = QPushButton("스윕 생성")
        ok_btn.clicked.connect(d.accept)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(d.reject)
        ok_row.addWidget(cancel_btn)
        ok_row.addWidget(ok_btn)
        v.addLayout(ok_row)

        if d.exec() != QDialog.Accepted:
            return

        input_path = input_edit.text().strip()
        if not input_path or not Path(input_path).exists():
            QMessageBox.warning(self, "파일 없음", "입력 파일이 유효하지 않습니다.")
            return
        key = key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "키 없음", "파라미터 키를 입력하세요.")
            return
        try:
            values = [float(v.strip()) for v in vals_edit.text().split(",") if v.strip()]
        except ValueError:
            QMessageBox.warning(self, "값 오류", "값은 쉼표로 구분된 숫자여야 합니다.")
            return
        if not values:
            return

        preset = self._current_preset()
        if preset is None:
            return
        root = Path(self.output_root_edit.text() or str(Path.home()))

        new_jobs = make_parameter_sweep(
            base_input=Path(input_path),
            output_root=root,
            quality_level=preset.quality_level,
            tier_hint=preset.tier_hint,
            sweep_key=key,
            sweep_values=values,
            preset_name=preset.name,
        )
        # 프리셋 base params도 합침 (sweep key로 덮어쓰기)
        for j in new_jobs:
            merged = dict(preset.params)
            merged.update(j.params)
            j.params = merged

        self._jobs.extend(new_jobs)
        self._refresh_table()

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._jobs) and self._jobs[r].status != JobStatus.RUNNING:
                del self._jobs[r]
        self._refresh_table()

    def _clear_all(self) -> None:
        if any(j.status == JobStatus.RUNNING for j in self._jobs):
            QMessageBox.warning(self, "실행 중", "실행 중인 job이 있어 제거할 수 없습니다.")
            return
        self._jobs.clear()
        self._refresh_table()

    def _pick_output_root(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "출력 루트 디렉토리 선택",
            self.output_root_edit.text() or str(Path.home()),
        )
        if d:
            self.output_root_edit.setText(d)

    # ------------------------------------------------------------------
    # 테이블 갱신
    # ------------------------------------------------------------------

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._jobs))
        for i, job in enumerate(self._jobs):
            self._update_row(i)
        self.progress.setMaximum(max(1, len(self._jobs)))
        self.progress.setValue(
            sum(1 for j in self._jobs
                if j.status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED))
        )

    def _update_row(self, idx: int) -> None:
        job = self._jobs[idx]
        items = [
            QTableWidgetItem(job.display_name()),
            QTableWidgetItem(job.preset_name or "—"),
            QTableWidgetItem(str(job.output_dir.name)),
            QTableWidgetItem(_STATUS_LABELS.get(job.status, job.status.value)),
            QTableWidgetItem(f"{job.elapsed_seconds:.1f}" if job.elapsed_seconds else ""),
            QTableWidgetItem(f"{job.n_cells:,}" if job.n_cells else ""),
        ]
        status_color = QColor(_STATUS_COLORS.get(job.status, "#e8ecf2"))
        items[3].setForeground(status_color)
        for col, it in enumerate(items):
            self.table.setItem(idx, col, it)

    # ------------------------------------------------------------------
    # 실행
    # ------------------------------------------------------------------

    def _on_run(self) -> None:
        if not self._jobs:
            QMessageBox.information(self, "비어 있음", "실행할 job을 먼저 추가하세요.")
            return
        # 대기 중인 것만 남기기 (이전 실행 결과 포함시 이어서)
        self._cancel_requested = False
        self._running_idx = -1
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._start_next()

    def _start_next(self) -> None:
        # 다음 pending job 찾기
        if self._cancel_requested:
            self._on_batch_done()
            return
        next_idx = next(
            (i for i, j in enumerate(self._jobs) if j.status == JobStatus.PENDING),
            -1,
        )
        if next_idx < 0:
            self._on_batch_done()
            return

        self._running_idx = next_idx
        job = self._jobs[next_idx]
        job.status = JobStatus.RUNNING
        self._update_row(next_idx)

        # PipelineWorker 생성
        import time as _time

        from desktop.qt_app.main_window import QualityLevel
        from desktop.qt_app.pipeline_worker import PipelineWorker

        job._start_time = _time.monotonic()  # type: ignore[attr-defined]

        try:
            qlevel = QualityLevel(job.quality_level)
        except Exception:
            qlevel = QualityLevel.DRAFT

        worker = PipelineWorker(
            input_path=job.input_path,
            quality_level=qlevel,
            output_dir=job.output_dir,
            tier_hint=job.tier_hint,
            tier_specific_params=job.params,
        )
        self._worker = worker

        worker.finished.connect(self._on_job_finished)  # type: ignore[attr-defined]
        worker.start()  # type: ignore[attr-defined]

    def _on_job_finished(self, result: object) -> None:
        import time as _time

        if self._running_idx < 0:
            return
        job = self._jobs[self._running_idx]
        job.elapsed_seconds = _time.monotonic() - getattr(job, "_start_time", _time.monotonic())

        if result is None:
            job.status = JobStatus.FAILED
            job.error = "no result"
        elif getattr(result, "success", False):
            job.status = JobStatus.SUCCESS
            # checkmesh 결과에서 n_cells 추출
            try:
                qr = getattr(result, "quality_report", None)
                cm = getattr(qr, "check_mesh", None)
                if cm is not None:
                    job.n_cells = int(getattr(cm, "cells", 0))
            except Exception:
                pass
        else:
            job.status = JobStatus.FAILED
            job.error = str(getattr(result, "error", "unknown"))

        self._update_row(self._running_idx)
        self.progress.setValue(
            sum(1 for j in self._jobs
                if j.status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED))
        )

        # 다음 job
        QTimer.singleShot(50, self._start_next)

    def _on_cancel(self) -> None:
        self._cancel_requested = True
        # 현재 실행 중 worker에 중단 요청
        if self._worker is not None:
            try:
                self._worker.requestInterruption()  # type: ignore[attr-defined]
            except Exception:
                pass
        # 대기 중인 job들을 취소 상태로
        for j in self._jobs:
            if j.status == JobStatus.PENDING:
                j.status = JobStatus.CANCELLED
        self._refresh_table()

    def _on_batch_done(self) -> None:
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._worker = None
        self._running_idx = -1

        summary = BatchSummary.from_jobs(self._jobs)
        msg = (
            f"배치 완료\n\n"
            f"총 {summary.total}개 job\n"
            f"  ✓ 성공: {summary.succeeded}\n"
            f"  ✗ 실패: {summary.failed}\n"
            f"  ⊘ 취소: {summary.cancelled}\n"
            f"총 소요: {summary.total_elapsed_seconds:.1f}초\n"
            f"성공률: {summary.pass_rate() * 100:.1f}%"
        )
        QMessageBox.information(self, "배치 완료", msg)
