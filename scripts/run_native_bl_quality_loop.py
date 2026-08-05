"""Prepare, dispatch, and collect isolated native boundary-layer work."""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "harness" / "native_bl_quality_loop.json"
RESEARCH_NOTE = (
    REPO_ROOT / "docs/references/boundary_layers/native_bl_harness_research_2026-07-22.md"
)


def _load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if set(config.get("engines", ())) != {"tet", "hex", "poly"}:
        raise ValueError("config.engines must contain exactly tet, hex, poly")
    return config


def _planner_brief(config: dict[str, Any]) -> str:
    return "\n".join(
        (
            "# Native Wall-Face Boundary-Layer Planner",
            "",
            f"Model: {config['planner']['model']}",
            f"Read `{RESEARCH_NOTE.relative_to(REPO_ROOT)}` and current native code.",
            "",
            "Deliver `plan.md` with three independent cards, one per engine.",
            "Each card must use typed wall provenance, gap/collision caps, positive-volume",
            "acceptance, and focused tests. Hard acceptance: non-manifold=0, negative=0,",
            "non-orthogonality<=70, skewness<=4, aspect ratio<=200. Cite primary research.",
            "Do not edit code, widen tests, or touch unrelated dirty changes.",
            "",
        )
    )


def _worker_brief(engine: str, spec: dict[str, Any], config: dict[str, Any]) -> str:
    scope = "\n".join(f"- `{path}`" for path in spec["scope"])
    tests = "\n".join(f"- `{command}`" for command in spec["tests"])
    return "\n".join(
        (
            f"# Native {engine} Wall-Face Boundary-Layer Improver",
            "",
            f"Model: {config['improver']['model']}",
            f"Workspace: `{spec['workspace']}`",
            "Read parent `plan.md`, research note, then only this scope:",
            scope,
            "",
            f"Implement only {engine} card. Preserve public APIs, typed provenance,",
            "wall-only selection, unrelated dirty changes. No reset, checkout, stash,",
            "broad cleanup, external meshing dependency, or threshold change.",
            "",
            "Required evidence:",
            tests,
            "- `python3 scripts/validate_native_bl_case.py <generated-case>`",
            "Return changed paths, generated case path, test result, JSON quality report.",
            "",
        )
    )


def prepare(config: dict[str, Any], run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "planner_brief.md").write_text(_planner_brief(config), encoding="utf-8")
    for engine, spec in config["engines"].items():
        engine_dir = run_dir / engine
        engine_dir.mkdir()
        (engine_dir / "worker_brief.md").write_text(
            _worker_brief(engine, spec, config), encoding="utf-8"
        )
    manifest = {"config": config, "research_note": str(RESEARCH_NOTE), "run_dir": str(run_dir)}
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _command(command: list[str], **values: str) -> list[str]:
    return [part.format(**values) for part in command]


def _run(command: list[str], cwd: Path, log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    return result.returncode


def _ensure_isolated_workspaces(config: dict[str, Any]) -> None:
    current = REPO_ROOT.resolve()
    workspaces: list[Path] = []
    for engine, spec in config["engines"].items():
        raw_workspace = str(spec.get("workspace", "")).strip()
        if not raw_workspace:
            raise ValueError(f"{engine}.workspace is required before dispatch")
        workspace = Path(raw_workspace).resolve()
        if workspace == current:
            raise ValueError(f"{engine}.workspace cannot be current dirty worktree")
        if not (workspace / ".git").exists():
            raise ValueError(f"{engine}.workspace is not a Git worktree: {workspace}")
        workspaces.append(workspace)
    if len(set(workspaces)) != len(workspaces):
        raise ValueError("tet, hex, poly must use distinct workspaces")


def run_planner(config: dict[str, Any], run_dir: Path) -> int:
    command = config["planner"].get("command")
    if not command:
        raise ValueError("planner.command is null; configure gpt-5.6-sol runner")
    return _run(
        _command(command, brief=str(run_dir / "planner_brief.md"), output=str(run_dir / "plan.md")),
        REPO_ROOT,
        run_dir / "planner.log",
    )


def run_improvers(config: dict[str, Any], run_dir: Path) -> dict[str, int]:
    if not (run_dir / "plan.md").is_file():
        raise ValueError("plan.md missing; run planner and review result first")
    command = config["improver"].get("command")
    if not command:
        raise ValueError("improver.command is null; configure gpt-5.6-terra runner")
    _ensure_isolated_workspaces(config)

    def launch(engine: str) -> tuple[str, int]:
        spec = config["engines"][engine]
        engine_dir = run_dir / engine
        code = _run(
            _command(
                command,
                brief=str(engine_dir / "worker_brief.md"),
                plan=str(run_dir / "plan.md"),
                output=str(engine_dir / "improver.md"),
                engine=engine,
            ),
            Path(spec["workspace"]),
            engine_dir / "improver.log",
        )
        return engine, code

    with ThreadPoolExecutor(max_workers=3) as executor:
        return dict(executor.map(launch, ("tet", "hex", "poly")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "planner", "improvers"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    config = _load_config(args.config)
    run_dir = args.run_dir or (
        REPO_ROOT / "research/quality-harness/runs" / f"native-bl-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    )
    try:
        if args.action == "prepare":
            prepare(config, run_dir)
            print(run_dir)
            return 0
        if not run_dir.is_dir():
            parser.error("--run-dir must identify prepared run")
        if args.action == "planner":
            return run_planner(config, run_dir)
        outcomes = run_improvers(config, run_dir)
        print(json.dumps(outcomes, sort_keys=True))
        return 0 if all(code == 0 for code in outcomes.values()) else 1
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
