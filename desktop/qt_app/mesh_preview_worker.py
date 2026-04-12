"""스레드 기반 메시 미리보기 로더 — UI 블로킹 방지."""
from __future__ import annotations

from pathlib import Path


class MeshPreviewWorker:
    """메시 파일을 별도 스레드에서 로드하는 워커."""

    def __new__(cls, viewer: object, mesh_path: str | Path) -> MeshPreviewWorker:  # type: ignore[misc]
        """QThread를 동적으로 상속한 인스턴스를 반환한다."""
        from PySide6.QtCore import QThread, Signal

        if not hasattr(cls, "_qt_class"):
            class _LoaderThread(QThread):
                """메시 로드 워커 스레드."""

                finished: Signal[bool] = Signal(bool)
                error: Signal[str] = Signal(str)

                def __init__(self, viewer: object, mesh_path: str | Path) -> None:
                    super().__init__()
                    self._viewer = viewer
                    self._mesh_path = Path(mesh_path)

                def run(self) -> None:
                    """메시를 로드하고 뷰어에 반영."""
                    try:
                        if hasattr(self._viewer, "load_mesh"):
                            result = self._viewer.load_mesh(str(self._mesh_path))  # type: ignore[union-attr]
                            self.finished.emit(bool(result))
                        else:
                            self.error.emit("메시 뷰어에 load_mesh 메서드가 없습니다")
                    except Exception as e:  # noqa: BLE001
                        self.error.emit(str(e))

            cls._qt_class = _LoaderThread

        instance = cls._qt_class.__new__(cls._qt_class)
        instance.__init__(viewer, mesh_path)
        return instance  # type: ignore[return-value]
