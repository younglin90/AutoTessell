"""스레드 기반 메시 미리보기 로더 — UI 블로킹 방지."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QThread, Signal


class MeshPreviewWorker(QThread):
    """메시 파일을 별도 스레드에서 로드하는 워커."""

    finished = Signal(bool)  # 로드 성공 여부
    error = Signal(str)      # 오류 메시지

    def __init__(self, viewer: object, mesh_path: str | Path) -> None:
        """초기화.

        Args:
            viewer: MeshViewerWidget 인스턴스
            mesh_path: 메시 파일 경로
        """
        super().__init__()
        self._viewer = viewer
        self._mesh_path = Path(mesh_path)

    def run(self) -> None:
        """메시를 로드하고 뷰어에 반영."""
        try:
            if not self._viewer:
                self.error.emit("메시 뷰어가 None입니다")
                return

            if not hasattr(self._viewer, "load_mesh"):
                self.error.emit("메시 뷰어에 load_mesh 메서드가 없습니다")
                return

            # 메시 로드 (비동기)
            result = self._viewer.load_mesh(str(self._mesh_path))  # type: ignore[union-attr]
            self.finished.emit(bool(result))

        except Exception as e:  # noqa: BLE001
            import traceback
            error_msg = str(e)[:100]
            self.error.emit(error_msg)
            print(f"[MeshPreviewWorker 오류] {error_msg}")
            traceback.print_exc()
