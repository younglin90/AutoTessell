from pathlib import Path
from types import SimpleNamespace
import shutil
import hashlib

from core.generator.native_tet.capsule import emit_native_tet_bl_capsule
from tests.test_native_l2_native_tet_polymesh_evidence import (
    BOUNDARY,
    FACES,
    NEIGHBOUR,
    OWNER,
    POINTS,
    _write_polymesh,
)


def _case(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    poly = case / "constant" / "polyMesh"
    _write_polymesh(poly)
    shutil.copytree(poly, case / "constant" / "polyMesh_pre_bl")
    source = case / "source" / "shape.stl"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"sealed source")
    (case / "native_bl_lineage.json").write_text(
        '{"schema":"native-tet-bl-direct-lineage/v1","records":[{"source_face":0,"source_vertices":[0,2,1],"patch_index":0,"owner_cell":0,"layer_point_ids":[[0,2,1],[0,2,1]],"prism_cell_ids":[0]}]}'
    )
    return case


def test_capsule_emits_actual_sidecars_and_direct_ids(tmp_path):
    case = _case(tmp_path)
    result = SimpleNamespace(direct_id_map={
        "schema": "native-tet-bl-direct-id-map/v1",
        "records": [{
            "source_face": 0,
            "source_vertices": [0, 2, 1],
            "patch_index": 0,
            "wall_face_ids": [0],
            "front_face_ids": [1],
            "final_cell_ids": [0],
        }],
    })
    ok, message = emit_native_tet_bl_capsule(
        case,
        authority={
            "source_path": "source/shape.stl",
            "source_sha256": hashlib.sha256(b"sealed source").hexdigest(),
            "source_authority_status": "SOURCE_VERIFIED",
            "source_authority_kind": "explicit-stl-facet-ledger",
            "wall_edge_eligible": True,
            "provisional": False,
            "feature": "wall",
            "patch": "wall",
            "physical_group": "fluid",
            "component": "main",
            "provenance": "direct",
        },
        subdivided=result,
        requested_layers=1,
        growth_ratio=1.0,
        first_thickness=0.1,
        quality_aspect_cap=100.0,
    )
    assert ok, message
    assert message == "native_tet_direct_id_capsule_emitted"
    assert not (case / "native_bl_lineage.json").exists()
    for name in ("evidence.atne", "ledger.tsv", "binding.tsv", "layers.tsv"):
        assert (case / name).is_file()
    binding = (case / "binding.tsv").read_text().rstrip("\n").split("\t")
    assert binding[20] == "0"
    assert binding[21] == "1"
    assert binding[22] == "0"


def test_capsule_refuses_unsealed_source_before_writing(tmp_path):
    case = _case(tmp_path)
    ok, message = emit_native_tet_bl_capsule(
        case,
        authority={
            "source_path": "source/shape.stl",
            "source_authority_status": "SOURCE_PROVISIONAL",
            "wall_edge_eligible": True,
        },
        subdivided=SimpleNamespace(direct_id_map={}),
        requested_layers=1,
        growth_ratio=1.0,
        first_thickness=0.1,
        quality_aspect_cap=100.0,
    )
    assert not ok
    assert message.endswith("source_authority_not_sealed")
    assert not (case / "evidence.atne").exists()


def test_capsule_refuses_source_digest_mismatch_before_writing(tmp_path):
    case = _case(tmp_path)
    ok, message = emit_native_tet_bl_capsule(
        case,
        authority={
            "source_path": "source/shape.stl",
            "source_sha256": "0" * 64,
            "source_authority_status": "SOURCE_VERIFIED",
            "wall_edge_eligible": True,
            "provisional": False,
        },
        subdivided=SimpleNamespace(direct_id_map={}),
        requested_layers=1,
        growth_ratio=1.0,
        first_thickness=0.1,
        quality_aspect_cap=100.0,
    )
