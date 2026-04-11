"""OpenFOAM utils shell safety tests."""

import shlex
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.utils.openfoam_utils import (
    _to_wsl_linux_path,
    get_openfoam_label_size,
    run_openfoam,
)

def test_run_openfoam_with_spaces_in_path():
    """공백이 포함된 경로에서도 full_cmd가 올바르게 구성되는지 확인."""
    case_dir = Path("/tmp/my case dir")
    bashrc = Path("/opt/openfoam/etc/bashrc")
    
    with patch("core.utils.openfoam_utils._find_openfoam_bashrc", return_value=bashrc):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            
            run_openfoam("blockMesh", case_dir, args=["-parallel", "log file"])
            
            # subprocess.run 호출 시 전달된 cmd 확인
            args, kwargs = mock_run.call_args
            full_cmd = args[0][2] # ["bash", "-c", full_cmd]
            
            assert f"source {shlex.quote(str(bashrc))}" in full_cmd
            assert f"-case {shlex.quote(str(case_dir))}" in full_cmd
            assert shlex.quote("-parallel") in full_cmd
            assert shlex.quote("log file") in full_cmd
            # 공백이 적절히 quote 되었는지 확인
            assert "'/tmp/my case dir'" in full_cmd or '"/tmp/my case dir"' in full_cmd
            assert "'log file'" in full_cmd or '"log file"' in full_cmd


def test_get_openfoam_label_size_prefers_int64_when_both_exist(tmp_path: Path):
    """Int32/Int64 플랫폼이 공존하면 Int64를 우선해야 한다."""
    of_dir = tmp_path / "openfoam2406"
    (of_dir / "etc").mkdir(parents=True)
    (of_dir / "etc" / "bashrc").write_text("# test")
    (of_dir / "platforms" / "linux64GccDPInt32Opt").mkdir(parents=True)
    (of_dir / "platforms" / "linux64GccDPInt64Opt").mkdir(parents=True)

    with patch("core.utils.openfoam_utils._find_openfoam_bashrc", return_value=of_dir / "etc" / "bashrc"):
        assert get_openfoam_label_size() == 64


def test_to_wsl_linux_path_converts_unc() -> None:
    """WSL UNC 입력을 Linux 경로 + distro로 변환해야 한다."""
    path, distro = _to_wsl_linux_path(r"\\wsl.localhost\Ubuntu\home\user\case")
    assert path == "/home/user/case"
    assert distro == "Ubuntu"
