"""y⁺ 기반 첫 번째 BL 층 두께 자동 계산 (beta96).

벽 근처 유동의 무차원 벽 거리 y⁺ 타깃에서 물리적 첫 층 두께를 역산:

    y⁺ = y_first × u_τ / ν

    u_τ = U∞ × √(Cf / 2)           # 마찰 속도
    Cf ≈ 0.0592 × Re_L^(-0.2)       # Schlichting 평판 난류 경계층
    Re_L = U∞ × L / ν

    → y_first = y⁺_target × ν / u_τ

참고:
    - y⁺ ≈ 1 → 저-레이놀즈 난류 모델 (kOmegaSST, Spalart-Allmaras)
    - y⁺ 30~300 → 벽 함수 (kEpsilon standard)
    - L = bbox 대각선 (특성 길이 근사)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from core.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# 유체 물성 (20°C, 표준 대기압)
# ---------------------------------------------------------------------------

FLUID_PROPERTIES: dict[str, dict[str, float]] = {
    "air": {
        "kinematic_viscosity": 1.516e-5,  # ν [m²/s]
        "density": 1.204,                  # ρ [kg/m³]
    },
    "water": {
        "kinematic_viscosity": 1.004e-6,
        "density": 998.2,
    },
    "oil": {
        "kinematic_viscosity": 1e-4,
        "density": 870.0,
    },
}


@dataclass
class YPlusResult:
    """y⁺ 계산 결과."""
    y_first: float          # 첫 번째 층 두께 [m]
    y_plus_achieved: float  # 달성 y⁺ (= y_plus_target, 역산이므로 동일)
    u_tau: float            # 마찰 속도 [m/s]
    re_l: float             # 레이놀즈 수
    cf: float               # 마찰 계수
    fluid: str
    flow_velocity: float
    characteristic_length: float
    message: str = ""


def estimate_first_layer_thickness(
    flow_velocity: float,
    characteristic_length: float,
    *,
    fluid: str = "air",
    kinematic_viscosity: float | None = None,
    y_plus_target: float = 1.0,
) -> YPlusResult:
    """y⁺ 타깃에서 BL 첫 층 두께를 역산.

    Args:
        flow_velocity: 유입 속도 U∞ [m/s].
        characteristic_length: 특성 길이 L [m] (보통 geometry bbox 대각선).
        fluid: "air" | "water" | "oil". kinematic_viscosity 미지정 시 사용.
        kinematic_viscosity: 직접 지정 시 fluid 무시 [m²/s].
        y_plus_target: 목표 y⁺ (기본 1.0 — low-Re 모델용).

    Returns:
        YPlusResult. y_first [m] 가 BLConfig.first_thickness 로 사용.

    Raises:
        ValueError: 입력이 물리적으로 무효한 경우.
    """
    if flow_velocity <= 0:
        raise ValueError(f"flow_velocity > 0 필요: {flow_velocity}")
    if characteristic_length <= 0:
        raise ValueError(f"characteristic_length > 0 필요: {characteristic_length}")

    nu: float
    if kinematic_viscosity is not None:
        nu = float(kinematic_viscosity)
    else:
        props = FLUID_PROPERTIES.get(fluid.lower())
        if props is None:
            raise ValueError(
                f"알 수 없는 fluid: {fluid}. 지원: {list(FLUID_PROPERTIES)}. "
                "또는 --kinematic-viscosity 로 직접 지정."
            )
        nu = float(props["kinematic_viscosity"])

    U = float(flow_velocity)
    L = float(characteristic_length)
    yp = float(y_plus_target)

    Re_L = U * L / nu

    # Schlichting 평판 난류 경계층 마찰 계수
    # Cf = 0.0592 × Re^(-0.2) — 유효 범위 Re = 5×10^5 ~ 10^7
    # 낮은 Re 에선 층류 → Cf 상향 보정 (0.074/Re^0.2 로 보수적 사용)
    if Re_L < 5e5:
        # 층류 지배 영역 — Blasius Cf
        Cf = 1.328 / math.sqrt(Re_L)
    elif Re_L > 1e9:
        # 극초고 Re — ITTC 마찰 공식
        Cf = 0.075 / (math.log10(Re_L) - 2.0) ** 2
    else:
        Cf = 0.0592 * Re_L ** (-0.2)

    u_tau = U * math.sqrt(Cf / 2.0)
    if u_tau < 1e-12:
        raise ValueError("u_tau ≈ 0 — flow_velocity 또는 Re 를 확인하세요.")

    y_first = yp * nu / u_tau

    msg = (
        f"y⁺={yp:.1f} target → y_first={y_first:.3e} m "
        f"(Re={Re_L:.2e}, u_τ={u_tau:.4f} m/s, Cf={Cf:.4e}, fluid={fluid})"
    )
    log.info("yplus_computed", y_first=y_first, Re_L=Re_L, u_tau=u_tau,
             y_plus_target=yp, fluid=fluid)

    return YPlusResult(
        y_first=y_first,
        y_plus_achieved=yp,
        u_tau=u_tau,
        re_l=Re_L,
        cf=Cf,
        fluid=fluid,
        flow_velocity=U,
        characteristic_length=L,
        message=msg,
    )
