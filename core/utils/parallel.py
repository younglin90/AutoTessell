"""OpenFOAM 병렬 분해 설정 (decomposeParDict).

대규모 메쉬에서 MPI 병렬 처리를 위한 도메인 분해 설정을 생성한다.
"""

from __future__ import annotations

import os
from pathlib import Path

from core.utils.logging import get_logger

log = get_logger(__name__)


def write_decompose_par_dict(
    case_dir: Path,
    n_procs: int | None = None,
    method: str = "scotch",
) -> Path:
    """system/decomposeParDict를 생성한다.

    Args:
        case_dir: OpenFOAM case 디렉터리.
        n_procs: 프로세서 수 (None이면 CPU 코어 수의 절반).
        method: 분해 방법 ("scotch", "hierarchical", "simple").

    Returns:
        생성된 파일 경로.
    """
    if n_procs is None:
        n_procs = max(1, os.cpu_count() or 1)

    path = case_dir / "system" / "decomposeParDict"
    path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      decomposeParDict;
}}

numberOfSubdomains  {n_procs};
method              {method};

// scotch: automatic balanced decomposition (recommended)
// hierarchical: regular grid decomposition
// simple: simple geometric split

coeffs
{{
}}

// To run in parallel:
//   decomposePar -case {case_dir}
//   mpirun -np {n_procs} simpleFoam -parallel -case {case_dir}
//   reconstructPar -case {case_dir}
"""
    path.write_text(content)
    log.info("decompose_par_dict_written", path=str(path), n_procs=n_procs, method=method)
    return path
