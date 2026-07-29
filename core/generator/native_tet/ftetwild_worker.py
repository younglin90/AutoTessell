"""Crash-isolated vendored fTetWild bridge for native-tet P4C recovery."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np


def tetrahedralize(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    edge_length_r: float,
    epsilon: float,
    skip_simplify: bool,
    stop_quality: float,
    max_threads: int,
    max_its: int,
    timeout_s: float = 180.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Run vendored C++ fTetWild outside caller process."""
    with tempfile.TemporaryDirectory(prefix="autotessell_ftetwild_") as directory:
        root = Path(directory)
        source = root / "input.npz"
        result = root / "result.npz"
        error = root / "error.txt"
        # These files are local, short-lived IPC.  Compression only adds
        # Python CPU time before/after the native solve and gives no durable
        # storage benefit.
        np.savez(source, vertices=vertices, faces=faces)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--input", str(source),
            "--output", str(result),
            "--error", str(error),
            "--edge-length-r", repr(float(edge_length_r)),
            "--epsilon", repr(float(epsilon)),
            "--stop-quality", repr(float(stop_quality)),
            "--max-threads", str(max(1, int(max_threads))),
            "--max-its", str(max(0, int(max_its))),
            "--skip-simplify", "1" if skip_simplify else "0",
        ]
        repo_root = Path(__file__).resolve().parents[3]
        worker_env = os.environ.copy()
        worker_env["PYTHONPATH"] = (
            str(repo_root)
            + os.pathsep
            + worker_env.get("PYTHONPATH", "")
        )
        try:
            completed = subprocess.run(
                command,
                # fTetWild can emit a line per optimization iteration.  The
                # parent only needs stderr on failure; retaining stdout turns
                # a long native run into avoidable Python-side memory pressure.
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=float(timeout_s),
                check=False,
                cwd=str(repo_root),
                env=worker_env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("vendored fTetWild worker timed out") from exc
        if completed.returncode != 0 or not result.exists():
            detail = error.read_text(encoding="utf-8", errors="replace") if error.exists() else ""
            raise RuntimeError(
                "vendored fTetWild worker failed: "
                + (detail or completed.stderr.strip() or str(completed.returncode))[:300]
            )
        with np.load(result) as data:
            return (
                np.asarray(data["vertices"], dtype=np.float64),
                np.asarray(data["tets"], dtype=np.int64),
            )


def _worker(args: argparse.Namespace) -> None:
    try:
        from core.generator.native_tet.wildmesh_native_wrapper import (
            generate_via_wildmeshing,
        )

        with np.load(args.input) as data:
            vertices = np.asarray(data["vertices"], dtype=np.float64)
            faces = np.asarray(data["faces"], dtype=np.int64)
        out_vertices, out_tets, result = generate_via_wildmeshing(
            vertices,
            faces,
            edge_length_r=float(args.edge_length_r),
            epsilon=float(args.epsilon),
            skip_simplify=bool(args.skip_simplify),
            stop_quality=float(args.stop_quality),
            max_threads=max(1, int(args.max_threads)),
            max_its=max(0, int(args.max_its)),
            coarsen=True,
            correct_surface_orientation=True,
        )
        if not result.success:
            raise RuntimeError(result.message)
        np.savez(
            args.output,
            vertices=np.asarray(out_vertices, dtype=np.float64),
            tets=np.asarray(out_tets, dtype=np.int64),
        )
    except Exception as exc:  # noqa: BLE001
        Path(args.error).write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        os._exit(2)
    # Avoid extension teardown after output is durable.
    os._exit(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--error", required=True)
    parser.add_argument("--edge-length-r", required=True)
    parser.add_argument("--epsilon", required=True)
    parser.add_argument("--stop-quality", required=True)
    parser.add_argument("--max-threads", required=True)
    parser.add_argument("--max-its", required=True)
    parser.add_argument("--skip-simplify", required=True, type=int)
    _worker(parser.parse_args())


if __name__ == "__main__":
    main()
