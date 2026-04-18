"""드롭 즉시 지오메트리 분석 — trimesh 기반 빠른 통계.

출력 목표:
- triangles, bbox_diag, watertight/manifold
- 추천 품질 레벨 (삼각형 수 기반)
- 예상 볼륨 셀 수 (메쉬 크기·품질 레벨 기반 추정)
- 과거 유사 실행 이력이 있으면 ETA 예측
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GeometryHint:
    """드롭 직후 보여줄 지오메트리 요약."""

    n_triangles: int = 0
    n_vertices: int = 0
    bbox_diag: float = 0.0
    is_watertight: bool = False
    is_winding_consistent: bool = False
    file_size_mb: float = 0.0
    # 추천값
    recommended_quality: str = "draft"  # draft/standard/fine
    recommended_reason: str = ""
    # ETA 예측
    eta_seconds_draft: float | None = None
    eta_seconds_standard: float | None = None
    eta_seconds_fine: float | None = None
    eta_confidence: str = ""  # "low" | "medium" | "high" | ""
    # 에러 메시지
    error: str | None = None


def analyze(path: Path | str) -> GeometryHint:
    """파일 경로에서 빠른 지오메트리 요약 산출. trimesh 필수."""
    path = Path(path)
    hint = GeometryHint()
    if not path.exists():
        hint.error = f"파일 없음: {path}"
        return hint

    try:
        hint.file_size_mb = path.stat().st_size / (1024 * 1024)
    except Exception:
        pass

    # trimesh 로드 — 메쉬 기반 형식만 처리 (STEP/IGES는 별도 경로 필요)
    ext = path.suffix.lower()
    if ext not in {".stl", ".obj", ".ply", ".off", ".3mf"}:
        # CAD 파일은 별도 tesselation 필요 — 간단한 메타만
        hint.error = f"{ext} 파일은 tessellation 후 분석 필요"
        return hint

    try:
        import trimesh

        # process=True → 중복 정점 병합 (watertight 판정에 필수)
        mesh = trimesh.load(str(path), force="mesh", process=True)
        if not hasattr(mesh, "faces"):
            hint.error = "유효한 메쉬 아님"
            return hint
        hint.n_triangles = int(len(mesh.faces))
        hint.n_vertices = int(len(mesh.vertices))
        try:
            bbox = mesh.bounds
            import numpy as _np

            diag = float(_np.linalg.norm(bbox[1] - bbox[0]))
            hint.bbox_diag = diag
        except Exception:
            pass
        try:
            hint.is_watertight = bool(mesh.is_watertight)
        except Exception:
            pass
        try:
            hint.is_winding_consistent = bool(mesh.is_winding_consistent)
        except Exception:
            pass
    except Exception as e:
        hint.error = f"trimesh 로드 실패: {e}"
        return hint

    _recommend_quality(hint)
    _predict_eta(hint)
    return hint


def _recommend_quality(hint: GeometryHint) -> None:
    """삼각형 수 + 위상 기반 추천 품질 레벨."""
    t = hint.n_triangles
    if t == 0:
        return
    if t < 5_000:
        hint.recommended_quality = "draft"
        hint.recommended_reason = f"{t:,} 삼각형 — 빠른 TetWild로 충분"
    elif t < 100_000:
        hint.recommended_quality = "standard"
        hint.recommended_reason = f"{t:,} 삼각형 — Netgen/cfMesh 적합"
    else:
        hint.recommended_quality = "fine"
        hint.recommended_reason = (
            f"{t:,} 삼각형 — 세부 특징 많음, snappyHexMesh + BL 권장"
        )
    # 수리 필요 시 힌트 추가
    if not hint.is_watertight:
        hint.recommended_reason += " (Watertight 아님 — L1 수리 활성화 추천)"


def _predict_eta(hint: GeometryHint) -> None:
    """history.jsonl에서 유사 메쉬 실행 시간 평균 → ETA."""
    from desktop.qt_app import history as _h

    entries = _h.load_all()
    if not entries:
        return

    # 삼각형 수가 ±50% 이내인 과거 성공 실행만 필터
    t = hint.n_triangles
    if t == 0:
        return

    def _filter_similar(quality: str) -> list[float]:
        times: list[float] = []
        for e in entries:
            if not e.success or e.quality_level != quality:
                continue
            # 이전 실행의 입력 파일에서 삼각형 수는 몰라도
            # 셀 수로 스케일 추정 (볼륨 셀 ≈ 10 * 삼각형)
            approx_t = max(1, e.n_cells // 10)
            if 0.5 <= approx_t / max(t, 1) <= 2.0:
                times.append(e.elapsed_seconds)
        return times

    draft_times = _filter_similar("draft")
    std_times = _filter_similar("standard")
    fine_times = _filter_similar("fine")

    if draft_times:
        hint.eta_seconds_draft = statistics.median(draft_times)
    if std_times:
        hint.eta_seconds_standard = statistics.median(std_times)
    if fine_times:
        hint.eta_seconds_fine = statistics.median(fine_times)

    # 신뢰도 판단
    n_similar = len(draft_times) + len(std_times) + len(fine_times)
    if n_similar >= 5:
        hint.eta_confidence = "high"
    elif n_similar >= 2:
        hint.eta_confidence = "medium"
    elif n_similar >= 1:
        hint.eta_confidence = "low"


def format_hint(hint: GeometryHint) -> str:
    """사용자 표시용 멀티라인 문자열."""
    if hint.error:
        return f"⚠ {hint.error}"
    lines = [
        f"삼각형: {hint.n_triangles:,}    정점: {hint.n_vertices:,}",
        f"BBox 대각: {hint.bbox_diag:.3f}    크기: {hint.file_size_mb:.2f} MB",
    ]
    badges = []
    badges.append("✓ Watertight" if hint.is_watertight else "✗ Watertight")
    badges.append("✓ Winding" if hint.is_winding_consistent else "✗ Winding")
    lines.append("  ".join(badges))
    if hint.recommended_quality:
        lines.append(
            f"추천: {hint.recommended_quality.upper()} — {hint.recommended_reason}"
        )
    eta_parts = []
    if hint.eta_seconds_draft is not None:
        eta_parts.append(f"Draft~{_fmt_time(hint.eta_seconds_draft)}")
    if hint.eta_seconds_standard is not None:
        eta_parts.append(f"Std~{_fmt_time(hint.eta_seconds_standard)}")
    if hint.eta_seconds_fine is not None:
        eta_parts.append(f"Fine~{_fmt_time(hint.eta_seconds_fine)}")
    if eta_parts:
        conf = f" ({hint.eta_confidence})" if hint.eta_confidence else ""
        lines.append(f"ETA{conf}: {'  '.join(eta_parts)}")
    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"
