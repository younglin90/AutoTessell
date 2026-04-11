#!/usr/bin/env python3
"""Draft/Standard/Fine 엔진 프로필 검증."""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def test_quality_level(test_file: Path, quality: str) -> dict[str, Any]:
    """단일 Quality Level 테스트."""
    result = {
        "file": test_file.name,
        "quality": quality,
        "status": "unknown",
        "time_s": 0.0,
        "cells": 0,
        "mesh_ok": False,
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
                timeout=600,
                cwd=str(Path(__file__).parent.parent),
            )

            elapsed = time.monotonic() - t_start
            result["time_s"] = elapsed

            if proc.returncode == 0:
                result["status"] = "✅"

                # 품질 리포트 읽기
                quality_file = case_dir / "quality_report.json"
                if quality_file.exists():
                    with open(quality_file) as f:
                        qr = json.load(f)
                        stats = qr.get("mesh_statistics", {})
                        result["cells"] = stats.get("cells", 0)
                        result["mesh_ok"] = qr.get("verdict") == "PASS"

                        # 메시 품질 지표
                        result["details"] = {
                            "max_non_ortho": stats.get("max_non_orthogonality"),
                            "max_skewness": stats.get("max_skewness"),
                            "max_aspect_ratio": stats.get("max_aspect_ratio"),
                        }
            else:
                result["status"] = "❌"
                result["error"] = proc.stderr[:200] if proc.stderr else "Unknown error"

        except subprocess.TimeoutExpired:
            result["status"] = "⏱"
            result["error"] = f"Timeout (>{quality=='fine' and 600 or 120}s)"
        except Exception as e:
            result["status"] = "⚠️"
            result["error"] = str(e)[:100]

    return result


def main():
    """모든 Quality Level 테스트."""
    repo_root = Path(__file__).parent.parent
    bench_dir = repo_root / "tests" / "benchmarks"

    print("\n" + "=" * 120)
    print("🔬 엔진 프로필 검증 (Draft/Standard/Fine)")
    print("=" * 120 + "\n")

    # 테스트 케이스 선택 (다양한 크기)
    all_files = sorted(bench_dir.glob("*.stl"))
    test_files = [
        f for f in all_files
        if any(x in f.name for x in [
            "sphere_watertight",        # 기본
            "large_mesh",               # 대용량
            "mixed_features",           # 혼합 피처
            "nonmanifold",              # 문제 있는 메시
        ])
    ]

    if not test_files:
        test_files = all_files[:3]  # 최소 3개

    print(f"📋 테스트 대상: {len(test_files)}개 케이스\n")
    for f in test_files:
        print(f"  • {f.name}")
    print()

    quality_levels = ["draft", "standard", "fine"]
    all_results = {}

    for quality in quality_levels:
        print(f"\n{'='*120}")
        print(f"🎯 {quality.upper()} Quality Level")
        print(f"{'='*120}\n")

        quality_results = []

        for test_file in test_files:
            print(f"  {test_file.name:45}", end=" ", flush=True)

            result = test_quality_level(test_file, quality)
            quality_results.append(result)

            status = result["status"]
            time_str = f"{result['time_s']:.1f}s"
            cells_str = f"{result['cells']:,}" if result["cells"] > 0 else "—"
            ok_str = "✓" if result["mesh_ok"] else "✗"

            print(f"{status} {time_str:>7} | {cells_str:>8} cells | Mesh {ok_str}")

            if result["error"]:
                print(f"{'':47} ⚠️  {result['error']}")

        all_results[quality] = quality_results

    # 요약
    print(f"\n{'='*120}")
    print("📊 프로필별 요약")
    print(f"{'='*120}\n")

    for quality in quality_levels:
        results = all_results[quality]
        passed = sum(1 for r in results if r["status"] == "✅")
        time_values = [r["time_s"] for r in results if r["time_s"] > 0]

        avg_time = sum(time_values) / len(time_values) if time_values else 0
        print(f"{quality.upper():10} | 성공: {passed}/{len(results)} | 평균시간: {avg_time:.1f}s")

    # 상세 결과 저장
    report_file = repo_root / "ENGINE_PROFILE_VALIDATION_REPORT.json"
    with open(report_file, "w") as f:
        json.dump(
            {
                "test_files": [f.name for f in test_files],
                "quality_levels": quality_levels,
                "results": all_results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\n💾 상세 리포트: {report_file}\n")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
