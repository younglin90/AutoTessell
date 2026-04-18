"""배치 처리 — 여러 STL 또는 파라미터 스윕을 연속 실행.

CFD 튜닝 시나리오:
1. 동일 파일 × epsilon [0.001, 0.002, 0.005] → 3 job
2. 5개 STL 동일 프리셋 → 5 job
3. 혼합: 3개 STL × 2 epsilon → 6 job

각 job은 기존 PipelineWorker를 재사용해 직렬 실행.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchJob:
    """단일 배치 항목."""

    input_path: Path
    output_dir: Path
    quality_level: str = "draft"
    tier_hint: str = "auto"
    params: dict = field(default_factory=dict)  # tier_specific_params
    preset_name: str = ""  # UI 표시용
    # 실행 결과 (채워짐)
    status: JobStatus = JobStatus.PENDING
    elapsed_seconds: float = 0.0
    n_cells: int = 0
    error: str | None = None

    def display_name(self) -> str:
        """테이블에 표시할 짧은 이름."""
        base = self.input_path.stem
        if self.params:
            # 파라미터 키=값 한두개 간단 표시
            keys = list(self.params.keys())[:2]
            parts = [f"{k}={self.params[k]}" for k in keys]
            return f"{base} ({', '.join(parts)})"
        return base


@dataclass
class BatchSummary:
    """실행 완료 후 요약."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    total_elapsed_seconds: float = 0.0

    @classmethod
    def from_jobs(cls, jobs: list[BatchJob]) -> BatchSummary:
        s = cls()
        s.total = len(jobs)
        for j in jobs:
            if j.status == JobStatus.SUCCESS:
                s.succeeded += 1
            elif j.status == JobStatus.FAILED:
                s.failed += 1
            elif j.status == JobStatus.CANCELLED:
                s.cancelled += 1
            s.total_elapsed_seconds += j.elapsed_seconds
        return s

    def pass_rate(self) -> float:
        """0.0~1.0 — 성공 비율."""
        if self.total == 0:
            return 0.0
        return self.succeeded / self.total


def make_parameter_sweep(
    base_input: Path,
    output_root: Path,
    quality_level: str,
    tier_hint: str,
    sweep_key: str,
    sweep_values: list,
    preset_name: str = "",
) -> list[BatchJob]:
    """하나의 파일 × 파라미터 값 리스트 → Job 리스트.

    예: sweep_key="epsilon", values=[0.001, 0.002, 0.005]
    → 3개의 BatchJob (output dir도 자동으로 epsilon별로 분리)
    """
    jobs: list[BatchJob] = []
    for v in sweep_values:
        # output_dir = output_root / {stem}_{key}_{value}
        safe_v = str(v).replace(".", "p").replace("-", "neg")
        out = output_root / f"{base_input.stem}_{sweep_key}_{safe_v}"
        jobs.append(
            BatchJob(
                input_path=base_input,
                output_dir=out,
                quality_level=quality_level,
                tier_hint=tier_hint,
                params={sweep_key: v},
                preset_name=preset_name,
            )
        )
    return jobs


def make_file_batch(
    input_paths: list[Path],
    output_root: Path,
    quality_level: str,
    tier_hint: str,
    params: dict | None = None,
    preset_name: str = "",
) -> list[BatchJob]:
    """여러 파일 × 동일 설정 → Job 리스트.

    output_dir = output_root / {stem}_case
    """
    jobs: list[BatchJob] = []
    for p in input_paths:
        jobs.append(
            BatchJob(
                input_path=p,
                output_dir=output_root / f"{p.stem}_case",
                quality_level=quality_level,
                tier_hint=tier_hint,
                params=dict(params) if params else {},
                preset_name=preset_name,
            )
        )
    return jobs
