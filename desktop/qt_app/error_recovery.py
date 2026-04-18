"""파이프라인 실패 시 사용자에게 원인 + 복구 가이드를 제시하는 다이얼로그.

CFD 엔지니어 대상:
- OpenFOAM 미설치 → 설치 가이드
- Hausdorff 실패 → 입력 파일 품질 분석 제안
- TetWild epsilon 실패 → 품질 레벨 강등 제안
- 모든 Tier 실패 → GitHub 이슈 제출 링크
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


@dataclass
class RecoveryAction:
    """사용자가 취할 수 있는 복구 액션."""

    label: str
    description: str
    handler_key: str  # 'install_openfoam' | 'lower_quality' | 'repair_surface' | 'issue_url' | 'dismiss'


# 에러 패턴 → 복구 가이드 매핑
RECOVERY_PATTERNS: list[tuple[str, str, list[RecoveryAction]]] = [
    (
        r"(openfoam.*not found|controlDict|FOAM FATAL|Foam::|openfoam_utility_failed)",
        "OpenFOAM이 설치되지 않았거나 PATH에 없습니다.\n\n"
        "AutoTessell은 OpenFOAM의 `gmshToFoam`, `checkMesh` 유틸리티를 사용해 "
        "메시 변환·검증을 수행합니다. OpenFOAM 2406 이상이 필요합니다.",
        [
            RecoveryAction(
                label="설치 가이드 열기",
                description="브라우저에서 OpenFOAM 공식 설치 가이드 페이지 열기",
                handler_key="install_openfoam",
            ),
            RecoveryAction(
                label="Draft 품질로 재시도",
                description="OpenFOAM 의존 Tier를 건너뛰고 TetWild만 사용 (우회)",
                handler_key="lower_quality",
            ),
            RecoveryAction(label="닫기", description="", handler_key="dismiss"),
        ],
    ),
    (
        r"(hausdorff|fidelity.*fail|hausdorff.*ratio.*exceed)",
        "메시가 원본 지오메트리와 너무 많이 벗어났습니다 (Hausdorff 거리 초과).\n\n"
        "입력 STL이 손상됐거나 세부 특징이 많아 현재 품질 레벨로는 충분히 "
        "해상할 수 없을 가능성이 큽니다.",
        [
            RecoveryAction(
                label="표면 리메쉬 활성화",
                description="pyACVD/geogram 리메쉬로 입력 표면 품질 개선 후 재시도",
                handler_key="repair_surface",
            ),
            RecoveryAction(
                label="Fine 품질로 재시도",
                description="더 많은 셀을 허용 (시간 오래 걸림)",
                handler_key="raise_quality",
            ),
            RecoveryAction(label="닫기", description="", handler_key="dismiss"),
        ],
    ),
    (
        r"(watertight|not manifold|non.manifold|self.intersect)",
        "입력 메시에 위상적 문제가 있습니다 (watertight 아님, 자기교차, 또는 non-manifold).\n\n"
        "AutoTessell은 L1 pymeshfix로 자동 수리를 시도했지만 실패했습니다.",
        [
            RecoveryAction(
                label="AI 수리 활성화 (MeshAnything)",
                description="L3 AI fallback 체크박스 켜고 재시도 (GPU 필요, 분 단위 소요)",
                handler_key="enable_ai_fallback",
            ),
            RecoveryAction(label="닫기", description="", handler_key="dismiss"),
        ],
    ),
    (
        r"(all tiers.*fail|no tier succeeded|Failed after.*iteration)",
        "모든 Tier가 실패했습니다. 이것은 예외적인 상황입니다.\n\n"
        "입력 파일 또는 환경 특이 이슈일 수 있습니다. "
        "GitHub 이슈로 제보해 주시면 빠르게 조사하겠습니다.",
        [
            RecoveryAction(
                label="GitHub 이슈 제출",
                description="재현 정보와 함께 이슈 페이지 열기",
                handler_key="issue_url",
            ),
            RecoveryAction(label="닫기", description="", handler_key="dismiss"),
        ],
    ),
]


def classify_error(error_message: str) -> tuple[str, list[RecoveryAction]] | None:
    """에러 메시지를 패턴 매칭해 안내 문구 + 액션 목록 반환. 매치 없으면 None."""
    if not error_message:
        return None
    for pattern, guide, actions in RECOVERY_PATTERNS:
        if re.search(pattern, error_message, re.IGNORECASE):
            return (guide, actions)
    return None


class ErrorRecoveryDialog(QDialog):
    """파이프라인 실패 시 사용자에게 복구 옵션을 제공하는 모달."""

    def __init__(
        self,
        parent=None,
        title: str = "파이프라인 실패",
        error_message: str = "",
        guide_text: str = "",
        actions: list[RecoveryAction] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.setStyleSheet(
            "QDialog { background: #0f1318; color: #e8ecf2; }"
        )

        self.chosen_action: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # 제목
        title_lbl = QLabel(f"❌ {title}")
        title_lbl.setStyleSheet(
            "color: #ff6b6b; font-size: 14px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(title_lbl)

        # 안내 텍스트
        guide_lbl = QLabel(guide_text)
        guide_lbl.setWordWrap(True)
        guide_lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 12px; background: transparent; padding: 4px 0;"
        )
        layout.addWidget(guide_lbl)

        # 원본 에러 로그 (접힘)
        if error_message:
            log_view = QTextBrowser()
            log_view.setPlainText(error_message[-2000:])  # 마지막 2000자
            log_view.setFont(QFont("JetBrains Mono", 9))
            log_view.setStyleSheet(
                "QTextBrowser { background: #05070a; color: #818a99; "
                "border: 1px solid #262c36; border-radius: 4px; padding: 6px; }"
            )
            log_view.setMaximumHeight(140)
            layout.addWidget(log_view)

        # 액션 버튼 행
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        for act in actions or []:
            btn = QPushButton(act.label)
            btn.setToolTip(act.description)
            btn.setStyleSheet(
                "QPushButton { background: #21262d; color: #e8ecf2; "
                "border: 1px solid #30363d; border-radius: 4px; "
                "padding: 6px 14px; font-size: 12px; } "
                "QPushButton:hover { background: #2d333b; border-color: #4ea3ff; } "
                "QPushButton:pressed { background: #1f6feb; }"
            )
            btn.clicked.connect(
                lambda _checked=False, _k=act.handler_key: self._on_action(_k)
            )
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

    def _on_action(self, key: str) -> None:
        self.chosen_action = key
        self.accept()
