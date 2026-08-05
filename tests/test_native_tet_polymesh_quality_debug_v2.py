from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "auto_tessell_core" / "build"))
sys.path.insert(0, str(_ROOT / "tests"))
import native_tet_polymesh_quality as native  # noqa: E402
from test_native_tet_polymesh_quality import _write_cube  # noqa: E402


def test_debug_oracle_v2(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_cube(root)
    result = dict(native.audit(str(root)))
    print(result)
    assert result["valid"] is True
