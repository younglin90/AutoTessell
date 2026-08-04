from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _cli() -> Path:
    candidates = [
        Path("auto_tessell_core/build/native_tet_persisted_volume_artifact_cli"),
        Path("auto_tessell_core/build/Debug/native_tet_persisted_volume_artifact_cli"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    pytest.skip("native persisted Tet child verifier has not been built")


def _write_tetra(root: Path) -> None:
    root.mkdir()
    (root / "points").write_text(
        "4\n(\n(0 0 0)\n(1 0 0)\n(0 1 0)\n(0 0 1)\n)\n",
        encoding="utf-8",
    )
    (root / "faces").write_text(
        "4\n(\n3(0 2 1)\n3(0 1 3)\n3(0 3 2)\n3(1 2 3)\n)\n",
        encoding="utf-8",
    )
    (root / "owner").write_text("4\n(\n0\n0\n0\n0\n)\n", encoding="utf-8")
    (root / "neighbour").write_text("0\n(\n)\n", encoding="utf-8")
    (root / "boundary").write_text(
        "1\n(\nwall\n{\n type wall;\n nFaces 4;\n startFace 0;\n}\n)\n",
        encoding="utf-8",
    )


def _write_ledger(path: Path) -> None:
    semantics = "tetra-wall wall fluid-wall fixture fixture-ledger"
    path.write_text(
        "\n".join(
            [
                "schema native-tet-source-ledger/v1",
                f"face face-z0 0 2 1 {semantics}",
                f"face face-y0 0 1 3 {semantics}",
                f"face face-x0 0 3 2 {semantics}",
                f"face face-top 1 2 3 {semantics}",
                f"cell cell-0 face-z0 {semantics}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _run(cli: Path, poly_mesh: Path, ledger: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(cli), str(poly_mesh), str(ledger)],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


def test_fresh_cpp_child_recomputes_persisted_tet_certificate(tmp_path: Path) -> None:
    cli = _cli()
    poly_mesh = tmp_path / "polyMesh"
    ledger = tmp_path / "source.ledger"
    _write_tetra(poly_mesh)
    _write_ledger(ledger)

    first = _run(cli, poly_mesh, ledger)
    second = _run(cli, poly_mesh, ledger)

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert "accepted=true" in first.stdout
    assert "status=native-tet-persisted-volume-child-verified" in first.stdout
    assert "topology_duplicate=0" in first.stdout
    assert "non_manifold=0" in first.stdout
    assert "inverted=0" in first.stdout
    assert "positive_measure=true" in first.stdout
    first_digest = next(line for line in first.stdout.splitlines() if line.startswith("certificate_sha256="))
    second_digest = next(line for line in second.stdout.splitlines() if line.startswith("certificate_sha256="))
    assert first_digest == second_digest


def test_fresh_cpp_child_refuses_tampered_source_orientation(tmp_path: Path) -> None:
    cli = _cli()
    poly_mesh = tmp_path / "polyMesh"
    ledger = tmp_path / "source.ledger"
    _write_tetra(poly_mesh)
    _write_ledger(ledger)
    ledger.write_text(ledger.read_text(encoding="utf-8").replace("face-z0 0 2 1", "face-z0 0 1 2"), encoding="utf-8")

    refused = _run(cli, poly_mesh, ledger)

    assert refused.returncode != 0
    assert "accepted=false" in refused.stdout
    assert "source_boundary_coverage_mismatch" in refused.stdout


def test_fresh_cpp_child_refuses_nonpositive_persisted_tet(tmp_path: Path) -> None:
    cli = _cli()
    poly_mesh = tmp_path / "polyMesh"
    ledger = tmp_path / "source.ledger"
    _write_tetra(poly_mesh)
    _write_ledger(ledger)
    (poly_mesh / "points").write_text(
        (poly_mesh / "points").read_text(encoding="utf-8").replace("(0 0 1)", "(0 0 0)"),
        encoding="utf-8",
    )

    refused = _run(cli, poly_mesh, ledger)

    assert refused.returncode != 0
    assert "accepted=false" in refused.stdout
    assert "persisted_tet_nonpositive_volume" in refused.stdout
