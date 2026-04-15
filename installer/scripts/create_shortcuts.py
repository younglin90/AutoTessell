"""Windows 바로가기 및 시작 메뉴 항목 생성 스크립트."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def create_shortcut(
    target: Path,
    shortcut_path: Path,
    description: str = "",
    icon: Path | None = None,
) -> bool:
    """Windows .lnk 바로가기를 생성한다."""
    try:
        import win32com.client  # pywin32
        shell = win32com.client.Dispatch("WScript.Shell")
        lnk = shell.CreateShortcut(str(shortcut_path))
        lnk.TargetPath = str(target)
        lnk.Description = description
        if icon:
            lnk.IconLocation = str(icon)
        lnk.save()
        return True
    except ImportError:
        # pywin32가 없으면 PowerShell로 생성
        import subprocess
        ps_cmd = (
            f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{shortcut_path}');"
            f"$s.TargetPath='{target}';"
            f"$s.Description='{description}';"
            f"$s.Save()"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  [경고] 바로가기 생성 실패: {e}")
        return False


def main() -> None:
    if sys.platform != "win32":
        return

    install_root = Path(__file__).resolve().parents[3]
    python_exe = Path(sys.executable)
    gui_launcher = install_root / "installer" / "scripts" / "launch_gui.bat"

    # launch_gui.bat 생성
    gui_launcher.write_text(
        f'@echo off\n"{python_exe}" -m desktop.qt_main\n',
        encoding="utf-8",
    )

    # 바탕화면 바로가기
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    if desktop.exists():
        ok = create_shortcut(
            target=gui_launcher,
            shortcut_path=desktop / "AutoTessell.lnk",
            description="AutoTessell — CAD/Mesh to OpenFOAM polyMesh",
        )
        print(f"  바탕화면 바로가기: {'완료' if ok else '실패'}")

    # 시작 메뉴
    start_menu = (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "AutoTessell"
    )
    start_menu.mkdir(parents=True, exist_ok=True)
    ok = create_shortcut(
        target=gui_launcher,
        shortcut_path=start_menu / "AutoTessell.lnk",
        description="AutoTessell GUI",
    )
    print(f"  시작 메뉴 항목: {'완료' if ok else '실패'}")


if __name__ == "__main__":
    main()
