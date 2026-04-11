#!/usr/bin/env python3
"""모든 테스트 입력 포맷을 사용해 메싱 검증."""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def run_mesh_test(test_file: Path, quality: str = "draft") -> dict[str, Any]:
    """단일 테스트 케이스 메싱 검증."""
    result = {
        "file": test_file.name,
        "format": test_file.suffix.lower(),
        "size_mb": test_file.stat().st_size / (1024 * 1024),
        "status": "unknown",
        "time_s": 0.0,
        "cells": 0,
        "error": None,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir) / "case"

        t_start = time.monotonic()
        try:
            cmd = [
                "python3", "-m", "cli.main", "run",
                str(test_file),
                "-o", str(case_dir),
                "--quality", quality,
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(Path(__file__).parent.parent),
            )

            elapsed = time.monotonic() - t_start
            result["time_s"] = elapsed

            if proc.returncode == 0:
                result["status"] = "✅ success"

                # 메시 정보 추출
                quality_file = case_dir / "quality_report.json"
                if quality_file.exists():
                    with open(quality_file) as f:
                        qr = json.load(f)
                        result["cells"] = qr.get("mesh_statistics", {}).get("cells", 0)
                        result["verdict"] = qr.get("verdict", "unknown")
            else:
                result["status"] = "❌ failed"
                result["error"] = proc.stderr[:200] if proc.stderr else "Unknown error"

        except subprocess.TimeoutExpired:
            result["status"] = "⏱ timeout"
            result["error"] = "Timeout after 300s"
        except Exception as e:
            result["status"] = "⚠️ error"
            result["error"] = str(e)[:100]

    return result


def main():
    """모든 포맷 테스트."""
    repo_root = Path(__file__).parent.parent
    bench_dir = repo_root / "tests" / "benchmarks"

    print("\n" + "=" * 100)
    print("🔍 모든 테스트 입력 포맷 메싱 검증")
    print("=" * 100 + "\n")

    # 테스트 파일 수집 (모든 포맷)
    test_files = sorted(bench_dir.glob("*.*"))

    # 포맷별로 그룹화
    formats = {}
    for f in test_files:
        fmt = f.suffix.lower()
        if fmt not in formats:
            formats[fmt] = []
        formats[fmt].append(f)

    print(f"📊 포맷 요약:")
    for fmt, files in sorted(formats.items()):
        print(f"  {fmt:10} : {len(files):2}개")
    print()

    results = []
    total = len(test_files)

    print(f"🚀 메싱 검증 시작 ({total}개 파일):\n")
    print("-" * 100)

    for i, test_file in enumerate(test_files, 1):
        print(f"[{i:2}/{total}] {test_file.name:50}", end=" ", flush=True)

        result = run_mesh_test(test_file, quality="draft")
        results.append(result)

        status_icon = result["status"].split()[0]
        time_str = f"{result['time_s']:.1f}s" if result["time_s"] > 0 else "—"
        cells_str = f"{result['cells']:,}" if result["cells"] > 0 else "—"

        print(f"{status_icon} {time_str:>6} | {cells_str:>8} cells")

        if result["error"]:
            print(f"{'':52} ⚠️  {result['error']}")

    # 요약
    passed = sum(1 for r in results if "✅" in r["status"])
    timeout = sum(1 for r in results if "⏱" in r["status"])
    error = sum(1 for r in results if "⚠️" in r["status"])
    failed = sum(1 for r in results if "❌" in r["status"])

    print("\n" + "=" * 100)
    print(f"📊 검증 결과: ✅ {passed}/{total} 성공 | ⏱ {timeout} | ⚠️ {error} | ❌ {failed}")
    print("=" * 100 + "\n")

    if passed > 0:
        times = [r["time_s"] for r in results if r["status"].startswith("✅")]
        cells = [r["cells"] for r in results if r["cells"] > 0]

        print(f"⏱  실행 시간 (성공한 경우):")
        print(f"   최소: {min(times):.2f}s")
        print(f"   최대: {max(times):.2f}s")
        print(f"   평균: {sum(times)/len(times):.2f}s")

        if cells:
            print(f"\n📦 메시 크기 (성공한 경우):")
            print(f"   최소: {min(cells):,} cells")
            print(f"   최대: {max(cells):,} cells")

    # 결과 저장
    report_file = repo_root / "MESH_FORMAT_VALIDATION_REPORT.json"
    with open(report_file, "w") as f:
        json.dump({
            "total": total,
            "passed": passed,
            "failed": failed,
            "timeout": timeout,
            "error": error,
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"💾 상세 리포트: {report_file}\n")

    return 0 if failed == 0 and error == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
