"""L0 contracts for phase-scoped release-goal evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).with_name("verify_goal.py")


def _load_goal_module():
    spec = importlib.util.spec_from_file_location("verify_goal_phased_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_runs_all_phases_in_contract_order(monkeypatch: pytest.MonkeyPatch) -> None:
    goal = _load_goal_module()
    calls: list[object] = []
    monkeypatch.setattr(goal, "verify_gui", lambda: calls.append("gui"))
    monkeypatch.setattr(
        goal,
        "verify_param_propagation",
        lambda target_cells, bl_layers: calls.append(("param", target_cells, bl_layers)),
    )
    monkeypatch.setattr(
        goal,
        "verify_e2e",
        lambda types, target_cells, bl_layers, timeout: calls.append(
            ("e2e", types, target_cells, bl_layers, timeout)
        ),
    )

    assert goal.main([]) == 0
    assert calls == [
        "gui",
        ("param", 15000, 2),
        ("e2e", ["tet", "hex_dominant", "poly"], 15000, 2, 420),
    ]


def test_selected_phase_forwards_controls_and_marks_omitted_not_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    goal = _load_goal_module()
    calls: list[object] = []
    monkeypatch.setattr(
        goal,
        "verify_e2e",
        lambda types, target_cells, bl_layers, timeout: calls.append(
            (types, target_cells, bl_layers, timeout)
        ),
    )
    evidence_path = tmp_path / "evidence.json"

    assert goal.main(
        [
            "--phase", "e2e",
            "--types", "tet,poly",
            "--types", "poly",
            "--target-cells", "2000",
            "--bl-layers", "0",
            "--per-type-timeout", "17",
            "--evidence-json", str(evidence_path),
        ]
    ) == 0

    assert calls == [(["tet", "poly"], 2000, 0, 17)]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["phases"]["e2e"]["status"] == "PASS"
    assert evidence["phases"]["gui"]["status"] == "NOT_RUN"
    assert evidence["phases"]["param"]["status"] == "NOT_RUN"
    assert evidence["inputs"]["bl_layers"] == 0


def test_selected_phase_failure_is_recorded_as_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    goal = _load_goal_module()
    monkeypatch.setattr(goal, "verify_gui", lambda: (_ for _ in ()).throw(RuntimeError("forced")))
    evidence_path = tmp_path / "evidence.json"

    assert goal.main(["--phase", "gui", "--evidence-json", str(evidence_path)]) == 1
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["phases"]["gui"]["status"] == "FAIL"
    assert evidence["phases"]["param"]["status"] == "NOT_RUN"
    assert evidence["result"] == "FAIL"
