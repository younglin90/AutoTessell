#!/usr/bin/env python3
"""Build and smoke-test an AutoTessell wheel in a fresh external virtualenv.

Run from a checkout without writing build products into it:

    python scripts/verify_package_wheel.py --repo . --timeout-sec 120

The JSON result is release evidence, not a synthetic success marker.  Every
phase records its command, exit status, duration, and a bounded stdout/stderr
tail.  A timed out or failed install leaves the run failed and prevents the
CLI phases from being reported as passed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path
from typing import Any


_OUTPUT_LIMIT = 4000


def _tail(value: str) -> str:
    return value[-_OUTPUT_LIMIT:]


def _run(command: list[str], *, cwd: Path, timeout_sec: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "status": "timeout",
            "command": command,
            "duration_sec": round(time.perf_counter() - started, 3),
            "timeout_sec": timeout_sec,
            "stdout_tail": _tail(error.stdout or ""),
            "stderr_tail": _tail(error.stderr or ""),
        }
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "command": command,
        "returncode": completed.returncode,
        "duration_sec": round(time.perf_counter() - started, 3),
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def _venv_executable(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        suffix = ".exe" if name != "python" else ".exe"
        return venv_dir / "Scripts" / f"{name}{suffix}"
    return venv_dir / "bin" / name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _phase_pass(result: dict[str, Any]) -> bool:
    return result.get("status") == "pass"


def verify(repo: Path, timeout_sec: float) -> dict[str, Any]:
    repo = repo.resolve()
    benchmark = repo / "tests" / "benchmarks" / "sphere.stl"
    if not (repo / "pyproject.toml").is_file():
        raise ValueError(f"not a Python project root: {repo}")
    if not benchmark.is_file():
        raise ValueError(f"missing packaging smoke fixture: {benchmark}")

    root = Path(tempfile.mkdtemp(prefix="autotessell-wheel-"))
    wheel_dir = root / "wheel"
    wheel_dir.mkdir()
    fixture_dir = root / "fixture"
    fixture_dir.mkdir()
    fixture = fixture_dir / benchmark.name
    shutil.copy2(benchmark, fixture)
    result: dict[str, Any] = {
        "schema_version": 1,
        "repo": str(repo),
        "temp_root": str(root),
        "python": sys.version,
        "platform": platform.platform(),
        "timeout_sec": timeout_sec,
        "phases": {},
    }

    phases: dict[str, dict[str, Any]] = result["phases"]
    phases["wheel_build"] = _run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheel_dir), str(repo)],
        cwd=root,
        timeout_sec=timeout_sec,
    )
    wheels = sorted(wheel_dir.glob("auto_tessell-*.whl"))
    if not _phase_pass(phases["wheel_build"]) or len(wheels) != 1:
        result["status"] = "fail"
        result["wheel_count"] = len(wheels)
        return result

    wheel = wheels[0]
    result["wheel"] = {
        "filename": wheel.name,
        "sha256": _sha256(wheel),
        "bytes": wheel.stat().st_size,
    }
    venv_dir = root / "venv"
    started = time.perf_counter()
    try:
        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    except Exception as error:  # pragma: no cover - platform setup failure
        phases["venv_create"] = {
            "status": "fail",
            "duration_sec": round(time.perf_counter() - started, 3),
            "error": repr(error),
        }
        result["status"] = "fail"
        return result
    phases["venv_create"] = {
        "status": "pass",
        "duration_sec": round(time.perf_counter() - started, 3),
    }

    python = _venv_executable(venv_dir, "python")
    phases["wheel_install"] = _run(
        [str(python), "-m", "pip", "install", str(wheel)],
        cwd=root,
        timeout_sec=timeout_sec,
    )
    if not _phase_pass(phases["wheel_install"]):
        result["status"] = "fail"
        return result

    phases["installed_version"] = _run(
        [
            str(python),
            "-c",
            "import importlib.metadata; print(importlib.metadata.version('auto-tessell'))",
        ],
        cwd=root,
        timeout_sec=timeout_sec,
    )
    cli = _venv_executable(venv_dir, "auto-tessell")
    phases["cli_help"] = _run([str(cli), "--help"], cwd=root, timeout_sec=timeout_sec)
    phases["cli_analyze_sphere"] = _run(
        [str(cli), "analyze", str(fixture)],
        cwd=root,
        timeout_sec=timeout_sec,
    )
    result["status"] = "pass" if all(_phase_pass(phase) for phase in phases.values()) else "fail"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    if args.timeout_sec <= 0:
        parser.error("--timeout-sec must be positive")

    try:
        report = verify(args.repo, args.timeout_sec)
    except ValueError as error:
        report = {"schema_version": 1, "status": "fail", "error": str(error)}
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output_json is not None:
        args.output_json.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
