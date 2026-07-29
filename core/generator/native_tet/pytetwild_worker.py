"""Crash-isolated pytetwild bridge.

The extension can terminate the hosting interpreter during native teardown on
some builds.  Execute it in a disposable process and return only arrays.
"""

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
    edge_length_fac: float,
    epsilon: float,
    simplify: bool,
    stop_energy: float,
    num_threads: int,
    num_opt_iter: int,
    timeout_s: float = 180.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Run the extension outside the caller process."""
    with tempfile.TemporaryDirectory(prefix="autotessell_pytetwild_") as directory:
        root = Path(directory)
        source = root / "input.npz"
        result = root / "result.npz"
        error = root / "error.txt"
        np.savez_compressed(source, vertices=vertices, faces=faces)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--input", str(source),
            "--output", str(result),
            "--error", str(error),
            "--edge-length-fac", repr(float(edge_length_fac)),
            "--epsilon", repr(float(epsilon)),
            "--stop-energy", repr(float(stop_energy)),
            "--num-threads", str(max(1, int(num_threads))),
            "--num-opt-iter", str(max(0, int(num_opt_iter))),
            "--simplify", "1" if simplify else "0",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=float(timeout_s),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("pytetwild worker timed out") from exc
        if completed.returncode != 0 or not result.exists():
            detail = error.read_text(encoding="utf-8", errors="replace") if error.exists() else ""
            raise RuntimeError(
                "pytetwild worker failed: "
                + (detail or completed.stderr.strip() or str(completed.returncode))[:300]
            )
        with np.load(result) as data:
            return (
                np.asarray(data["vertices"], dtype=np.float64),
                np.asarray(data["tets"], dtype=np.int64),
            )


def _worker(args: argparse.Namespace) -> None:
    try:
        import pytetwild

        with np.load(args.input) as data:
            vertices = np.asarray(data["vertices"], dtype=np.float64)
            faces = np.asarray(data["faces"], dtype=np.int32)
        out_vertices, out_tets = pytetwild.tetrahedralize(
            vertices,
            faces,
            edge_length_fac=float(args.edge_length_fac),
            epsilon=float(args.epsilon),
            simplify=bool(args.simplify),
            stop_energy=float(args.stop_energy),
            num_threads=max(1, int(args.num_threads)),
            num_opt_iter=max(0, int(args.num_opt_iter)),
            quiet=True,
        )
        np.savez_compressed(
            args.output,
            vertices=np.asarray(out_vertices, dtype=np.float64),
            tets=np.asarray(out_tets, dtype=np.int64),
        )
    except Exception as exc:  # noqa: BLE001
        Path(args.error).write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        os._exit(2)
    # Avoid extension teardown in the worker process after the result is durable.
    os._exit(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--error", required=True)
    parser.add_argument("--edge-length-fac", required=True)
    parser.add_argument("--epsilon", required=True)
    parser.add_argument("--stop-energy", required=True)
    parser.add_argument("--num-threads", required=True)
    parser.add_argument("--num-opt-iter", required=True)
    parser.add_argument("--simplify", required=True, type=int)
    _worker(parser.parse_args())


if __name__ == "__main__":
    main()
