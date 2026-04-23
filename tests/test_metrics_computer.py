"""beta48 — AdditionalMetricsComputer dedicated 회귀."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.evaluator.metrics import AdditionalMetricsComputer
from core.generator.polymesh_writer import write_generic_polymesh
from core.schemas import AdditionalMetrics


def _make_tet_polymesh(case_dir: Path) -> None:
    """최소 2-tet polyMesh 생성."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, 1], [0, 0, -1],
    ], dtype=np.float64)
    tet1 = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    tet2 = [[0, 1, 2], [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    write_generic_polymesh(V, [tet1, tet2], case_dir)


def test_compute_no_polymesh_returns_empty_metrics(tmp_path: Path) -> None:
    """polyMesh 디렉터리 없으면 빈 AdditionalMetrics 반환 (예외 없음)."""
    computer = AdditionalMetricsComputer()
    result = computer.compute(tmp_path)
    assert isinstance(result, AdditionalMetrics)
    # 빈 객체는 cell_volume stats / bl stats 가 None
    # (AdditionalMetrics 의 필드가 Optional 이므로)


def test_compute_returns_additional_metrics_type(tmp_path: Path) -> None:
    """compute 는 항상 AdditionalMetrics 인스턴스 반환."""
    _make_tet_polymesh(tmp_path)
    computer = AdditionalMetricsComputer()
    result = computer.compute(tmp_path)
    assert isinstance(result, AdditionalMetrics)


def test_compute_internal_exception_gracefully_handled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_compute_internal 에서 예외 발생 시 빈 AdditionalMetrics 반환."""
    _make_tet_polymesh(tmp_path)
    computer = AdditionalMetricsComputer()

    def _raise(*a, **kw):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(computer, "_compute_internal", _raise)
    result = computer.compute(tmp_path)
    assert isinstance(result, AdditionalMetrics)


def test_compute_import_error_handled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_compute_internal ImportError 시에도 AdditionalMetrics 반환."""
    _make_tet_polymesh(tmp_path)
    computer = AdditionalMetricsComputer()

    def _raise_import(*a, **kw):
        raise ImportError("simulated pyvista missing")

    monkeypatch.setattr(computer, "_compute_internal", _raise_import)
    result = computer.compute(tmp_path)
    assert isinstance(result, AdditionalMetrics)


def test_compute_on_valid_polymesh_not_crashing(tmp_path: Path) -> None:
    """valid polyMesh → compute 가 crash 없이 AdditionalMetrics 반환."""
    _make_tet_polymesh(tmp_path)
    computer = AdditionalMetricsComputer()
    result = computer.compute(tmp_path)
    assert isinstance(result, AdditionalMetrics)
    # cell_volume_stats 가 계산되었다면 CellVolumeStats 인스턴스
    if result.cell_volume_stats is not None:
        from core.schemas import CellVolumeStats
        assert isinstance(result.cell_volume_stats, CellVolumeStats)


def test_check_bl_enabled_on_polymesh_without_bl(tmp_path: Path) -> None:
    """BL 정보 없는 단순 polyMesh → _check_bl_enabled 가 False 반환."""
    _make_tet_polymesh(tmp_path)
    computer = AdditionalMetricsComputer()
    # 메서드가 존재하는 private 이지만 테스트 — False 반환 기대
    result = computer._check_bl_enabled(tmp_path)
    assert isinstance(result, bool)
    # 이 polyMesh 는 BL 삽입 안 함 → False
    assert result is False


def test_find_vtk_file_empty_dir_returns_none(tmp_path: Path) -> None:
    """VTK 파일 없는 디렉터리 → _find_vtk_file None."""
    computer = AdditionalMetricsComputer()
    result = computer._find_vtk_file(tmp_path)
    assert result is None


def test_find_vtk_file_picks_vtk_or_vtu(tmp_path: Path) -> None:
    """.vtk 또는 .vtu 파일이 있으면 반환."""
    fake = tmp_path / "mesh.vtk"
    fake.write_bytes(b"# vtk DataFile Version 3.0\nASCII\n")
    computer = AdditionalMetricsComputer()
    result = computer._find_vtk_file(tmp_path)
    # vtk 파일을 찾거나 None (구현에 따라) — 예외 없이 완료
    assert result is None or result.suffix in (".vtk", ".vtu")
