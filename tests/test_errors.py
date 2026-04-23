"""beta40 — core/utils/errors.py dedicated 회귀."""
from __future__ import annotations

import pytest

from core.utils.errors import (
    AutoTessellError,
    diagnose_error,
    format_missing_dependency_message,
)


# ---------------------------------------------------------------------------
# AutoTessellError
# ---------------------------------------------------------------------------


def test_autotessell_error_basic_message() -> None:
    """AutoTessellError 는 Exception 상속 + 메시지 보존."""
    err = AutoTessellError("something went wrong")
    assert isinstance(err, Exception)
    assert str(err) == "something went wrong"
    assert err.hint == ""
    assert err.details == ""


def test_autotessell_error_with_hint_and_details() -> None:
    """hint / details kwargs 저장."""
    err = AutoTessellError("fail", hint="try this", details="debug info")
    assert err.hint == "try this"
    assert err.details == "debug info"


def test_rich_message_includes_all_parts() -> None:
    """rich_message 가 Error / Hint / details 를 모두 포함 (rich markup 포함)."""
    err = AutoTessellError("msg", hint="h", details="d")
    out = err.rich_message()
    assert "msg" in out
    assert "h" in out
    assert "d" in out
    assert "[bold red]" in out
    assert "[yellow]" in out


def test_rich_message_omits_empty_parts() -> None:
    """빈 hint / details 는 rich_message 에 포함되지 않음."""
    err = AutoTessellError("just an error")
    out = err.rich_message()
    assert "just an error" in out
    assert "Hint:" not in out
    # details markup 도 없어야
    assert "[dim]" not in out


# ---------------------------------------------------------------------------
# format_missing_dependency_message
# ---------------------------------------------------------------------------


def test_format_missing_dep_basic() -> None:
    msg = format_missing_dependency_message(
        "pymeshfix", fallback="trimesh", action="pip install pymeshfix",
    )
    assert "pymeshfix unavailable" in msg
    assert "fallback=trimesh" in msg
    assert "action=pip install pymeshfix" in msg


def test_format_missing_dep_with_detail() -> None:
    """detail 이 있으면 마지막에 추가."""
    msg = format_missing_dependency_message(
        "netgen", fallback="meshpy", action="pip install netgen-mesher",
        detail="conda-forge 도 가능",
    )
    assert "detail=conda-forge 도 가능" in msg


# ---------------------------------------------------------------------------
# diagnose_error
# ---------------------------------------------------------------------------


def test_diagnose_file_not_found_stl_hints() -> None:
    """FileNotFoundError + stl 확장자 메시지 → 한국어 힌트."""
    err = FileNotFoundError("cannot find /tmp/foo.stl")
    out = diagnose_error(err)
    assert "파일을 찾을 수 없습니다" in out
    assert "Hint" in out


def test_diagnose_cadquery_import() -> None:
    """cadquery ImportError 감지."""
    err = ImportError("No module named 'cadquery'")
    out = diagnose_error(err)
    assert "cadquery" in out
    assert "STEP" in out or "IGES" in out


def test_diagnose_netgen_import() -> None:
    err = ImportError("netgen 모듈 찾을 수 없음")
    out = diagnose_error(err)
    assert "Netgen" in out or "netgen" in out


def test_diagnose_memory_error() -> None:
    """MemoryError 감지 후 quality/element-size 힌트."""
    err = MemoryError("out of memory")
    out = diagnose_error(err)
    assert "메모리" in out
    assert "quality" in out or "element-size" in out


def test_diagnose_all_tiers_failed() -> None:
    """'All tiers failed' 패턴 → 진단 메시지."""
    err = RuntimeError("All mesh generation tiers failed")
    out = diagnose_error(err)
    assert "생성 엔진" in out or "tier" in out.lower()


def test_diagnose_unknown_error_returns_type_and_message() -> None:
    """패턴 매칭 실패 시 기본 포맷 (Error type + message)."""
    err = ValueError("some unrelated error")
    out = diagnose_error(err)
    assert "ValueError" in out
    assert "some unrelated error" in out


def test_diagnose_openfoam_not_found_hint() -> None:
    err = RuntimeError("checkMesh binary not found")
    out = diagnose_error(err)
    assert "OpenFOAM" in out


def test_diagnose_non_watertight_hint() -> None:
    err = ValueError("mesh is not watertight")
    out = diagnose_error(err)
    assert "watertight" in out.lower() or "수리" in out
