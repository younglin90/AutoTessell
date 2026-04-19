"""Wildmesh-only 모드 preflight — 실행 전 위험 패턴 감지.

Strategist가 non-wildmesh 모드에서 자동으로 우회하던 위험 케이스를
wildmesh_only에서는 wildmesh가 직접 처리해야 함. 실패 가능성이 높으면
사용자에게 미리 경고해서 override 여부 결정권을 준다.

감지 대상:
- Non-watertight (critical_issue 와 유사) → wildmesh 내부 수리도 실패 가능
- Thin-wall (aspect ratio > 100) → 찌그러진 tet 생성
- Planar 입력 (z-range / bbox_diag < 2%) → 불필요한 3D 체우기
- 너무 큰 메쉬 (>500k faces) → timeout 위험
- 극소 삼각형 (min edge < 1e-6) → fTetWild kernel precision 실패
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class WarningLevel(str, Enum):
    INFO = "info"       # 참고 정보
    WARN = "warn"       # 실패 가능성 중간
    DANGER = "danger"   # 실패 가능성 높음


@dataclass
class PreflightWarning:
    level: WarningLevel
    title: str
    description: str
    suggestion: str = ""


@dataclass
class PreflightReport:
    """입력 파일 preflight 결과."""
    warnings: list[PreflightWarning] = field(default_factory=list)
    is_safe: bool = True            # 하나라도 DANGER 있으면 False

    def add(self, w: PreflightWarning) -> None:
        self.warnings.append(w)
        if w.level == WarningLevel.DANGER:
            self.is_safe = False


def analyze(path: Path | str) -> PreflightReport:
    """입력 파일을 분석하고 wildmesh_only 모드에서의 위험 경고 모음 반환."""
    path = Path(path)
    report = PreflightReport()

    if not path.exists():
        report.add(PreflightWarning(
            level=WarningLevel.DANGER,
            title="파일 없음",
            description=f"{path}",
        ))
        return report

    # 지원 포맷인지 빠른 검사
    ext = path.suffix.lower()
    if ext not in {".stl", ".obj", ".ply", ".off", ".3mf"}:
        # CAD 파일 — 별도 tessellation 경로가 처리
        report.add(PreflightWarning(
            level=WarningLevel.INFO,
            title="CAD 파일",
            description=f"{ext} — cadquery/gmsh 테셀레이션 후 wildmesh 처리",
        ))
        return report

    try:
        import numpy as _np
        import trimesh
        mesh = trimesh.load(str(path), force="mesh", process=True)
        n_faces = int(len(mesh.faces)) if hasattr(mesh, "faces") else 0
        if n_faces == 0:
            report.add(PreflightWarning(
                level=WarningLevel.DANGER,
                title="유효한 메쉬 아님",
                description=f"{path.name} — trimesh가 faces 를 찾지 못함",
            ))
            return report

        # 1) Watertight 검사
        try:
            is_watertight = bool(mesh.is_watertight)
        except Exception:
            is_watertight = False
        if not is_watertight:
            report.add(PreflightWarning(
                level=WarningLevel.WARN,
                title="Non-watertight 표면",
                description="WildMesh는 watertight 요구. fill_holes + pymeshfix 자동 시도 예정.",
                suggestion="실패시 표면 리메쉬(L2) 또는 AI 수리(L3) 활성화",
            ))

        # 2) Bounding box 비율 — thin-wall / planar 감지
        try:
            bounds = mesh.bounds
            extents = _np.abs(bounds[1] - bounds[0])
            diag = float(_np.linalg.norm(extents))
            min_ext = float(extents.min())
            max_ext = float(extents.max())
            aspect = max_ext / max(min_ext, 1e-12)
            z_range_ratio = float(extents[2] / max(diag, 1e-12))

            if aspect > 100.0:
                report.add(PreflightWarning(
                    level=WarningLevel.DANGER,
                    title=f"극도 thin-wall 형상 (aspect={aspect:.1f})",
                    description="얇은 형상은 wildmesh가 찌그러진 tet 생성. 다른 모드는 tier0_2d_meshpy로 우회.",
                    suggestion="wildmesh_only 모드 해제 + 2D 모드 사용 권장",
                ))
            elif aspect > 30.0:
                report.add(PreflightWarning(
                    level=WarningLevel.WARN,
                    title=f"높은 aspect ratio ({aspect:.1f})",
                    description="품질 저하 가능. epsilon 작게 + edge_length_r 작게 권장",
                ))

            if z_range_ratio < 0.02:
                report.add(PreflightWarning(
                    level=WarningLevel.DANGER,
                    title="Planar 입력 (거의 2D)",
                    description=f"z-range={extents[2]:.4f}는 bbox의 {z_range_ratio * 100:.1f}%. "
                                "wildmesh는 3D tet로 강제 체우기 → 불필요한 셀 증가.",
                    suggestion="wildmesh_only 해제 + 2D 모드 사용",
                ))
        except Exception:
            pass

        # 3) 메쉬 크기 — timeout 위험
        if n_faces > 500_000:
            report.add(PreflightWarning(
                level=WarningLevel.WARN,
                title=f"매우 큰 메쉬 ({n_faces:,} faces)",
                description="WildMesh 실행 시간이 길어질 수 있음 (수 분~수십 분). "
                            "동적 timeout 적용되지만 상한 30분.",
                suggestion="품질 draft 로 우선 점검",
            ))
        elif n_faces < 50:
            report.add(PreflightWarning(
                level=WarningLevel.WARN,
                title=f"매우 작은 메쉬 ({n_faces} faces)",
                description="wildmesh가 유효한 tet을 생성하지 못할 수 있음",
            ))

        # 4) 극소 엣지 감지
        try:
            min_edge = float(mesh.edges_unique_length.min())
            if min_edge < 1e-6:
                report.add(PreflightWarning(
                    level=WarningLevel.WARN,
                    title=f"극소 엣지 감지 (min={min_edge:.2e})",
                    description="fTetWild kernel precision 한계 접근. 스케일 보정 권장.",
                ))
        except Exception:
            pass

    except Exception as e:  # noqa: BLE001
        report.add(PreflightWarning(
            level=WarningLevel.DANGER,
            title="분석 실패",
            description=f"{type(e).__name__}: {e}",
        ))

    return report


def format_summary(report: PreflightReport) -> str:
    """다이얼로그 표시용 단일 문자열."""
    if not report.warnings:
        return "✓ preflight 통과 — 감지된 위험 없음"
    lines = []
    for w in report.warnings:
        icon = {"info": "ℹ", "warn": "⚠", "danger": "✗"}.get(w.level.value, "•")
        lines.append(f"{icon} [{w.level.value.upper()}] {w.title}")
        lines.append(f"    {w.description}")
        if w.suggestion:
            lines.append(f"    해결: {w.suggestion}")
    return "\n".join(lines)
