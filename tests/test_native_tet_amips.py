"""P2 — AMIPS smoothing tests."""
from __future__ import annotations

import numpy as np


def test_amips_regular_tet_has_zero_energy() -> None:
    from core.generator.native_tet.amips import _tet_amips_energy

    # regular tet (edge length √2 scaled).
    pts = np.array([
        [0, 0, 0], [1, 0, 0],
        [0.5, np.sqrt(3) / 2, 0],
        [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)],
    ], dtype=np.float64)[None]   # (1, 4, 3)
    e = _tet_amips_energy(pts[:, 0], pts[:, 1], pts[:, 2], pts[:, 3])
    assert abs(float(e[0])) < 1e-4


def test_amips_sliver_has_higher_energy_than_regular() -> None:
    from core.generator.native_tet.amips import _tet_amips_energy

    reg = np.array([
        [[0, 0, 0], [1, 0, 0],
         [0.5, np.sqrt(3) / 2, 0],
         [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)]],
    ], dtype=np.float64)
    sliv = np.array([
        [[0, 0, 0], [1, 0, 0], [2, 0.01, 0], [1, 0, 0.01]],
    ], dtype=np.float64)
    e_reg = float(_tet_amips_energy(reg[:, 0], reg[:, 1], reg[:, 2], reg[:, 3])[0])
    e_sl = float(_tet_amips_energy(sliv[:, 0], sliv[:, 1], sliv[:, 2], sliv[:, 3])[0])
    assert e_sl > e_reg + 10.0


def test_amips_relocation_decreases_energy_on_sliver() -> None:
    from core.generator.native_tet.amips import smooth_amips

    # cube 8 verts + 1 interior sliver-prone point.
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        [0.05, 0.5, 0.5],   # 경계 근처 → sliver 유발.
    ], dtype=np.float64)
    tets = np.array([
        [0, 1, 2, 8], [0, 2, 3, 8],
        [4, 5, 6, 8], [4, 6, 7, 8],
        [0, 4, 5, 8], [0, 5, 1, 8],
        [2, 6, 7, 8], [2, 7, 3, 8],
        [1, 5, 6, 8], [1, 6, 2, 8],
        [0, 3, 7, 8], [0, 7, 4, 8],
    ], dtype=np.int64)
    r, new_pts = smooth_amips(
        pts, tets,
        locked_vertex_ids=np.arange(8),
        n_iter=5, alpha=1.0,
    )
    assert r.energy_after <= r.energy_before + 1e-6


def test_use_torch_amips_in_harness_params_fine() -> None:
    """beta2310 — HARNESS_PARAMS["tier_native_tet"]["fine"] 가 use_torch_amips=True.

    P2.2: fine quality 에서 amips_torch (CUDA 가용 시 GPU) 자동 라우팅.
    CUDA 미가용 환경에선 mesher 가 자동 numpy fallback (not is_available)."""
    import inspect
    from core.generator._tier_native_common import HARNESS_PARAMS, run_native_tier
    fine = HARNESS_PARAMS["tier_native_tet"]["fine"]
    assert fine.get("use_torch_amips") is True, \
        "fine quality 에 use_torch_amips=True 누락"
    # allowlist 통과 (CLI/GUI tier_specific_params 도 도달).
    src = inspect.getsource(run_native_tier)
    assert '"use_torch_amips"' in src, "_TIER_PARAM_KEYS allowlist 누락"


def test_mesher_signature_accepts_use_torch_amips() -> None:
    """beta2310 — generate_native_tet 시그너쳐에 use_torch_amips kwarg 노출."""
    import inspect
    from core.generator.native_tet.mesher import generate_native_tet
    sig = inspect.signature(generate_native_tet)
    assert "use_torch_amips" in sig.parameters
    assert sig.parameters["use_torch_amips"].default is False


def test_qed_decimate_auto_triggers_on_large_input() -> None:
    """beta2308 — quadric_decimate 가 50k+ face 입력에 자동 활성화.

    이전 (beta2243) 엔 AUTO_TESSELL_QED=1 명시 opt-in 만 → 대형 입력
    sliver 격감 효과가 사용자 환경에 도달 안함.
    beta2308 은 default "auto" → F.shape[0] > 50000 시 자동 ON.
    AUTO_TESSELL_QED=0 으로 강제 OFF / =1 로 강제 ON 옵트도 유지.
    """
    import inspect
    from core.generator.native_tet import mesher
    src = inspect.getsource(mesher)
    # 새 default 모드.
    assert 'AUTO_TESSELL_QED", "auto"' in src, \
        "AUTO_TESSELL_QED default 'auto' 누락"
    # 50000 임계.
    assert '"AUTO_TESSELL_QED_MIN_F", "50000"' in src, \
        "QED_MIN_F default 50000 누락"
    # auto 분기 자동 활성 로직.
    assert "_qed_on = (F.shape[0] > _qed_min)" in src, \
        "auto 분기 자동 활성 로직 누락"


def test_rrr2_monotone_guard_relaxed_to_worst_drop_0p015() -> None:
    """beta2307 — RRR2 의 monotone guard 가 worst -0.015 + mean improve 로 완화.

    이전 (pre-beta2307) 엔 strict guard `post.min() >= pre.min() - 1e-12`
    → 거의 모든 AMIPS 시도가 reject 되어 60+ round 카드 누적에도 grade A=0/20.

    beta2307 은 fTetWild §3.5 envelope-bounded relocation 의 활용을 위해
    worst 하락 ≤ 0.015 (절대 임계) + mean 향상 (≥ pre - 1e-12) 로 완화.
    SSS_REVIVAL block (line 2508) 의 동일 임계와 일관성.
    """
    import inspect
    from core.generator.native_tet import mesher
    src = inspect.getsource(mesher)
    # 새 임계 존재.
    assert "_worst_drop <= 0.015" in src, \
        "RRR2 worst_drop ≤ 0.015 임계 누락"
    # 옛 strict guard 잔존 금지.
    rrr2_strict = "post_q.min() >= pre_min - 1e-12 and post_q.mean() >= pre_mean - 1e-12"
    assert rrr2_strict not in src, \
        "RRR2 strict guard 잔존 — 완화되어야 함 (beta2307)"
