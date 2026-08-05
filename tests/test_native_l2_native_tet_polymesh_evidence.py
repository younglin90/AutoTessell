from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import shutil

from core.evaluator.native_l2_evidence_audit import (
    audit_native_tet_polymesh_persisted_evidence,
)

BUILD = Path("auto_tessell_core/build").resolve()

POINTS = """FoamFile
{
    format ascii;
}
4
(
(0.27652929 -1.34456104 -0.00555535)
(0.02560822 0.67669257 0.53413318)
(-1.96273171 0.52735918 0.04309917)
(-1.71675168 -1.46212854 -0.38129397)
)
"""
FACES = """FoamFile
{
    format ascii;
}
4
(
3(0 2 1)
3(0 1 3)
3(0 3 2)
3(1 2 3)
)
"""
OWNER = """FoamFile
{
    format ascii;
}
4
(
0
0
0
0
)
"""
NEIGHBOUR = """FoamFile
{
    format ascii;
}
0
(
)
"""
BOUNDARY = """FoamFile
{
    format ascii;
}
1
(
wall
{
    type wall;
    nFaces 4;
    startFace 0;
}
)
"""

def _write_polymesh(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name, value in {
        "points": POINTS,
        "faces": FACES,
        "owner": OWNER,
        "neighbour": NEIGHBOUR,
        "boundary": BOUNDARY,
    }.items():
        (path / name).write_text(value)

def _tree_digest(path: Path) -> str:
    raw = b""
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        raw += name.encode() + b"\0" + (path / name).read_bytes() + b"\0"
    return sha256(raw).hexdigest()

def _make_root(tmp_path: Path, layers: int = 0) -> Path:
    root = tmp_path / f"tet-polymesh-{layers}"
    source = b"authoritative-tet-source"
    (root / "source").mkdir(parents=True)
    (root / "source/raw-source.stl").write_bytes(source)
    paths = {
        "output": root / "output/case/constant/polyMesh",
        "baseline": root / "baseline/case/constant/polyMesh",
        "run1": root / "runs/run-1/case/constant/polyMesh",
        "run2": root / "runs/run-2/case/constant/polyMesh",
        "run3": root / "runs/run-3/case/constant/polyMesh",
    }
    for path in paths.values():
        _write_polymesh(path)
    if layers:
        positive_points = POINTS.replace(
            "(-1.71675168 -1.46212854 -0.38129397)",
            "(-1.70675168 -1.46212854 -0.38129397)",
        )
        for key in ("output", "run1", "run2", "run3"):
            (paths[key] / "points").write_text(positive_points)
    ledger = "face-0\tedge-0\tflat\twall\tfluid\tmain\tforward\t0,1,2\t0\n"
    (root / "ledger.tsv").write_text(ledger)
    binding = (
        "face-0\t\t\tedge-0\twall-0\tstrip-0\tout-0\tvol-0\tflat\twall"
        "\tfluid\tmain\tdirect\t0\t1\t2\t3\tface-0\tstrip-0\t0\t0\t0\t0\n"
    )
    (root / "binding.tsv").write_text(binding if layers else "")
    (root / "layers.tsv").write_text("0\t0.1\t0.1\t0.1\t1.0\t0\t1\t2\t3\n" if layers else "")
    source_digest = sha256(source).hexdigest()
    artifact_digest = _tree_digest(paths["output"])
    digest_a = "a" * 64
    digest_b = "b" * 64
    digest_c = "c" * 64
    lines = [
        "schema=native-l2-persisted-evidence/v1",
        "engine=native_tet",
        "artifact_format=openfoam-polymesh-ascii/v1",
        "source_path=source/raw-source.stl",
        "polymesh_root=output/case/constant/polyMesh",
        "baseline_polymesh_root=baseline/case/constant/polyMesh",
        "run_polymesh_root_1=runs/run-1/case/constant/polyMesh",
        "run_polymesh_root_2=runs/run-2/case/constant/polyMesh",
        "run_polymesh_root_3=runs/run-3/case/constant/polyMesh",
        "ledger_path=ledger.tsv",
        "binding_path=binding.tsv",
        f"source_sha256={source_digest}",
        f"artifact_tree_sha256={artifact_digest}",
        f"build_sha256={digest_b}",
        f"config_sha256={digest_c}",
        f"baseline_digest={digest_a if layers == 0 else digest_b}",
        f"candidate_digest={digest_a if layers == 0 else digest_c}",
        f"requested_layers={layers}",
        f"actual_layers={layers}",
        f"bl0_exact_identity={'true' if layers == 0 else 'false'}",
    ]
    if layers:
        lines.extend([
            "positive_contract=true",
            "source_authority_kind=explicit-stl-facet-ledger",
            "source_authority_status=SOURCE_VERIFIED",
            "wall_edge_eligible=true",
            "writer_owned_id_capsule=true",
            "pure_tet=true",
            "layer_record_count=1",
            "wall_edge_binding_count=1",
            "first_thickness=0.1",
            "growth_ratio=1.0",
            "total_thickness=0.1",
            "quality_aspect_cap=5.0",
            "layer_path=layers.tsv",
        ])
    (root / "evidence.atne").write_text("\n".join(lines) + "\n")
    return root

def test_native_tet_polymesh_reader_accepts_bl0_and_recomputes_quality(tmp_path, monkeypatch):
    root = _make_root(tmp_path, 0)
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    first = audit_native_tet_polymesh_persisted_evidence(str(root))
    second = audit_native_tet_polymesh_persisted_evidence(str(root))
    assert first == second
    assert first["accepted"] is True
    assert first["status"] == "native_tet_polymesh_persisted_sealed"
    assert first["artifact_format"] == "openfoam-polymesh-ascii/v1"
    assert first["reader_native"] is True
    assert first["geometry_recomputed"] is True
    assert first["wall_front_status"] == "not_applicable_bl0"
    assert first["topology"]["duplicate"] == 0
    assert first["topology"]["non_manifold"] == 0
    assert first["topology"]["inverted"] == 0
    assert first["quality"]["minimum_cell_volume_or_jacobian"] > 0
    assert first["quality"]["max_skewness"] < 0.5
    assert first["quality"]["max_non_orthogonality_degrees"] < 35

def test_native_tet_polymesh_reader_accepts_positive_bl_contract(tmp_path, monkeypatch):
    root = _make_root(tmp_path, 1)
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    result = audit_native_tet_polymesh_persisted_evidence(str(root))
    assert result["accepted"] is True
    assert result["status"] == "native_tet_positive_bl_persisted_sealed"
    assert result["wall_front_status"] == "cxx_geometry_recomputed"
    assert result["quality"]["max_wall_front_orthogonality_degrees"] < 25
    assert result["quality"]["aspect_cap"] == 5.0
    assert result["actual_layers"] == 1

def test_native_tet_polymesh_reader_rejects_forged_final_cell_id(tmp_path, monkeypatch):
    root = _make_root(tmp_path, 1)
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    fields = (root / "binding.tsv").read_text().rstrip("\n").split("\t")
    fields[20] = "99"
    (root / "binding.tsv").write_text("\t".join(fields) + "\n")
    result = audit_native_tet_polymesh_persisted_evidence(str(root))
    assert result["accepted"] is False
    assert result["reason"] == "native_tet_positive_bl_final_cell_id_invalid"

def test_native_tet_polymesh_reader_rejects_tamper_and_missing_positive_contract(tmp_path, monkeypatch):
    root = _make_root(tmp_path, 0)
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    (root / "output/case/constant/polyMesh/faces").write_text(
        FACES.replace("3(0 2 1)", "3(0 1 2)")
    )
    tampered = audit_native_tet_polymesh_persisted_evidence(str(root))
    assert tampered["accepted"] is False
    assert tampered["reason"] == "native_tet_artifact_digest_mismatch"

    positive = _make_root(tmp_path, 1)
    evidence = (positive / "evidence.atne").read_text()
    (positive / "evidence.atne").write_text(evidence.replace("positive_contract=true", "positive_contract=false"))
    result = audit_native_tet_polymesh_persisted_evidence(str(positive))
    assert result["accepted"] is False
    assert result["reason"] == "native_tet_positive_bl_artifact_contract_missing"

def test_native_tet_polymesh_reader_rejects_missing_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    result = audit_native_tet_polymesh_persisted_evidence(str(tmp_path / "missing"))
    assert result["accepted"] is False
    assert result["reason"] == "persisted_root_missing"
