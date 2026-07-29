"""HEX-GEAR-DEGEN-DROP-1 — identify writer-dropped raw gear cells.

This is a report-only diagnostic.  It captures the in-memory cell list at the
public writer boundary, reproduces the generic writer's face-cleaning rule,
and reports the exact raw cell/face that makes each cell droppable.  It does
not patch production code or change the generated mesh.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from typing import Any

import numpy as np

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402


GEAR = Path(REPO) / "tests" / "stl" / "04_extreme_gear.stl"


class Capture:
    def __init__(self, real: Any) -> None:
        self.real = real
        self.points: np.ndarray | None = None
        self.cells: list[list[list[int]]] | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if len(args) >= 2:
            self.points = np.asarray(args[0], dtype=np.float64).copy()
            self.cells = [
                [[int(v) for v in face] for face in cell]
                for cell in args[1]
            ]
        return self.real(*args, **kwargs)


def clean_face(
    points: np.ndarray, face: list[int], area_eps: float
) -> tuple[list[int] | None, dict[str, Any]]:
    cleaned: list[int] = []
    seen: set[int] = set()
    consecutive_removed: list[int] = []
    repeated_removed: list[int] = []
    for raw_v in face:
        v = int(raw_v)
        if cleaned and cleaned[-1] == v:
            consecutive_removed.append(v)
            continue
        if v in seen:
            repeated_removed.append(v)
            continue
        cleaned.append(v)
        seen.add(v)
    if len(cleaned) >= 2 and cleaned[-1] == cleaned[0]:
        cleaned.pop()
    geometric_area = 0.0
    if len(cleaned) >= 3:
        pts = points[np.asarray(cleaned, dtype=np.int64)]
        base = pts[0]
        for i in range(1, len(cleaned) - 1):
            geometric_area += 0.5 * float(
                np.linalg.norm(np.cross(pts[i] - base, pts[i + 1] - base))
            )
    reason = "ok"
    if len(cleaned) < 3:
        reason = "fewer-than-3-unique-vertices"
    elif geometric_area <= area_eps:
        reason = "near-zero-face-area"
    elif consecutive_removed or repeated_removed:
        reason = "duplicate-vertex-cleaned-but-face-survives"
    detail = {
        "raw_face": list(face),
        "cleaned_face": list(cleaned),
        "raw_len": len(face),
        "clean_len": len(cleaned),
        "consecutive_removed": consecutive_removed,
        "repeated_removed": repeated_removed,
        "area": geometric_area,
        "area_eps": area_eps,
        "reason": reason,
    }
    return (cleaned if reason != "near-zero-face-area" and len(cleaned) >= 3 else None), detail


def main() -> int:
    import core.generator.polymesh_writer as writer_module

    native = writer_module._load_native_polymesh()
    print(f"native_polymesh_available={native is not None}")
    capture = Capture(writer_module.write_generic_polymesh)
    writer_module.write_generic_polymesh = capture
    try:
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                GEAR,
                case,
                quality_level="fine",
                mesh_type="hex_dominant",
                tier_hint="native_hex",
                max_iterations=1,
                auto_retry="off",
                strict_tier=True,
                write_of_case=True,
                max_cells=8000,
                tier_specific_params={
                    "max_cells": 8000,
                    "target_cells": 8000,
                    "bl_layers": 0,
                },
            )
            if capture.points is None or capture.cells is None:
                print(f"NO_CAPTURE error={result.error}")
                return 1
            points = capture.points
            cells = capture.cells
            bbox_diag = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
            area_eps = max((bbox_diag * 1e-12) ** 2, 1e-30)
            print(
                f"raw_points={len(points)} raw_cells={len(cells)} "
                f"bbox_diag={bbox_diag:.17g} area_eps={area_eps:.17g}"
            )

            dropped: list[dict[str, Any]] = []
            for cell_id, faces in enumerate(cells):
                details: list[dict[str, Any]] = []
                fatal: dict[str, Any] | None = None
                for face_id, face in enumerate(faces):
                    _, detail = clean_face(points, face, area_eps)
                    detail["cell_id"] = cell_id
                    detail["face_id"] = face_id
                    details.append(detail)
                    if detail["reason"] in {
                        "fewer-than-3-unique-vertices",
                        "near-zero-face-area",
                    }:
                        if fatal is None:
                            fatal = detail
                if fatal is not None or len(details) < 4:
                    dropped.append(
                        {
                            "cell_id": cell_id,
                            "n_faces": len(faces),
                            "fatal": fatal,
                            "checked_faces": details,
                            "drop_reason": (
                                fatal["reason"]
                                if fatal is not None
                                else "fewer-than-4-surviving-faces"
                            ),
                        }
                    )

            print(f"reproduced_dropped_cells={len(dropped)}")
            grouped: dict[tuple[int, ...], list[int]] = {}
            for row in dropped:
                fatal = row["fatal"]
                if fatal is None:
                    continue
                key = tuple(sorted(int(v) for v in fatal["cleaned_face"]))
                grouped.setdefault(key, []).append(int(row["cell_id"]))
            print(f"unique_degenerate_face_keys={len(grouped)}")
            for key, cell_ids in grouped.items():
                print(f"DEGENERATE_FACE_KEY verts={key} cells={cell_ids}")
            for row in dropped:
                fatal = row["fatal"]
                print(
                    f"DROP cell={row['cell_id']} reason={row['drop_reason']} "
                    f"n_faces={row['n_faces']}"
                )
                if fatal is not None:
                    fatal_points = points[np.asarray(fatal["cleaned_face"], dtype=np.int64)]
                    centered = fatal_points - fatal_points.mean(axis=0)
                    rank = int(np.linalg.matrix_rank(centered, tol=1e-12))
                    print(
                        "  face="
                        f"{fatal['face_id']} raw={fatal['raw_face']} "
                        f"cleaned={fatal['cleaned_face']} "
                        f"area={fatal['area']:.17g} "
                        f"eps={fatal['area_eps']:.17g} "
                        f"rank={rank} "
                        f"consecutive={fatal['consecutive_removed']} "
                        f"repeated={fatal['repeated_removed']}"
                    )
                    for vertex_id, point in zip(fatal["cleaned_face"], fatal_points):
                        print(
                            f"    v={vertex_id} xyz="
                            f"({point[0]:.17g},{point[1]:.17g},{point[2]:.17g})"
                        )
                    print("  cell_faces:")
                    for detail in row["checked_faces"]:
                        print(
                            f"    face={detail['face_id']} "
                            f"verts={detail['raw_face']} "
                            f"cleaned_area={detail['area']:.17g} "
                            f"reason={detail['reason']}"
                        )
                for detail in row["checked_faces"]:
                    if detail is fatal:
                        continue
                    if detail["consecutive_removed"] or detail["repeated_removed"]:
                        print(
                            "  nonfatal-duplicate "
                            f"face={detail['face_id']} raw={detail['raw_face']} "
                            f"cleaned={detail['cleaned_face']} "
                            f"area={detail['area']:.17g}"
                        )
            return 0
    finally:
        writer_module.write_generic_polymesh = capture.real


if __name__ == "__main__":
    raise SystemExit(main())
