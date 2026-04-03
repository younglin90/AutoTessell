"""OpenFOAM utils shell safety tests."""

import shlex
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.utils.openfoam_utils import run_openfoam

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
