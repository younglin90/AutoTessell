#!/usr/bin/env python3
"""Run the native-poly L3 test corpus in isolated, immutable-head shards.

The runner is validation infrastructure.  It does not modify product code or
test selection semantics.  Every selected pytest module is collected first,
then executed unchanged in a new process group.  A timeout is a recorded L3
failure, never a pass or a skip, and does not hide later modules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SEC = 240.0
CORPUS_PATTERNS = (
    "test_native_poly*.py",
    "test_native_polymesh*.py",
    "test_tier_native_poly*.py",
    "test_poly_bl_transition*.py",
)
RUNNER_TEST = "tests/test_native_poly_l3_corpus_runner.py"


class CorpusError(RuntimeError):
    """A fail-closed corpus-runner contract violation."""


@dataclass(frozen=True)
class GitIdentity:
    head: str
    tree: str


@dataclass(frozen=True)
class ProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_sec: float
    timed_out: bool
    process_group_alive: bool


@dataclass(frozen=True)
class JUnitCounts:
    tests: int
    failures: int
    errors: int
    skipped: int


def _run_checked(command: Sequence[str], *, cwd: Path) -> str:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr)[-2000:]
        raise CorpusError(f"command failed ({result.returncode}): {command!r}\n{detail}")
    return result.stdout.strip()


def capture_git_identity(repository_root: Path) -> GitIdentity:
    """Return HEAD/tree only when the repository worktree is exactly clean."""
    status = _run_checked(
        ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
        cwd=repository_root,
    )
    if status:
        raise CorpusError("repository is not clean; immutable-head run refused")
    return GitIdentity(
        head=_run_checked(["git", "rev-parse", "HEAD"], cwd=repository_root),
        tree=_run_checked(["git", "rev-parse", "HEAD^{tree}"], cwd=repository_root),
    )


def require_git_identity(repository_root: Path, expected: GitIdentity) -> None:
    """Fail if tracked state, HEAD, or tree changed after capture."""
    actual = capture_git_identity(repository_root)
    if actual != expected:
        raise CorpusError(
            "immutable-head identity changed: "
            f"expected={asdict(expected)!r} actual={asdict(actual)!r}"
        )


def discover_modules(repository_root: Path) -> tuple[str, ...]:
    """Discover the declared native-poly L3 module family deterministically."""
    tests_dir = repository_root / "tests"
    modules = {
        path.relative_to(repository_root).as_posix()
        for pattern in CORPUS_PATTERNS
        for path in tests_dir.glob(pattern)
        if path.is_file()
    }
    modules.discard(RUNNER_TEST)
    if not modules:
        raise CorpusError("native-poly corpus discovery returned no modules")
    return tuple(sorted(modules))


def parse_collected_nodeids(output: str, modules: Sequence[str]) -> tuple[str, ...]:
    """Parse pytest ``--collect-only -q`` output without trusting its summary."""
    module_set = set(modules)
    nodeids = tuple(
        line.strip()
        for line in output.splitlines()
        if "::" in line and line.split("::", 1)[0] in module_set
    )
    if not nodeids:
        raise CorpusError("pytest collection returned no native-poly nodeids")
    if len(nodeids) != len(set(nodeids)):
        raise CorpusError("pytest collection returned duplicate nodeids")
    covered = {nodeid.split("::", 1)[0] for nodeid in nodeids}
    missing_modules = module_set - covered
    if missing_modules:
        raise CorpusError(f"modules without collected tests: {sorted(missing_modules)!r}")
    return nodeids


def collect_manifest(
    *, repository_root: Path, python_bin: str, identity: GitIdentity
) -> dict[str, Any]:
    modules = discover_modules(repository_root)
    command = [python_bin, "-m", "pytest", "--collect-only", "-q", *modules]
    result = run_process_group(
        command,
        cwd=repository_root,
        timeout_sec=120.0,
        environment=_single_thread_environment(),
    )
    require_git_identity(repository_root, identity)
    if result.timed_out or result.returncode != 0 or result.process_group_alive:
        detail = (result.stdout + result.stderr)[-2000:]
        raise CorpusError(f"pytest collection failed closed: {detail}")
    nodeids = parse_collected_nodeids(result.stdout, modules)
    by_module = {
        module: [nodeid for nodeid in nodeids if nodeid.startswith(f"{module}::")]
        for module in modules
    }
    manifest_sha256 = _manifest_digest(modules=modules, nodeids=nodeids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "native_poly_l3_manifest",
        "head": identity.head,
        "tree": identity.tree,
        "modules": list(modules),
        "nodeids": list(nodeids),
        "nodeids_by_module": by_module,
        "module_count": len(modules),
        "nodeid_count": len(nodeids),
        "manifest_sha256": manifest_sha256,
    }


def _manifest_digest(*, modules: Sequence[str], nodeids: Sequence[str]) -> str:
    digest_input = json.dumps(
        {"modules": list(modules), "nodeids": list(nodeids)},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()


def _single_thread_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
    )
    return environment


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(process: subprocess.Popen[str], grace_sec: float) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace_sec)
    except subprocess.TimeoutExpired:
        pass
    if _process_group_exists(process.pid):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        pass


def run_process_group(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_sec: float,
    environment: Mapping[str, str] | None = None,
    termination_grace_sec: float = 2.0,
) -> ProcessResult:
    """Run one command in a new POSIX process group and contain timeouts."""
    if timeout_sec <= 0.0:
        raise ValueError("timeout_sec must be positive")
    if os.name != "posix":
        raise CorpusError("native-poly L3 runner requires a POSIX/WSL environment")

    started = time.monotonic()
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=None if environment is None else dict(environment),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_group(process, termination_grace_sec)
        stdout, stderr = process.communicate()
    elapsed = time.monotonic() - started
    group_alive = _process_group_exists(process.pid)
    if group_alive:
        _terminate_process_group(process, 0.1)
        group_alive = _process_group_exists(process.pid)
    return ProcessResult(
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        elapsed_sec=elapsed,
        timed_out=timed_out,
        process_group_alive=group_alive,
    )


def parse_junit_counts(path: Path) -> JUnitCounts:
    if not path.exists():
        raise CorpusError("pytest did not write JUnit XML")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise CorpusError(f"invalid JUnit XML: {exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise CorpusError("JUnit XML contains no testsuite")
    return JUnitCounts(
        tests=sum(int(suite.attrib.get("tests", "0")) for suite in suites),
        failures=sum(int(suite.attrib.get("failures", "0")) for suite in suites),
        errors=sum(int(suite.attrib.get("errors", "0")) for suite in suites),
        skipped=sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
    )


def parse_xpass_nodeids(output: str) -> tuple[str, ...]:
    """Read only pytest's ``-rX`` summary records, never ordinary PASS text."""
    prefix = "XPASS "
    nodeids: list[str] = []
    for line in output.splitlines():
        if not line.startswith(prefix):
            continue
        nodeid = line[len(prefix) :].split(" - ", 1)[0].strip()
        if not nodeid:
            raise CorpusError("pytest emitted an empty XPASS summary record")
        nodeids.append(nodeid)
    if len(nodeids) != len(set(nodeids)):
        raise CorpusError("pytest emitted duplicate XPASS summary records")
    return tuple(nodeids)


