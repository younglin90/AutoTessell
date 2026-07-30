"""Fail-closed contracts for the native-poly immutable L3 shard runner."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run_native_poly_l3_corpus.py"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("native_poly_l3_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _make_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Poly L3 Test")
    _git(repository, "config", "user.email", "poly-l3@example.invalid")
    (repository / "tracked.txt").write_text("frozen\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-q", "-m", "frozen")
    return repository


def _process(
    *,
    returncode: int | None = 0,
    timed_out: bool = False,
    process_group_alive: bool = False,
) -> object:
    return RUNNER.ProcessResult(
        returncode=returncode,
        stdout="",
        stderr="",
        elapsed_sec=0.01,
        timed_out=timed_out,
        process_group_alive=process_group_alive,
    )


def _result(module: str, nodeids: list[str], classification: str = "passed") -> dict[str, object]:
    return {
        "module": module,
        "nodeids": nodeids,
        "nodeid_count": len(nodeids),
        "classification": classification,
    }


def _shard(
    *,
    index: int,
    modules: list[str],
    nodeids: list[str],
    results: list[dict[str, object]],
    count: int = 2,
) -> dict[str, object]:
    manifest_sha256 = RUNNER._manifest_digest(modules=modules, nodeids=nodeids)
    return {
        "kind": "native_poly_l3_shard",
        "head": "a" * 40,
        "tree": "b" * 40,
        "manifest_sha256": manifest_sha256,
        "manifest_nodeids": nodeids,
        "manifest_modules": modules,
        "shard_index": index,
        "shard_count": count,
        "selected_modules": [str(result["module"]) for result in results],
        "results": results,
    }


def test_git_identity_rejects_dirty_state_and_head_move(tmp_path: Path) -> None:
    repository = _make_repository(tmp_path)
    identity = RUNNER.capture_git_identity(repository)

    (repository / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RUNNER.CorpusError, match="not clean"):
        RUNNER.require_git_identity(repository, identity)

    (repository / "tracked.txt").write_text("frozen\n", encoding="utf-8")
    _git(repository, "commit", "--allow-empty", "-q", "-m", "move-head")
    with pytest.raises(RUNNER.CorpusError, match="identity changed"):
        RUNNER.require_git_identity(repository, identity)


@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX/WSL")
def test_timeout_kills_entire_process_group_and_returns(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    program = (
        "import pathlib,subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c',"
        "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)']);"
        "pathlib.Path(sys.argv[1]).write_text(str(p.pid),encoding='utf-8');"
        "time.sleep(0.2);"
        "time.sleep(60)"
    )
    result = RUNNER.run_process_group(
        [sys.executable, "-c", program, str(child_pid_path)],
        cwd=tmp_path,
        timeout_sec=0.5,
        termination_grace_sec=0.1,
    )

    assert result.timed_out
    assert not result.process_group_alive
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2.0
    while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    if Path(f"/proc/{child_pid}").exists():
        status = Path(f"/proc/{child_pid}/status").read_text(encoding="utf-8")
        assert "State:\tZ" in status


def test_result_classification_is_fail_closed() -> None:
    passing = RUNNER.JUnitCounts(tests=3, failures=0, errors=0, skipped=0)
    skipped = RUNNER.JUnitCounts(tests=3, failures=0, errors=0, skipped=1)
    failing = RUNNER.JUnitCounts(tests=3, failures=1, errors=0, skipped=0)

    assert (
        RUNNER.classify_module_result(process=_process(), counts=passing, expected_nodeids=3)
        == "passed"
    )
    assert (
        RUNNER.classify_module_result(process=_process(), counts=skipped, expected_nodeids=3)
        == "passed_with_skips"
    )
    assert (
        RUNNER.classify_module_result(
            process=_process(returncode=1), counts=failing, expected_nodeids=3
        )
        == "failed"
    )
    assert (
        RUNNER.classify_module_result(
            process=_process(timed_out=True), counts=None, expected_nodeids=3
        )
        == "timeout"
    )
    assert (
        RUNNER.classify_module_result(
            process=_process(process_group_alive=True), counts=None, expected_nodeids=3
        )
        == "process_leak"
    )
    assert (
        RUNNER.classify_module_result(process=_process(), counts=None, expected_nodeids=3)
        == "runner_error"
    )
    assert (
        RUNNER.classify_module_result(process=_process(), counts=passing, expected_nodeids=4)
        == "runner_error"
    )


def test_merge_requires_exact_shards_and_node_accounting() -> None:
    modules = ["tests/test_native_poly_a.py", "tests/test_native_poly_b.py"]
    nodeids = [f"{modules[0]}::test_a", f"{modules[1]}::test_b"]
    shard0 = _shard(
        index=0,
        modules=modules,
        nodeids=nodeids,
        results=[_result(modules[0], [nodeids[0]])],
    )
    shard1 = _shard(
        index=1,
        modules=modules,
        nodeids=nodeids,
        results=[_result(modules[1], [nodeids[1]])],
    )

    merged = RUNNER.merge_shard_payloads([shard1, shard0])
    assert merged["accounted_nodeids"] == 2
    assert merged["accounting_ratio"] == 1.0
    assert merged["release_pass"] is True

    with pytest.raises(RUNNER.CorpusError, match="duplicate shard"):
        RUNNER.merge_shard_payloads([shard0, shard0])
    with pytest.raises(RUNNER.CorpusError, match="shard index gap"):
        RUNNER.merge_shard_payloads([shard0])

    duplicate = json.loads(json.dumps(shard1))
    duplicate["results"][0]["nodeids"] = [nodeids[0]]
    with pytest.raises(RUNNER.CorpusError, match="duplicate nodeid"):
        RUNNER.merge_shard_payloads([shard0, duplicate])

    gap = json.loads(json.dumps(shard1))
    gap["results"][0]["nodeids"] = []
    gap["results"][0]["nodeid_count"] = 0
    with pytest.raises(RUNNER.CorpusError, match="nodeid accounting gap"):
        RUNNER.merge_shard_payloads([shard0, gap])

    wrong_assignment = json.loads(json.dumps(shard1))
    wrong_assignment["selected_modules"] = [modules[0]]
    wrong_assignment["results"][0]["module"] = modules[0]
    with pytest.raises(RUNNER.CorpusError, match="deterministic assignment mismatch"):
        RUNNER.merge_shard_payloads([shard0, wrong_assignment])


def test_merge_refuses_identity_drift_and_nonpass_release() -> None:
    modules = ["tests/test_native_poly_a.py", "tests/test_native_poly_b.py"]
    nodeids = [f"{modules[0]}::test_a", f"{modules[1]}::test_b"]
    shard0 = _shard(
        index=0,
        modules=modules,
        nodeids=nodeids,
        results=[_result(modules[0], [nodeids[0]])],
    )
    shard1 = _shard(
        index=1,
        modules=modules,
        nodeids=nodeids,
        results=[_result(modules[1], [nodeids[1]], "timeout")],
    )
    merged = RUNNER.merge_shard_payloads([shard0, shard1])
    assert merged["release_pass"] is False
    assert merged["classification_counts"] == {"passed": 1, "timeout": 1}

    moved = json.loads(json.dumps(shard1))
    moved["tree"] = "d" * 40
    with pytest.raises(RUNNER.CorpusError, match="immutable manifest identity"):
        RUNNER.merge_shard_payloads([shard0, moved])

    corrupt = json.loads(json.dumps(shard1))
    corrupt["manifest_nodeids"] = [*nodeids, "tests/test_native_poly_b.py::test_extra"]
    with pytest.raises(RUNNER.CorpusError, match="embedded manifest mismatch"):
        RUNNER.merge_shard_payloads([shard0, corrupt])


def test_discovery_excludes_runner_self_but_includes_declared_families(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    expected = {
        "tests/test_native_poly_a.py",
        "tests/test_native_polymesh_b.py",
        "tests/test_tier_native_poly_c.py",
        "tests/test_poly_bl_transition_d.py",
    }
    for relative in expected | {RUNNER.RUNNER_TEST}:
        path = tmp_path / relative
        path.write_text("def test_x(): pass\n", encoding="utf-8")
    (tests / "test_unrelated.py").write_text("def test_x(): pass\n", encoding="utf-8")

    assert set(RUNNER.discover_modules(tmp_path)) == expected


def test_parse_collected_nodeids_rejects_duplicate_and_gap() -> None:
    modules = ("tests/test_native_poly_a.py", "tests/test_native_poly_b.py")
    valid = "\n".join(f"{module}::test_x" for module in modules)
    assert len(RUNNER.parse_collected_nodeids(valid, modules)) == 2

    with pytest.raises(RUNNER.CorpusError, match="duplicate nodeids"):
        RUNNER.parse_collected_nodeids(f"{valid}\n{modules[0]}::test_x", modules)
    with pytest.raises(RUNNER.CorpusError, match="modules without collected"):
        RUNNER.parse_collected_nodeids(f"{modules[0]}::test_x", modules)
