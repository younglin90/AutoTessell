"""core/runtime/dependency_status.py 회귀 테스트 (v0.4.0-beta21)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.runtime import dependency_status as ds


def test_dependency_status_is_frozen_dataclass() -> None:
    """DependencyStatus 는 immutable — 실수로 state 변경되지 않게."""
    s = ds.DependencyStatus(
        name="x", category="core", optional=False, detected=True,
        detector="x", fallback="x", action="x",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        s.detected = False  # type: ignore[misc]


def test_collect_returns_nonempty_list_of_statuses() -> None:
    """collect_dependency_statuses 가 최소 10 개 이상의 entry 를 반환."""
    entries = ds.collect_dependency_statuses()
    assert isinstance(entries, list)
    assert len(entries) >= 10
    assert all(isinstance(e, ds.DependencyStatus) for e in entries)


def test_every_status_has_required_fields() -> None:
    """모든 entry 가 name/category/detector/fallback/action 을 비어있지 않게 채움."""
    for e in ds.collect_dependency_statuses():
        assert e.name and e.name.strip()
        assert e.category and e.category.strip()
        assert e.detector and e.detector.strip()
        assert e.fallback and e.fallback.strip()
        assert e.action and e.action.strip()


def test_openfoam_entry_is_non_optional_core() -> None:
    """OpenFOAM 은 core 범주 + non-optional 로 분류."""
    entries = ds.collect_dependency_statuses()
    of = next((e for e in entries if e.name == "OpenFOAM"), None)
    assert of is not None
    assert of.category == "core"
    assert of.optional is False


def test_module_check_truthy_for_existing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """_has_module 이 실제 패키지에 True, 존재하지 않는 이름에 False."""
    # 본 프로세스에 numpy 는 반드시 설치됨
    assert ds._has_module("numpy") is True
    assert ds._has_module("definitely_not_a_real_module_xyz_123") is False


def test_bin_check_truthy_for_existing_and_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """_has_bin 이 PATH 에 있는 바이너리에 True, 없는 것에 False."""
    # ls 는 거의 모든 리눅스 환경에 있음
    assert ds._has_bin("ls") is True
    assert ds._has_bin("definitely_not_on_path_xyz_987") is False


def test_module_detection_respects_importlib_monkeypatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """importlib.util.find_spec 을 monkeypatch 로 변경 시 _has_module 반영."""
    # numpy 를 "없는 것처럼" 보이도록 패치
    def _fake_find_spec(name: str):
        if name == "numpy":
            return None
        import importlib.util as _iu
        return _iu.find_spec.__wrapped__(name) if hasattr(_iu.find_spec, "__wrapped__") else None

    monkeypatch.setattr(ds.importlib.util, "find_spec", _fake_find_spec)
    assert ds._has_module("numpy") is False


def test_collect_with_openfoam_label_size_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenFOAM 감지 실패 (label size 0) 시 detected=False 로 반영."""
    monkeypatch.setattr(
        ds, "get_openfoam_label_size", lambda: 0,
    )
    entries = ds.collect_dependency_statuses()
    of = next(e for e in entries if e.name == "OpenFOAM")
    assert of.detected is False
