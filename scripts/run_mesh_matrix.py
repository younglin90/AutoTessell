#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Iterable


def _parse_timeout_map(items: Iterable[str]) -> dict[str, int]:
    """'key=sec' 목록을 파싱한다."""
    out: dict[str, int] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError(f"Invalid map entry (expected key=sec): {item!r}")
        sec = int(value)
        if sec <= 0:
            raise ValueError(f"Timeout must be > 0: {item!r}")
        out[key.strip()] = sec
    return out


def _parse_positive_int_map(items: Iterable[str]) -> dict[str, int]:
    """'key=int' 목록을 파싱한다 (int > 0)."""
    out: dict[str, int] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError(f"Invalid map entry (expected key=int): {item!r}")
        val = int(value)
        if val <= 0:
            raise ValueError(f"Value must be > 0: {item!r}")
        out[key.strip()] = val
    return out


def _resolve_timeout(
    *,
    default_sec: int,
    quality: str,
    tier: str,
    remesh_engine: str,
    by_quality: dict[str, int],
    by_tier: dict[str, int],
    by_remesh: dict[str, int],
) -> int:
    """조합별 timeout을 계산한다."""
    sec = default_sec
    sec = max(sec, by_quality.get(quality, sec))
    sec = max(sec, by_tier.get(tier, sec))
    sec = max(sec, by_remesh.get(remesh_engine, sec))
    return sec


def _resolve_max_iterations(
    *,
    default_iter: int,
    quality: str,
    tier: str,
    by_quality: dict[str, int],
    by_tier: dict[str, int],
) -> int:
    """조합별 max-iterations를 계산한다."""
    it = default_iter
    it = max(it, by_quality.get(quality, it))
    it = max(it, by_tier.get(tier, it))
    return it


def _profile_timeout_floor(*, profile: str, quality: str, tier: str, remesh_engine: str) -> int:
    """프로파일별 최소 timeout 하한값."""
    if profile != "fast":
        return 0
    # fine 품질에서 snappy/cfmesh/netgen/tetwild는 12~20초로는 빈번히 timeout됨
    if quality == "fine":
        if tier in {"snappy", "cfmesh"}:
            return 90
        if tier in {"netgen", "tetwild"}:
            return 60
        if tier == "auto":
            return 60
    if quality == "standard":
        if tier in {"snappy", "cfmesh"}:
            return 45
    return 0


def _profile_max_iterations(*, profile: str, quality: str, tier: str) -> int:
    """프로파일별 최대 재시도 횟수."""
    if profile == "fast" and quality == "fine" and tier in {"auto", "netgen", "tetwild"}:
        return 2
    return 1


def _extract_error_text(merged: str) -> str:
    # 1) CLI가 출력한 요약 오류를 최우선 사용
    error_lines = [ln.strip() for ln in merged.splitlines() if "[오류]" in ln]
    if error_lines:
        return error_lines[-1]

    # 2) 파이프라인 최종 실패 문구를 우선 사용
    if "All mesh generation tiers failed" in merged:
        return "All mesh generation tiers failed"
    m = re.findall(r"Failed after \d+ iterations", merged)
    if m:
        return m[-1]

    # 3) 그 외에는 하단의 ERROR/FATAL 라인으로 보조 추출
    err = ""
    for line in merged.splitlines()[::-1]:
        if (
            "ERROR" in line
            or "FATAL" in line
        ):
            err = line.strip()
            break
    if not err:
        err = "; ".join([x.strip() for x in merged.splitlines()[-4:] if x.strip()])[:500]
    return err


def classify_failure(status: str, error: str) -> str:
    """실패/타임아웃 원인을 카테고리로 분류한다."""
    if status == "pass":
        return "pass"
    if status == "timeout":
        return "timeout"
    msg = (error or "").lower()
    if "all mesh generation tiers failed" in msg:
        return "all_tiers_failed"
    if "no module named" in msg or "not installed" in msg:
        return "dependency_missing"
    if "import failed" in msg or "모듈 import 실패" in msg:
        return "engine_import_failed"
    if "foam fatal" in msg or "openfoam utility" in msg or "checkmesh" in msg:
        return "openfoam_failure"
    if "failed after" in msg:
        return "iteration_exhausted"
    if "conversion" in msg or "cad" in msg:
        return "conversion_failure"
    return "unknown_failure"


def _runtime_profile_args(*, profile: str, quality: str, tier: str, remesh_engine: str) -> list[str]:
    """매트릭스 실행 속도/안정성 프로파일에 따른 CLI 인자를 구성한다."""
    if profile == "balanced":
        return []
    if profile != "fast":
        raise ValueError(f"Unknown runtime profile: {profile}")

    out: list[str] = []
    # 대형 케이스에서 타임아웃을 줄이기 위한 보수적 완화값
    if tier in {"auto", "core", "snappy", "cfmesh"}:
        out.extend(["--base-cell-num", "20"])
    # fine 품질에서 netgen/tetwild를 과도하게 거칠게 만들면 품질 FAIL이 증가하므로 제외
    if quality != "fine" and tier in {"netgen", "tetwild"}:
        out.extend(["--element-size", "0.08"])
    if remesh_engine not in {"auto", "none"}:
        out.extend(["--remesh-target-faces", "3000"])
    if quality == "fine":
        out.extend(["--base-cell-num", "30"])
        # fine + strict-tier 매트릭스는 timeout 감소가 우선이므로 tier별 완화값 적용
        if tier == "snappy":
            out.extend(["--base-cell-num", "16", "--snappy-castellated-level", "1,2"])
        elif tier == "cfmesh":
            out.extend(["--base-cell-num", "16"])
        elif tier in {"netgen", "tetwild"}:
            out.extend(["--element-size", "0.06"])
    return out


