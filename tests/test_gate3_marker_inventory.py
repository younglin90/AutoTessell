"""Fail-closed Gate 3 inventory for skips, xfails, and flaky markers."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "tests" / "gate3_marker_defer_l0.json"
TARGET_PATTERNS = (
    "test_native_tet*.py",
    "test_native_hex*.py",
    "test_native_poly*.py",
    "test_native_tri*.py",
    "test_native_quad*.py",
    "test_native_surface*.py",
    "test_*route*.py",
    "test_cli*.py",
    "test_desktop*.py",
    "test_gui*.py",
    "test_qt*.py",
    "test_ui*.py",
)
MARKERS = {
    "pytest.skip",
    "pytest.xfail",
    "pytest.mark.skip",
    "pytest.mark.skipif",
    "pytest.mark.xfail",
    "pytest.mark.flaky",
}


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _reason(node: ast.Call, marker: str) -> str:
    reason = next((item.value for item in node.keywords if item.arg == "reason"), None)
    if reason is None and marker in {"pytest.skip", "pytest.xfail"} and node.args:
        reason = node.args[0]
    if isinstance(reason, ast.Constant) and isinstance(reason.value, str):
        return reason.value
    if isinstance(reason, ast.JoinedStr):
        return "<dynamic reason>"
    return "<no explicit reason>"


def collect_markers() -> list[dict[str, object]]:
    paths = sorted({path for pattern in TARGET_PATTERNS for path in (ROOT / "tests").glob(pattern)})
    rows: list[dict[str, object]] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            marker = _dotted_name(node.func)
            if marker not in MARKERS:
                continue
            rows.append(
                {
                    "file": path.relative_to(ROOT).as_posix(),
                    "line": node.lineno,
                    "marker": marker,
                    "reason": _reason(node, marker),
                }
            )
    return sorted(rows, key=lambda row: (str(row["file"]), int(row["line"]), str(row["marker"])))


def test_gate3_marker_inventory_matches_explicit_defer_ledger() -> None:
    expected = json.loads(LEDGER.read_text(encoding="utf-8"))
    actual = collect_markers()
    canonical = json.dumps(actual, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    deferred = [
        row
        for row in actual
        if row["reason"] in {"<dynamic reason>", "<no explicit reason>"}
    ]
    assert expected["scope_patterns"] == list(TARGET_PATTERNS)
    assert expected["marker_count"] == len(actual), (
        "Gate 3 collected marker count changed; update the DEFER ledger before release."
    )
    assert expected["marker_sha256"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest(), (
        "Gate 3 marker inventory changed. Add an exact file/line/marker/reason entry to the "
        "DEFER ledger, or remove the marker with an independently verified replacement test."
    )
    assert expected["deferred"] == deferred
