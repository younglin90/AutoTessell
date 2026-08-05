from __future__ import annotations

from pathlib import Path

from core.evaluator.native_canonical_quality_witness import build_authority_bound_volume_quality_witness

import pytest
from core.analyzer.readers import read_stl
from core.evaluator.native_canonical_quality_witness import build_canonical_quality_witness
from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_tet.mesher import generate_native_tet


def test_actual_cube_cpp_witness_matches_release_checker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    mesh = read_stl(Path("tests/benchmarks/cube.stl"))
    case = tmp_path / "cube"
    result = generate_native_tet(
        mesh.vertices, mesh.faces, case, seed_density=4, sliver_quality_threshold=0.0,
        enable_phase_a=False, recovery_iterations=0, smooth_iterations=0,
    )
    assert result.success
    witness = build_canonical_quality_witness(case)
    checker = NativeMeshChecker().run(case)
    assert witness["accepted"] is True
    assert witness["quality"]["release_skew"]["max"] == checker.max_skewness
    assert witness["quality"]["internal_non_orthogonality"]["max"] == pytest.approx(checker.max_non_orthogonality)
    assert witness["quality"]["boundary_skewness"]["status"] == "measured"
    assert witness["faces"][0]["face_uid"]
    assert witness["faces"][0]["owner_cell_uid"]
    assert witness["witness_sha256"]

    replay = [build_canonical_quality_witness(case)["witness_sha256"] for _ in range(3)]
    assert len(set(replay)) == 1


def test_cpp_witness_refuses_missing_case(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    result = build_canonical_quality_witness(tmp_path / "missing")
    assert result["accepted"] is False
    assert result["status"] == "unverified"



def _write_authority_cube(case: Path) -> None:
    poly = case / "constant" / "polyMesh"
    poly.mkdir(parents=True)
    (poly / "points").write_text("8\n(\n" + "".join(f"({x} {y} {z})\n" for x,y,z in ((0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1))) + ")\n")
    faces = ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
    (poly / "faces").write_text("6\n(\n" + "".join(f"4({ ' '.join(map(str, face)) })\n" for face in faces) + ")\n")
    (poly / "owner").write_text("6\n(\n0\n0\n0\n0\n0\n0\n)\n")
    (poly / "neighbour").write_text("0\n(\n)\n")


def _authority_case(output_sha: str = "b" * 64) -> tuple[dict[str, object], dict[str, object]]:
    source = "a" * 64
    source_authority = {"authoritative": True, "sha256": source}
    certificate = {
        "authoritative": True,
        "source_sha256": source,
        "output_sha256": output_sha,
        "source_shape_sha256": "c" * 64,
        "output_shape_sha256": "d" * 64,
        "feature_sha256": "e" * 64,
        "patch_sha256": "f" * 64,
        "physical_group_sha256": "1" * 64,
        "provenance_sha256": "2" * 64,
        "shape_preserved": True,
        "source_face_bindings": [{"source_face": "face-0", "output_boundary_faces": [0, 1, 2, 3, 4, 5]}],
    }
    return source_authority, certificate


def test_authority_bound_volume_witness_replays_persisted_cube(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    case = tmp_path / "cube"
    _write_authority_cube(case)
    source, certificate = _authority_case()
    witness = build_authority_bound_volume_quality_witness(
        case, source_authority=source, source_output_authority=certificate
    )
    assert witness["accepted"] is True, witness
    assert witness["schema"].endswith("authority-bound-quality-witness/v1")
    assert witness["witness_repeats"] == [witness["witness_sha256"]] * 3
    assert witness["quality"]["boundary_skewness"]["max"] < 1.0e-12
    assert witness["volume_quality"]["positive_geometry"] is True


def test_authority_bound_volume_witness_rejects_source_output_mismatch(tmp_path: Path) -> None:
    case = tmp_path / "cube"
    _write_authority_cube(case)
    source, certificate = _authority_case()
    certificate["source_sha256"] = "9" * 64
    witness = build_authority_bound_volume_quality_witness(
        case, source_authority=source, source_output_authority=certificate
    )
    assert witness["accepted"] is False
    assert witness["reason"] == "authority_source_binding_mismatch"
