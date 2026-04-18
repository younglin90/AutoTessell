"""메시 생성 결과 1-페이지 PDF 리포트 생성.

matplotlib 기반 (이미 의존성). 구성:
- 메타데이터 (입력 파일, Tier, 품질, 시간)
- 뷰포트 스크린샷 (임의 PNG)
- 3대 품질 메트릭 히스토그램 (Aspect/Skew/Non-ortho)
- 합격 기준 표 + checkMesh 요약

외부 전달용 (발주처/팀장 보고서).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    _MPL_AVAILABLE = True
except Exception:
    _MPL_AVAILABLE = False


@dataclass
class ReportData:
    """리포트 생성을 위한 입력 데이터."""

    input_file: str = ""
    output_dir: str = ""
    tier_used: str = ""
    quality_level: str = ""
    total_time_seconds: float = 0.0
    n_cells: int = 0
    n_points: int = 0
    # 메트릭
    max_aspect_ratio: float | None = None
    max_skewness: float | None = None
    max_non_orthogonality: float | None = None
    negative_volumes: int | None = None
    min_cell_volume: float | None = None
    # 히스토그램 배열
    hist_aspect: list[float] = field(default_factory=list)
    hist_skew: list[float] = field(default_factory=list)
    hist_non_ortho: list[float] = field(default_factory=list)
    # 스크린샷
    screenshot_path: str | None = None
    # 합격 기준
    passes: dict = field(default_factory=dict)  # {"aspect": True, "skew": False, ...}


def write_pdf(data: ReportData, out_path: Path) -> bool:
    """PDF 파일 생성. 성공시 True."""
    if not _MPL_AVAILABLE:
        return False

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with PdfPages(str(out_path)) as pdf:
            _write_page(pdf, data)
        return True
    except Exception:
        return False


def _write_page(pdf, data: ReportData) -> None:
    import numpy as _np

    fig = plt.figure(figsize=(8.5, 11), facecolor="white")

    # ── 헤더 ────────────────────────────────────────────────────────
    ax_header = fig.add_axes([0.05, 0.92, 0.90, 0.06])
    ax_header.axis("off")
    ax_header.text(
        0.0, 0.65, "AutoTessell 메시 리포트",
        fontsize=16, fontweight="bold", color="#0d1117",
    )
    ax_header.text(
        0.0, 0.15, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        fontsize=9, color="#5a6270",
    )
    # 판정 배지
    verdict = _compute_verdict(data)
    color = {"PASS": "#22c55e", "WARN": "#f59e0b", "FAIL": "#ef4444"}[verdict]
    ax_header.text(
        1.0, 0.4, verdict, ha="right", va="center",
        fontsize=20, fontweight="bold", color=color,
    )

    # ── 메타데이터 섹션 ─────────────────────────────────────────────
    ax_meta = fig.add_axes([0.05, 0.78, 0.90, 0.13])
    ax_meta.axis("off")
    rows = [
        ("입력 파일", Path(data.input_file).name or "—"),
        ("출력 경로", data.output_dir or "—"),
        ("사용 Tier", data.tier_used or "—"),
        ("품질 레벨", data.quality_level or "—"),
        ("총 소요 시간", f"{data.total_time_seconds:.1f}초"),
        ("셀 수", f"{data.n_cells:,}" if data.n_cells else "—"),
        ("점 수", f"{data.n_points:,}" if data.n_points else "—"),
    ]
    for i, (k, v) in enumerate(rows):
        y = 0.95 - i * 0.13
        ax_meta.text(0.0, y, k, fontsize=10, color="#5a6270", fontweight="bold")
        ax_meta.text(0.22, y, v, fontsize=10, color="#0d1117",
                     family="monospace")

    # ── 스크린샷 (선택적) ──────────────────────────────────────────
    if data.screenshot_path and Path(data.screenshot_path).exists():
        try:
            from matplotlib.image import imread

            img = imread(data.screenshot_path)
            ax_img = fig.add_axes([0.05, 0.48, 0.90, 0.28])
            ax_img.imshow(img)
            ax_img.axis("off")
            ax_img.set_title("뷰포트 캡처", fontsize=10, color="#5a6270", loc="left")
        except Exception:
            pass

    # ── 품질 히스토그램 3개 ────────────────────────────────────────
    hist_y = 0.22
    hist_height = 0.22
    for i, (label, data_arr, color, threshold) in enumerate([
        ("Aspect Ratio", data.hist_aspect, "#4ea3ff", 100.0),
        ("Skewness", data.hist_skew, "#f5b454", 4.0),
        ("Non-ortho°", data.hist_non_ortho, "#ff7b54", 65.0),
    ]):
        ax = fig.add_axes([0.05 + i * 0.31, hist_y, 0.28, hist_height])
        if data_arr and len(data_arr) > 1:
            arr = _np.asarray(data_arr, dtype=float)
            arr = arr[_np.isfinite(arr)]
            if len(arr) > 0:
                p99 = _np.percentile(arr, 99)
                _d = _np.clip(arr, 0, p99)
                ax.hist(_d, bins=25, color=color, alpha=0.85, edgecolor="white", linewidth=0.3)
                ax.axvline(threshold, color="#ef4444", linestyle="--", linewidth=1, alpha=0.7)
        ax.set_title(label, fontsize=9, color="#0d1117", fontweight="bold")
        ax.tick_params(labelsize=7, colors="#5a6270")

    # ── 합격 기준 표 ────────────────────────────────────────────────
    ax_pass = fig.add_axes([0.05, 0.05, 0.90, 0.12])
    ax_pass.axis("off")
    ax_pass.text(0.0, 0.95, "합격 기준 (OpenFOAM checkMesh)",
                 fontsize=10, fontweight="bold", color="#0d1117")
    criteria = [
        ("Aspect Ratio < 100", data.max_aspect_ratio, 100.0),
        ("Skewness < 4.0", data.max_skewness, 4.0),
        ("Non-ortho < 65°", data.max_non_orthogonality, 65.0),
        ("Negative volumes = 0", data.negative_volumes, 0),
    ]
    for i, (label, val, thr) in enumerate(criteria):
        y = 0.7 - i * 0.17
        if val is None:
            mark = "—"
            mcolor = "#5a6270"
        else:
            passed = (val == 0) if (thr == 0) else (val < thr)
            mark = "✓" if passed else "✗"
            mcolor = "#22c55e" if passed else "#ef4444"
        ax_pass.text(0.0, y, mark, fontsize=12, color=mcolor, fontweight="bold")
        ax_pass.text(0.04, y, label, fontsize=9, color="#0d1117")
        if val is not None:
            ax_pass.text(0.7, y, f"실측: {val}", fontsize=9, color="#5a6270",
                         family="monospace")

    # ── 푸터 ────────────────────────────────────────────────────────
    ax_footer = fig.add_axes([0.05, 0.01, 0.90, 0.03])
    ax_footer.axis("off")
    ax_footer.text(
        0.0, 0.5, "Generated by AutoTessell",
        fontsize=7, color="#a0a0a0", style="italic",
    )
    ax_footer.text(
        1.0, 0.5, "github.com/younglin90/AutoTessell",
        fontsize=7, color="#a0a0a0", ha="right", style="italic",
    )

    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


def _compute_verdict(data: ReportData) -> str:
    """PASS/WARN/FAIL 판정."""
    checks = [
        (data.max_aspect_ratio, 100.0, False),
        (data.max_skewness, 4.0, False),
        (data.max_non_orthogonality, 65.0, False),
        (data.negative_volumes, 0, True),  # equality check (must be 0)
    ]
    any_fail = False
    any_warn = False
    for val, thr, is_equality in checks:
        if val is None:
            continue
        if is_equality:
            if val != thr:
                any_fail = True
        else:
            if val >= thr:
                any_fail = True
            elif val >= thr * 0.8:
                any_warn = True
    if any_fail:
        return "FAIL"
    if any_warn:
        return "WARN"
    return "PASS"