def _run_one(
    python_bin: str,
    repo_root: Path,
    input_path: Path,
    quality: str,
    tier: str,
    remesh_engine: str,
    timeout_sec: int,
    runtime_profile: str,
    extra_cli_args: list[str],
    max_iterations: int,
) -> dict[str, object]:
    out_dir = (
        repo_root
        / "_matrix_runs"
        / f"mx_{input_path.stem}_{quality}_{tier}_{remesh_engine}".replace(".", "_")
    )
    cmd = [
        python_bin,
        "-m",
        "cli.main",
        "run",
        str(input_path),
        "--output",
        str(out_dir),
        "--quality",
        quality,
        "--tier",
        tier,
        "--remesh-engine",
        remesh_engine,
        "--checker-engine",
        "native",
        "--max-iterations",
        str(max_iterations),
    ]
    # fast+fine 조합은 fallback을 허용해 FAIL을 줄이고 timeout/pass로 유도
    use_strict_tier = tier != "auto" and not (runtime_profile == "fast" and quality == "fine")
    if use_strict_tier:
        cmd.append("--strict-tier")
    cmd.extend(
        _runtime_profile_args(
            profile=runtime_profile,
            quality=quality,
            tier=tier,
            remesh_engine=remesh_engine,
        )
    )
    cmd.extend(extra_cli_args)
    start = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            # 프로세스 트리 강제 종료 (자식 OpenFOAM/mesher 포함)
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return {
                "input": str(input_path),
                "quality": quality,
                "tier": tier,
                "remesh_engine": remesh_engine,
                "status": "timeout",
                "elapsed_sec": float(timeout_sec),
                "timeout_sec": timeout_sec,
                "max_iterations": max_iterations,
                "failure_category": "timeout",
                "error": f"timeout({timeout_sec}s)",
            }
        elapsed = round(time.time() - start, 2)
        merged = (stdout or "") + "\n" + (stderr or "")
        status = "pass" if proc.returncode == 0 else "fail"
        err = _extract_error_text(merged)
        failure_category = classify_failure(status, err)
        return {
            "input": str(input_path),
            "quality": quality,
            "tier": tier,
            "remesh_engine": remesh_engine,
            "status": status,
            "elapsed_sec": elapsed,
            "timeout_sec": timeout_sec,
            "max_iterations": max_iterations,
            "failure_category": failure_category,
            "error": err,
        }
    except Exception as exc:
        return {
            "input": str(input_path),
            "quality": quality,
            "tier": tier,
            "remesh_engine": remesh_engine,
            "status": "fail",
            "elapsed_sec": round(time.time() - start, 2),
            "timeout_sec": timeout_sec,
            "max_iterations": max_iterations,
            "failure_category": "runner_failure",
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run mesh pipeline matrix and save summary.")
    parser.add_argument("--repo-root", default=".", help="repo root path")
    parser.add_argument("--python-bin", default=".venv/bin/python", help="python executable path")
    parser.add_argument("--input", action="append", required=True, help="input file (repeatable)")
    parser.add_argument("--quality", action="append", default=None)
    parser.add_argument(
        "--tier",
        action="append",
        default=None,
    )
    parser.add_argument(
        "--remesh-engine",
        action="append",
        default=None,
    )
    parser.add_argument("--timeout-sec", type=int, default=60, help="base timeout for each combo")
    parser.add_argument(
        "--timeout-by-quality",
        action="append",
        default=[],
        metavar="QUALITY=SEC",
        help="override timeout by quality (repeatable)",
    )
    parser.add_argument(
        "--timeout-by-tier",
        action="append",
        default=[],
        metavar="TIER=SEC",
        help="override timeout by tier (repeatable)",
    )
    parser.add_argument(
        "--timeout-by-remesh",
        action="append",
        default=[],
        metavar="REMESH=SEC",
        help="override timeout by remesh_engine (repeatable)",
    )
    parser.add_argument("--out-prefix", default="matrix")
    parser.add_argument(
        "--runtime-profile",
        choices=["balanced", "fast"],
        default="balanced",
        help="matrix 실행 프로파일 (fast=타임아웃 완화용 보수적 파라미터 적용)",
    )
    parser.add_argument(
        "--append-arg",
        action="append",
        default=[],
        metavar="CLI_ARG",
        help="각 run 명령에 추가할 raw CLI 인자 (반복 가능)",
    )
    parser.add_argument(
        "--max-iter-by-quality",
        action="append",
        default=[],
        metavar="QUALITY=N",
        help="override max-iterations by quality (repeatable)",
    )
    parser.add_argument(
        "--max-iter-by-tier",
        action="append",
        default=[],
        metavar="TIER=N",
        help="override max-iterations by tier (repeatable)",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    python_bin = str((repo_root / args.python_bin).resolve())
    inputs = [Path(x).expanduser().resolve() for x in args.input]
    default_qualities = ["draft", "standard", "fine"]
    default_tiers = ["auto", "core", "netgen", "snappy", "cfmesh", "tetwild"]
    default_remesh = ["auto", "quadwild", "vorpalite", "pyacvd", "pymeshlab", "none"]

    qualities = list(dict.fromkeys(args.quality or default_qualities))
    tiers = list(dict.fromkeys(args.tier or default_tiers))
    remesh_engines = list(dict.fromkeys(args.remesh_engine or default_remesh))
    timeout_by_quality = _parse_timeout_map(args.timeout_by_quality)
    timeout_by_tier = _parse_timeout_map(args.timeout_by_tier)
    timeout_by_remesh = _parse_timeout_map(args.timeout_by_remesh)
    max_iter_by_quality = _parse_positive_int_map(args.max_iter_by_quality)
    max_iter_by_tier = _parse_positive_int_map(args.max_iter_by_tier)

    results: list[dict[str, object]] = []
    total = len(inputs) * len(qualities) * len(tiers) * len(remesh_engines)
    i = 0
    for input_path in inputs:
        for quality in qualities:
            for tier in tiers:
                for remesh_engine in remesh_engines:
                    i += 1
                    timeout_sec = _resolve_timeout(
                        default_sec=args.timeout_sec,
                        quality=quality,
                        tier=tier,
                        remesh_engine=remesh_engine,
                        by_quality=timeout_by_quality,
                        by_tier=timeout_by_tier,
                        by_remesh=timeout_by_remesh,
                    )
                    timeout_sec = max(
                        timeout_sec,
                        _profile_timeout_floor(
                            profile=args.runtime_profile,
                            quality=quality,
                            tier=tier,
                            remesh_engine=remesh_engine,
                        ),
                    )
                    default_max_iter = _profile_max_iterations(
                        profile=args.runtime_profile,
                        quality=quality,
                        tier=tier,
                    )
                    max_iterations = _resolve_max_iterations(
                        default_iter=default_max_iter,
                        quality=quality,
                        tier=tier,
                        by_quality=max_iter_by_quality,
                        by_tier=max_iter_by_tier,
                    )
                    print(
                        f"start {i}/{total} quality={quality} tier={tier} remesh={remesh_engine} "
                        f"timeout={timeout_sec}s max_iter={max_iterations}"
                    )
                    row = _run_one(
                        python_bin=python_bin,
                        repo_root=repo_root,
                        input_path=input_path,
                        quality=quality,
                        tier=tier,
                        remesh_engine=remesh_engine,
                        timeout_sec=timeout_sec,
                        runtime_profile=args.runtime_profile,
                        extra_cli_args=list(args.append_arg),
                        max_iterations=max_iterations,
                    )
                    results.append(row)
                    if i % 10 == 0 or i == total:
                        p = sum(1 for x in results if x["status"] == "pass")
                        f = sum(1 for x in results if x["status"] == "fail")
                        t = sum(1 for x in results if x["status"] == "timeout")
                        print(f"progress {i}/{total} pass={p} fail={f} timeout={t}")

    summary: dict[str, object] = {
        "total": len(results),
        "pass": sum(1 for r in results if r["status"] == "pass"),
        "fail": sum(1 for r in results if r["status"] == "fail"),
        "timeout": sum(1 for r in results if r["status"] == "timeout"),
        "by_failure_category": {},
        "by_tier": {},
        "by_quality": {},
        "by_input": {},
    }
    for key, bucket in (
        ("tier", "by_tier"),
        ("quality", "by_quality"),
        ("input", "by_input"),
        ("failure_category", "by_failure_category"),
    ):
        d: dict[str, dict[str, int]] = {}
        for r in results:
            k = str(r[key])
            item = d.setdefault(k, {"pass": 0, "fail": 0, "timeout": 0, "total": 0})
            item[str(r["status"])] += 1
            item["total"] += 1
        summary[bucket] = d

    reports_dir = repo_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    json_path = reports_dir / f"{args.out_prefix}_results.json"
    csv_path = reports_dir / f"{args.out_prefix}_results.csv"
    summary_path = reports_dir / f"{args.out_prefix}_summary.json"

    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "input",
                "quality",
                "tier",
                "remesh_engine",
                "status",
                "elapsed_sec",
                "timeout_sec",
                "max_iterations",
                "failure_category",
                "error",
            ],
        )
        w.writeheader()
        w.writerows(results)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"saved: {json_path}")
    print(f"saved: {csv_path}")
    print(f"saved: {summary_path}")


if __name__ == "__main__":
    main()