def classify_module_result(
    *,
    process: ProcessResult,
    counts: JUnitCounts | None,
    expected_nodeids: int,
    xpassed_nodeids: Sequence[str] = (),
) -> str:
    """Classify a module without converting missing evidence into success."""
    if process.process_group_alive:
        return "process_leak"
    if process.timed_out:
        return "timeout"
    if counts is None or counts.tests != expected_nodeids:
        return "runner_error"
    if xpassed_nodeids:
        return "xpassed"
    if process.returncode != 0:
        return "failed" if counts.failures or counts.errors else "runner_error"
    if counts.failures or counts.errors:
        return "runner_error"
    if counts.skipped == counts.tests:
        return "skipped"
    if counts.skipped:
        return "passed_with_skips"
    return "passed"


def module_shard(module: str, modules: Sequence[str], shard_count: int) -> int:
    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    try:
        index = list(modules).index(module)
    except ValueError as exc:
        raise CorpusError(f"unknown corpus module: {module}") from exc
    return index % shard_count


def run_module(
    *,
    repository_root: Path,
    python_bin: str,
    module: str,
    nodeids: Sequence[str],
    timeout_sec: float,
    identity: GitIdentity,
) -> dict[str, Any]:
    require_git_identity(repository_root, identity)
    with tempfile.TemporaryDirectory(prefix="autotessell-poly-l3-") as temporary:
        junit_path = Path(temporary) / "pytest.xml"
        command = [
            python_bin,
            "-m",
            "pytest",
            "-q",
            "-rxX",
            module,
            f"--junitxml={junit_path}",
        ]
        process = run_process_group(
            command,
            cwd=repository_root,
            timeout_sec=timeout_sec,
            environment=_single_thread_environment(),
        )
        counts: JUnitCounts | None = None
        junit_error: str | None = None
        if not process.timed_out:
            try:
                counts = parse_junit_counts(junit_path)
            except CorpusError as exc:
                junit_error = str(exc)
    require_git_identity(repository_root, identity)
    try:
        xpassed_nodeids = parse_xpass_nodeids(process.stdout)
    except CorpusError as exc:
        xpassed_nodeids = ()
        junit_error = str(exc) if junit_error is None else f"{junit_error}; {exc}"
    classification = classify_module_result(
        process=process,
        counts=counts,
        expected_nodeids=len(nodeids),
        xpassed_nodeids=xpassed_nodeids,
    )
    if junit_error is not None and classification not in {"timeout", "process_leak"}:
        classification = "runner_error"
    return {
        "module": module,
        "nodeids": list(nodeids),
        "nodeid_count": len(nodeids),
        "classification": classification,
        "returncode": process.returncode,
        "timed_out": process.timed_out,
        "process_group_alive": process.process_group_alive,
        "elapsed_sec": round(process.elapsed_sec, 6),
        "junit_counts": None if counts is None else asdict(counts),
        "xpassed_nodeids": list(xpassed_nodeids),
        "xpassed_count": len(xpassed_nodeids),
        "junit_error": junit_error,
        "stdout_tail": process.stdout[-4000:],
        "stderr_tail": process.stderr[-4000:],
    }


