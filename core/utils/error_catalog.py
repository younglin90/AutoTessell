"""J6 / beta2631 — 중앙 error catalog (사용자 친화 메시지).

핵심 사용 패턴:
    from core.utils.error_catalog import format_error, ErrorCode
    msg = format_error(ErrorCode.MESH_EMPTY, n_cells=0, n_pts=0)

각 ErrorCode 마다:
    - 한국어 메시지 (사용자 표시).
    - 영문 short code (로깅).
    - 가능한 원인 + 해결 방안.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    """카테고리별 error code."""

    # Input.
    INPUT_NOT_FOUND = "INPUT_NOT_FOUND"
    INPUT_UNREADABLE = "INPUT_UNREADABLE"
    INPUT_TOO_SMALL = "INPUT_TOO_SMALL"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    INPUT_NOT_WATERTIGHT = "INPUT_NOT_WATERTIGHT"
    INPUT_NON_MANIFOLD = "INPUT_NON_MANIFOLD"
    INPUT_HIGH_SI = "INPUT_HIGH_SI"

    # Mesh generation.
    MESH_EMPTY = "MESH_EMPTY"
    MESH_INTEGRITY_SUSPECT = "MESH_INTEGRITY_SUSPECT"
    MESH_TIMEOUT = "MESH_TIMEOUT"
    MESH_OOM = "MESH_OOM"

    # Boundary layer.
    BL_NO_WALL = "BL_NO_WALL"
    BL_COLLISION = "BL_COLLISION"
    BL_ASPECT_DEGENERATE = "BL_ASPECT_DEGENERATE"

    # ML.
    ML_MODEL_MISSING = "ML_MODEL_MISSING"
    ML_TORCH_UNAVAILABLE = "ML_TORCH_UNAVAILABLE"
    ML_DATASET_TOO_SMALL = "ML_DATASET_TOO_SMALL"

    # Export.
    EXPORT_FORMAT_UNSUPPORTED = "EXPORT_FORMAT_UNSUPPORTED"
    EXPORT_H5PY_MISSING = "EXPORT_H5PY_MISSING"
    EXPORT_WRITE_FAIL = "EXPORT_WRITE_FAIL"


@dataclass(frozen=True)
class ErrorSpec:
    """단일 error 의 사용자 친화 메시지 + 해결책."""

    code: ErrorCode
    message_ko: str  # 사용자 표시.
    message_en: str  # 로깅 (short).
    causes: tuple[str, ...]
    solutions: tuple[str, ...]


_CATALOG: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.INPUT_NOT_FOUND: ErrorSpec(
        code=ErrorCode.INPUT_NOT_FOUND,
        message_ko="입력 파일을 찾을 수 없습니다",
        message_en="input file not found",
        causes=("경로 오타", "파일 권한 부족"),
        solutions=("절대 경로로 재시도", "ls 로 파일 확인"),
    ),
    ErrorCode.INPUT_UNREADABLE: ErrorSpec(
        code=ErrorCode.INPUT_UNREADABLE,
        message_ko="입력 파일을 읽을 수 없습니다 (포맷 인식 실패)",
        message_en="input file unreadable",
        causes=("지원 안 되는 포맷", "파일 손상", "binary STL 헤더 truncated"),
        solutions=("STL/OBJ/PLY/STEP 등 지원 포맷 확인", "scripts/validate_stl.py 실행"),
    ),
    ErrorCode.INPUT_TOO_SMALL: ErrorSpec(
        code=ErrorCode.INPUT_TOO_SMALL,
        message_ko="입력 mesh 가 너무 작습니다 (vertex/face < 4)",
        message_en="input mesh too small",
        causes=("degenerate mesh", "변환 실패"),
        solutions=("입력 파일 다시 확인", "다른 mesh source 사용"),
    ),
    ErrorCode.INPUT_TOO_LARGE: ErrorSpec(
        code=ErrorCode.INPUT_TOO_LARGE,
        message_ko="입력 mesh 가 max_input_vertices 초과",
        message_en="input mesh exceeds max_input_vertices",
        causes=("매우 dense surface mesh"),
        solutions=(
            "--remesh-target-faces 로 사전 decimation",
            "--max-input-vertices 늘리기",
            "scripts/validate_stl.py 로 mesh 크기 확인",
        ),
    ),
    ErrorCode.INPUT_NOT_WATERTIGHT: ErrorSpec(
        code=ErrorCode.INPUT_NOT_WATERTIGHT,
        message_ko="입력 mesh 가 watertight 가 아님 (열린 boundary)",
        message_en="input not watertight",
        causes=("hole 존재", "non-manifold edge"),
        solutions=(
            "--force-repair 로 자동 수리",
            "L1 repair 활성 (preprocessor)",
            "--mesh-type tet 권장 (open boundary 강건)",
        ),
    ),
    ErrorCode.INPUT_NON_MANIFOLD: ErrorSpec(
        code=ErrorCode.INPUT_NON_MANIFOLD,
        message_ko="입력 mesh 가 non-manifold (3+ face share edge)",
        message_en="input not manifold",
        causes=("CAD export 오류", "boolean 결과의 잔여"),
        solutions=("--force-repair 로 자동 수리", "외부 mesh repair tool 권장"),
    ),
    ErrorCode.INPUT_HIGH_SI: ErrorSpec(
        code=ErrorCode.INPUT_HIGH_SI,
        message_ko="입력 mesh 의 self-intersection 비율이 높음",
        message_en="high self-intersection ratio",
        causes=("CAD boolean 오류", "STL 변환 손상"),
        solutions=(
            "AUTO_TESSELL_P2_6_SI_RESOLVE=1 로 SI Boolean resolve 활성",
            "scripts/validate_stl.py 결과 확인",
        ),
    ),
    ErrorCode.MESH_EMPTY: ErrorSpec(
        code=ErrorCode.MESH_EMPTY,
        message_ko="볼륨 mesh 가 생성되지 않음 (cell 수=0)",
        message_en="empty volume mesh",
        causes=(
            "seed_density 너무 작음",
            "envelope eps 너무 작음 (모든 점 외부 판정)",
            "input geometry 너무 thin",
        ),
        solutions=(
            "--element-size 줄이기",
            "--bbox-relative-size 늘리기",
            "다른 --tier 시도",
        ),
    ),
    ErrorCode.MESH_INTEGRITY_SUSPECT: ErrorSpec(
        code=ErrorCode.MESH_INTEGRITY_SUSPECT,
        message_ko="mesh 무결성 의심 (cell 수가 비정상적으로 적음)",
        message_en="mesh integrity suspect",
        causes=("self-intersect 입력", "non-manifold 입력"),
        solutions=(
            "history dialog 의 Integrity 컬럼 확인",
            "--force-repair 활성",
            "--surface-remesh 권장",
        ),
    ),
    ErrorCode.MESH_TIMEOUT: ErrorSpec(
        code=ErrorCode.MESH_TIMEOUT,
        message_ko="mesh 생성 timeout",
        message_en="mesh generation timeout",
        causes=("매우 큰 mesh", "AMIPS 무한 루프"),
        solutions=(
            "--quality draft 로 더 빠르게",
            "AUTO_TESSELL_P4C_PYTETWILD=0 으로 fallback off",
            "더 큰 timeout 설정",
        ),
    ),
    ErrorCode.MESH_OOM: ErrorSpec(
        code=ErrorCode.MESH_OOM,
        message_ko="메모리 부족",
        message_en="out of memory",
        causes=("매우 큰 mesh + 많은 layer"),
        solutions=(
            "--max-cells 1000000 낮추기",
            "--bl-layers 줄이기",
            "swap 활성화 또는 더 큰 RAM",
        ),
    ),
    ErrorCode.BL_NO_WALL: ErrorSpec(
        code=ErrorCode.BL_NO_WALL,
        message_ko="BL 적용할 wall patch 가 없음",
        message_en="no wall patch for BL",
        causes=("--mesh-type 이 BL 미지원", "patch type=patch (not wall)"),
        solutions=(
            "--mesh-type hex_dominant 또는 tet 으로 변경",
            "boundary patch type 명시",
        ),
    ),
    ErrorCode.BL_COLLISION: ErrorSpec(
        code=ErrorCode.BL_COLLISION,
        message_ko="BL prism collision 검출 (좁은 gap 또는 self-intersect)",
        message_en="BL prism collision",
        causes=("좁은 channel", "self-intersect 표면"),
        solutions=(
            "--bl-layers 줄이기",
            "--lcr-auto-reduce 활성 (Pointwise T-Rex 동등)",
            "--bl-aniso-split 활성",
        ),
    ),
    ErrorCode.BL_ASPECT_DEGENERATE: ErrorSpec(
        code=ErrorCode.BL_ASPECT_DEGENERATE,
        message_ko="BL prism aspect ratio 가 너무 큼 (sliver 위험)",
        message_en="BL prism aspect degenerate",
        causes=("first_thickness 가 mean_edge 대비 너무 작음"),
        solutions=(
            "AUTO_TESSELL_BL_ASPECT_TARGET=500 으로 cap",
            "--bl-first-height 늘리기",
            "--bl-growth-ratio 줄이기",
        ),
    ),
    ErrorCode.ML_MODEL_MISSING: ErrorSpec(
        code=ErrorCode.ML_MODEL_MISSING,
        message_ko="ML 모델 파일이 없음",
        message_en="ML model file missing",
        causes=("AUTO_TESSELL_ML_SMOOTH_MODEL 환경변수 미설정", "잘못된 경로"),
        solutions=(
            "scripts/train_quality_predictor.py 로 학습 후 배포",
            "models/ml_smooth_model.pt 경로 확인",
            "--ml-smooth-model PATH 명시",
        ),
    ),
    ErrorCode.ML_TORCH_UNAVAILABLE: ErrorSpec(
        code=ErrorCode.ML_TORCH_UNAVAILABLE,
        message_ko="torch 라이브러리가 설치되지 않음",
        message_en="torch unavailable",
        causes=("pip install torch 안 됨"),
        solutions=("pip install torch (CUDA 권장)", "ML 기능 끄기 (env 미설정)"),
    ),
    ErrorCode.ML_DATASET_TOO_SMALL: ErrorSpec(
        code=ErrorCode.ML_DATASET_TOO_SMALL,
        message_ko="ML 학습 dataset 이 너무 작음 (sample < 10)",
        message_en="ML dataset too small",
        causes=("collect_ml_dataset.py 실패", "STL mesh 생성 실패"),
        solutions=(
            "--max-meshes 50+ 으로 dataset 더 수집",
            "--n-samples-per-mesh 300 권장",
        ),
    ),
    ErrorCode.EXPORT_FORMAT_UNSUPPORTED: ErrorSpec(
        code=ErrorCode.EXPORT_FORMAT_UNSUPPORTED,
        message_ko="지원하지 않는 export 포맷",
        message_en="export format unsupported",
        causes=("오타", "신규 포맷 미구현"),
        solutions=(
            "지원 포맷: txt / binary / ccmio / cgns / fluent / vtu / plt / x / ucd / neu",
        ),
    ),
    ErrorCode.EXPORT_H5PY_MISSING: ErrorSpec(
        code=ErrorCode.EXPORT_H5PY_MISSING,
        message_ko="h5py 미설치 (HDF5 포맷 export 불가)",
        message_en="h5py not installed",
        causes=("pip install h5py 안 됨"),
        solutions=("pip install h5py", "ASCII 포맷 사용 (txt/fluent/vtu/plt/ucd/neu)"),
    ),
    ErrorCode.EXPORT_WRITE_FAIL: ErrorSpec(
        code=ErrorCode.EXPORT_WRITE_FAIL,
        message_ko="export 파일 쓰기 실패",
        message_en="export write fail",
        causes=("디스크 공간 부족", "권한 문제"),
        solutions=("출력 디렉터리 권한 확인", "df 로 공간 확인"),
    ),
}


def format_error(
    code: ErrorCode,
    *,
    lang: str = "ko",
    include_solutions: bool = True,
    **kwargs,
) -> str:
    """ErrorCode → 사용자 친화 메시지.

    Args:
        code: ErrorCode.
        lang: "ko" (default) | "en".
        include_solutions: 해결책 list 포함.
        **kwargs: 메시지 .format() 에 전달할 추가 변수 (n_cells 등).

    Returns:
        formatted message string.
    """
    spec = _CATALOG.get(code)
    if spec is None:
        return f"[{code}] (unknown error code)"

    base_msg = spec.message_ko if lang == "ko" else spec.message_en
    try:
        base_msg = base_msg.format(**kwargs)
    except Exception:
        pass

    parts = [f"[{spec.code.value}] {base_msg}"]
    if kwargs:
        kvs = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        parts.append(f"  context: {kvs}")
    if include_solutions and spec.solutions:
        parts.append("  causes: " + " / ".join(spec.causes))
        parts.append("  solutions:")
        for s in spec.solutions:
            parts.append(f"    - {s}")

    return "\n".join(parts)


def lookup(code: ErrorCode) -> ErrorSpec | None:
    """code → ErrorSpec (또는 None)."""
    return _CATALOG.get(code)


def all_codes() -> list[ErrorCode]:
    """모든 등록된 ErrorCode list."""
    return list(_CATALOG.keys())
