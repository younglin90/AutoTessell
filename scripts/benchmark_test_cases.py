#!/usr/bin/env python3
"""성능 벤치마킹 스크립트: 17개 테스트 케이스 실행 및 분석."""

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np


def get_test_cases() -> list[Path]:
    """테스트 케이스 경로 반환 (기본 9개 + 고급 8개)."""
    bench_dir = Path(__file__).parent.parent / "tests" / "benchmarks"
    if not bench_dir.exists():
        print(f"⚠ 벤치마크 디렉터리 없음: {bench_dir}")
        return []

    cases = sorted(bench_dir.glob("*.stl"))
    return cases


def extract_mesh_info(case_dir: Path) -> dict[str, Any]:
    """생성된 메시에서 정보 추출."""
    stats = {
        "cells": 0,
        "faces": 0,
        "points": 0,
        "mesh_ok": False,
        "quality_report": None,
    }

    # quality_report.json 읽기 (Evaluator 출력)
    quality_file = case_dir / "quality_report.json"
    if quality_file.exists():
        try:
            with open(quality_file) as f:
                report = json.load(f)
                # QualityReport schema: { "evaluation_summary": { "verdict": "PASS", ... } }
                summary = report.get("evaluation_summary", {})
                stats["mesh_ok"] = summary.get("verdict") == "PASS"
                stats["quality_report"] = report
        except Exception as e:
            print(f"  ⚠ quality_report.json 파싱 실패: {e}")

    # polyMesh 메타데이터 읽기
    poly_dir = case_dir / "constant" / "polyMesh"
    if poly_dir.exists():
        try:
            # points 파일에서 점 개수 추출
            points_file = poly_dir / "points"
            if points_file.exists():
                with open(points_file) as f:
                    content = f.read()
                    # OpenFOAM 포맷: ( num_points )
                    if "(" in content and ")" in content:
                        start = content.find("(")
                        end = content.find(")")
                        if start != -1 and end != -1:
                            try:
                                stats["points"] = int(content[start+1:end].strip())
                            except ValueError:
                                pass
        except Exception as e:
            print(f"  ⚠ polyMesh 메타 추출 실패: {e}")

    return stats


def run_benchmark(test_case: Path, quality: str = "draft", timeout: int = 600) -> dict[str, Any]:
    """단일 테스트 케이스 실행 및 벤치마크."""
    result = {
        "test_case": test_case.name,
        "quality": quality,
        "status": "unknown",
        "elapsed_seconds": 0.0,
        "cells": 0,
        "faces": 0,
        "points": 0,
        "mesh_ok": False,
        "error": None,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        case_dir = Path(tmpdir) / "case"

        t_start = time.monotonic()
        try:
            # auto-tessell run 실행 (python -m로 로컬 모듈 사용)
            cmd = [
                "python3", "-m", "cli.main", "run",
                str(test_case),
                "-o", str(case_dir),
                "--quality", quality,
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(Path(__file__).parent.parent),  # repo root에서 실행
            )

            elapsed = time.monotonic() - t_start
            result["elapsed_seconds"] = elapsed

            if proc.returncode == 0:
                result["status"] = "success"
                stats = extract_mesh_info(case_dir)
                result.update(stats)
            else:
                result["status"] = "failed"
                result["error"] = proc.stderr[:200] if proc.stderr else "Unknown error"

        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
            result["error"] = f"Timeout after {timeout}s"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

    return result


def main():
    """모든 테스트 케이스 벤치마킹."""
    print("\n" + "=" * 70)
    print("AutoTessell 성능 벤치마킹")
    print("=" * 70 + "\n")

    test_cases = get_test_cases()
    if not test_cases:
        print("❌ 테스트 케이스를 찾을 수 없습니다.")
        print("다음 명령어로 먼저 생성하세요:")
        print("  python3 scripts/generate_test_cases.py")
        print("  python3 scripts/generate_advanced_test_cases.py")
        return

    print(f"🎯 {len(test_cases)}개 테스트 케이스 발견\n")

    results = []

    for i, test_case in enumerate(test_cases, 1):
        print(f"[{i}/{len(test_cases)}] {test_case.name}...", end=" ", flush=True)
        result = run_benchmark(test_case, quality="draft")
        results.append(result)

        status_icon = {
            "success": "✅",
            "failed": "❌",
            "timeout": "⏱",
            "error": "⚠",
            "unknown": "❓",
        }.get(result["status"], "?")

        time_str = f"{result['elapsed_seconds']:.2f}s"
        cells_str = f"{result['cells']:,}" if result["cells"] > 0 else "—"
        mesh_ok = "OK" if result["mesh_ok"] else "FAIL"

        print(f"{status_icon} {time_str:>8} | {cells_str:>8} cells | {mesh_ok}")

        if result["error"]:
            print(f"      Error: {result['error']}")

    # 요약 통계
    print("\n" + "=" * 70)
    print("📊 벤치마킹 결과 요약")
    print("=" * 70 + "\n")

    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "failed"]
    timeout = [r for r in results if r["status"] == "timeout"]
    error = [r for r in results if r["status"] == "error"]

    print(f"✅ 성공: {len(successful)}/{len(results)}")
    print(f"❌ 실패: {len(failed)}/{len(results)}")
    print(f"⏱ 타임아웃: {len(timeout)}/{len(results)}")
    print(f"⚠ 오류: {len(error)}/{len(results)}")

    if successful:
        times = [r["elapsed_seconds"] for r in successful]
        cells = [r["cells"] for r in successful if r["cells"] > 0]

        print(f"\n⏱ 실행 시간 (성공한 경우):")
        print(f"  최소: {min(times):.2f}s")
        print(f"  최대: {max(times):.2f}s")
        print(f"  평균: {np.mean(times):.2f}s")
        print(f"  중앙값: {np.median(times):.2f}s")

        if cells:
            print(f"\n📦 메시 크기 (성공한 경우):")
            print(f"  최소: {min(cells):,} cells")
            print(f"  최대: {max(cells):,} cells")
            print(f"  평균: {np.mean(cells):,.0f} cells")

        mesh_ok_count = sum(1 for r in successful if r["mesh_ok"])
        print(f"\n✓ 메시 품질:")
        print(f"  OK: {mesh_ok_count}/{len(successful)}")
        print(f"  FAIL: {len(successful) - mesh_ok_count}/{len(successful)}")

    # 상세 결과 저장
    report_file = Path(__file__).parent.parent / "PERFORMANCE_REPORT.json"
    with open(report_file, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_cases": len(results),
            "summary": {
                "successful": len(successful),
                "failed": len(failed),
                "timeout": len(timeout),
                "error": len(error),
            },
            "results": results,
        }, f, indent=2)

    print(f"\n💾 상세 결과: {report_file}")

    # Markdown 리포트 생성
    generate_markdown_report(results, report_file.parent / "PERFORMANCE_REPORT.md")