def make_shard_payload(
    *, manifest: Mapping[str, Any], shard_index: int, shard_count: int
) -> dict[str, Any]:
    if shard_count <= 0 or not 0 <= shard_index < shard_count:
        raise CorpusError("shard index/count are invalid")
    modules = list(manifest["modules"])
    selected = [
        module for module in modules if module_shard(module, modules, shard_count) == shard_index
    ]
    if not selected:
        raise CorpusError("selected shard contains no modules")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "native_poly_l3_shard",
        "head": manifest["head"],
        "tree": manifest["tree"],
        "manifest_sha256": manifest["manifest_sha256"],
        "manifest_nodeids": manifest["nodeids"],
        "manifest_modules": modules,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "selected_modules": selected,
        "results": [],
    }


def merge_shard_payloads(payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge only a complete, same-head shard set with exact node accounting."""
    if not payloads:
        raise CorpusError("no shard payloads supplied")
    first = payloads[0]
    identity = (first.get("head"), first.get("tree"), first.get("manifest_sha256"))
    shard_count = int(first.get("shard_count", 0))
    if shard_count <= 0:
        raise CorpusError("invalid shard_count")
    by_index: dict[int, Mapping[str, Any]] = {}
    for payload in payloads:
        if payload.get("kind") != "native_poly_l3_shard":
            raise CorpusError("unexpected shard payload kind")
        current_identity = (
            payload.get("head"),
            payload.get("tree"),
            payload.get("manifest_sha256"),
        )
        if current_identity != identity or int(payload.get("shard_count", 0)) != shard_count:
            raise CorpusError("shards do not share one immutable manifest identity")
        index = int(payload.get("shard_index", -1))
        if index in by_index:
            raise CorpusError(f"duplicate shard index: {index}")
        by_index[index] = payload
    expected_indices = set(range(shard_count))
    if set(by_index) != expected_indices:
        raise CorpusError(
            f"shard index gap: expected={sorted(expected_indices)} actual={sorted(by_index)}"
        )

    manifest_nodeids = list(first.get("manifest_nodeids", []))
    manifest_modules = list(first.get("manifest_modules", []))
    if not manifest_nodeids or not manifest_modules:
        raise CorpusError("empty manifest embedded in shard")
    if len(manifest_nodeids) != len(set(manifest_nodeids)):
        raise CorpusError("manifest contains duplicate nodeids")
    expected_digest = _manifest_digest(
        modules=manifest_modules,
        nodeids=manifest_nodeids,
    )
    if expected_digest != identity[2]:
        raise CorpusError("embedded manifest digest is invalid")

    results: list[Mapping[str, Any]] = []
    seen_modules: set[str] = set()
    seen_nodeids: set[str] = set()
    for index in range(shard_count):
        payload = by_index[index]
        if (
            list(payload.get("manifest_nodeids", [])) != manifest_nodeids
            or list(payload.get("manifest_modules", [])) != manifest_modules
        ):
            raise CorpusError(f"shard {index} embedded manifest mismatch")
        selected = list(payload.get("selected_modules", []))
        expected_selected = [
            module
            for module in manifest_modules
            if module_shard(module, manifest_modules, shard_count) == index
        ]
        if selected != expected_selected:
            raise CorpusError(f"shard {index} deterministic assignment mismatch")
        actual = [str(result.get("module")) for result in payload.get("results", [])]
        if actual != selected:
            raise CorpusError(f"shard {index} result order/coverage mismatch")
        for result in payload.get("results", []):
            module = str(result.get("module"))
            nodeids = list(result.get("nodeids", []))
            if module in seen_modules:
                raise CorpusError(f"duplicate module result: {module}")
            if seen_nodeids.intersection(nodeids):
                raise CorpusError(f"duplicate nodeid result in module: {module}")
            if int(result.get("nodeid_count", -1)) != len(nodeids):
                raise CorpusError(f"nodeid count mismatch in module: {module}")
            if result.get("classification") not in {
                "passed",
                "passed_with_skips",
                "skipped",
                "failed",
                "timeout",
                "runner_error",
                "process_leak",
                "xpassed",
            }:
                raise CorpusError(f"unknown classification in module: {module}")
            seen_modules.add(module)
            seen_nodeids.update(nodeids)
            results.append(result)
    if seen_modules != set(manifest_modules):
        raise CorpusError("module accounting gap")
    if seen_nodeids != set(manifest_nodeids):
        raise CorpusError("nodeid accounting gap")

    classification_counts: dict[str, int] = {}
    for result in results:
        key = str(result["classification"])
        classification_counts[key] = classification_counts.get(key, 0) + 1
    release_pass = set(classification_counts).issubset({"passed"})
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "native_poly_l3_merged",
        "head": identity[0],
        "tree": identity[1],
        "manifest_sha256": identity[2],
        "module_count": len(seen_modules),
        "nodeid_count": len(seen_nodeids),
        "accounted_nodeids": len(seen_nodeids),
        "accounting_ratio": len(seen_nodeids) / len(manifest_nodeids),
        "classification_counts": classification_counts,
        "release_pass": release_pass,
        "results": results,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"cannot read shard JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CorpusError(f"shard JSON is not an object: {path}")
    return value


def _parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--output-dir", type=Path, default=Path("autoresearch-results/poly-l3"))
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int, default=4)
    parser.add_argument("--timeout-sec", type=float, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--merge", nargs="+", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    repository_root = arguments.repo_root.resolve()
    output_dir = (
        arguments.output_dir
        if arguments.output_dir.is_absolute()
        else repository_root / arguments.output_dir
    )
    try:
        if arguments.merge:
            payload = merge_shard_payloads([_read_json(path) for path in arguments.merge])
            identity = capture_git_identity(repository_root)
            if (payload["head"], payload["tree"]) != (identity.head, identity.tree):
                raise CorpusError("merged evidence does not match current immutable HEAD/tree")
            path = output_dir / f"merged-{identity.head[:12]}.json"
            _write_json(path, payload)
            print(json.dumps({"output": str(path), **payload}, sort_keys=True))
            return 0 if payload["release_pass"] else 1

        identity = capture_git_identity(repository_root)
        manifest = collect_manifest(
            repository_root=repository_root,
            python_bin=arguments.python_bin,
            identity=identity,
        )
        if arguments.collect_only:
            path = output_dir / f"manifest-{identity.head[:12]}.json"
            _write_json(path, manifest)
            print(json.dumps({"output": str(path), **manifest}, sort_keys=True))
            return 0
        if arguments.shard_index is None:
            raise CorpusError("--shard-index is required unless --collect-only or --merge is used")
        payload = make_shard_payload(
            manifest=manifest,
            shard_index=arguments.shard_index,
            shard_count=arguments.shard_count,
        )
        by_module = manifest["nodeids_by_module"]
        for module in payload["selected_modules"]:
            result = run_module(
                repository_root=repository_root,
                python_bin=arguments.python_bin,
                module=module,
                nodeids=by_module[module],
                timeout_sec=arguments.timeout_sec,
                identity=identity,
            )
            payload["results"].append(result)
            print(json.dumps(result, sort_keys=True))
        require_git_identity(repository_root, identity)
        path = output_dir / (
            f"shard-{arguments.shard_index}-of-{arguments.shard_count}-{identity.head[:12]}.json"
        )
        _write_json(path, payload)
        bad = [result for result in payload["results"] if result["classification"] != "passed"]
        print(json.dumps({"output": str(path), "bad_modules": len(bad)}, sort_keys=True))
        return 0 if not bad else 1
    except CorpusError as exc:
        print(f"native-poly L3 corpus refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
