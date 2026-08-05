from __future__ import annotations

import json
from pathlib import Path

from core.generator.native_tet.writer_ledger_receipt import (
    interface_children_from_writer_ledger,
)
from tests.test_native_tet_writer_ledger_validation import _payload


def test_writer_ledger_bridge_preserves_direct_child_ids(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = interface_children_from_writer_ledger(path)

    assert rows[0]["source_face"] == "face-0"
    assert rows[0]["children"][0]["output_face_id"] == "wall-0"
    assert rows[0]["children"][0]["disk_face_id"] == 0
    assert rows[0]["children"][0]["output_vertex_ids"] == [0, 1, 2]