def generate_markdown_report(results: list[dict[str, Any]], output_file: Path) -> None:
    """Markdown 형식의 성능 리포트 생성."""
    lines = [
        "# AutoTessell 성능 벤치마킹 리포트\n",
        f"생성 시간: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"테스트 케이스: {len(results)}개\n",
        "\n---\n",
        "## 📊 요약\n",
        "| 상태 | 개수 |\n",
        "|------|------|\n",
    ]

    successful = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    timeout = sum(1 for r in results if r["status"] == "timeout")
    error = sum(1 for r in results if r["status"] == "error")

    lines.append(f"| ✅ 성공 | {successful} |\n")
    lines.append(f"| ❌ 실패 | {failed} |\n")
    lines.append(f"| ⏱ 타임아웃 | {timeout} |\n")
    lines.append(f"| ⚠ 오류 | {error} |\n")

    # 성공한 경우의 통계
    successful_results = [r for r in results if r["status"] == "success"]
    if successful_results:
        times = [r["elapsed_seconds"] for r in successful_results]
        cells = [r["cells"] for r in successful_results if r["cells"] > 0]

        lines.append("\n## ⏱ 실행 시간 통계 (성공한 경우)\n")
        lines.append("| 지표 | 값 |\n")
        lines.append("|------|-----|\n")
        lines.append(f"| 최소 | {min(times):.2f}s |\n")
        lines.append(f"| 최대 | {max(times):.2f}s |\n")
        lines.append(f"| 평균 | {np.mean(times):.2f}s |\n")
        lines.append(f"| 중앙값 | {np.median(times):.2f}s |\n")

        if cells:
            lines.append("\n## 📦 메시 크기 통계\n")
            lines.append("| 지표 | 값 |\n")
            lines.append("|------|-----|\n")
            lines.append(f"| 최소 | {min(cells):,} cells |\n")
            lines.append(f"| 최대 | {max(cells):,} cells |\n")
            lines.append(f"| 평균 | {np.mean(cells):,.0f} cells |\n")

    # 상세 결과
    lines.append("\n## 📋 상세 결과\n")
    lines.append("| 테스트 케이스 | 상태 | 시간 | 셀 수 | Mesh OK |\n")
    lines.append("|---|---|---|---|---|\n")

    for r in results:
        status_icon = {
            "success": "✅",
            "failed": "❌",
            "timeout": "⏱",
            "error": "⚠",
            "unknown": "❓",
        }.get(r["status"], "?")

        time_str = f"{r['elapsed_seconds']:.2f}s" if r["elapsed_seconds"] > 0 else "—"
        cells_str = f"{r['cells']:,}" if r["cells"] > 0 else "—"
        mesh_ok = "✓" if r["mesh_ok"] else "✗"

        lines.append(
            f"| {r['test_case']} | {status_icon} | {time_str} | {cells_str} | {mesh_ok} |\n"
        )

        if r["error"]:
            lines.append(f"| | Error: {r['error'][:50]}... | | | |\n")

    with open(output_file, "w") as f:
        f.writelines(lines)

    print(f"📄 Markdown 리포트: {output_file}")


if __name__ == "__main__":
    main()
