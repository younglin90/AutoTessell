from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "auto_tessell_core" / "build"))
import native_tet_polymesh_quality as native  # noqa: E402
from test_native_tet_polymesh_quality import _write_cube  # noqa: E402


def test_debug_oracle(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_cube(root)
    result = dict(native.audit(str(root)))
    print(result)
    assert result["valid"] is True
