"""Parity checks for the optional native OpenFOAM faces parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.utils import polymesh_reader as reader


def _native_metrics_or_skip():
    module = reader._load_native_metrics()
    if module is None or not hasattr(module, "parse_foam_faces_file"):
        pytest.skip("native_metrics parser extension is not built")
    return module


def _write_faces(path: Path, body: str) -> Path:
    path.write_text(
        "FoamFile\n"
        "{\n"
        "    version 2.0;\n"
        "    format ascii;\n"
        "    class faceList;\n"
        '    location "constant/polyMesh";\n'
        "    object faces;\n"
        "}\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return path


def _parse_with_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
) -> list[list[int]]:
    monkeypatch.setattr(reader, "_NATIVE_METRICS", None)
    monkeypatch.setattr(reader, "_NATIVE_METRICS_IMPORT_ATTEMPTED", True)
    return reader.parse_foam_faces(path)


def test_native_faces_parser_matches_python_forms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _native_metrics_or_skip()
    faces_file = _write_faces(
        tmp_path / "faces",
        """4 // declared face count
        (
            4(0 1 2 3) // compact
            3 ( +4 -5 6 )
            0() /* empty face */
            2/* between count and list */(7 // within face
                8)
        )""",
    )

    native = module.parse_foam_faces_file(faces_file)
    python = _parse_with_python_fallback(monkeypatch, faces_file)

    assert native == python == [[0, 1, 2, 3], [4, -5, 6], [], [7, 8]]


def test_native_faces_parser_accepts_empty_outer_list(tmp_path: Path) -> None:
    module = _native_metrics_or_skip()
    faces_file = _write_faces(tmp_path / "faces", "0\n(\n)")

    assert module.parse_foam_faces_file(faces_file) == []


@pytest.mark.parametrize(
    "body",
    [
        "2 ( 3(0 1 2) )",
        "1 ( 3(0 1) )",
        "1 ( 2(0 1 2) )",
        "1 ( -2() )",
        "1 ( 2(0 bad) )",
        "1 ( 2(0 1)",
    ],
)
def test_native_faces_parser_rejects_malformed(tmp_path: Path, body: str) -> None:
    module = _native_metrics_or_skip()
    faces_file = _write_faces(tmp_path / "faces", body)

    with pytest.raises((RuntimeError, ValueError)):
        module.parse_foam_faces_file(faces_file)


def test_parse_foam_faces_falls_back_after_native_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faces_file = _write_faces(tmp_path / "faces", "2 ( 3(0 1 2) 3(2 1 3) )")

    class FailingNativeMetrics:
        @staticmethod
        def parse_foam_faces_file(_path: Path) -> list[list[int]]:
            raise RuntimeError("forced native parser failure")

    monkeypatch.setattr(reader, "_NATIVE_METRICS", FailingNativeMetrics())
    monkeypatch.setattr(reader, "_NATIVE_METRICS_IMPORT_ATTEMPTED", True)

    assert reader.parse_foam_faces(faces_file) == [[0, 1, 2], [2, 1, 3]]
