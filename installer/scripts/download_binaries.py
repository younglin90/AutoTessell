"""Windows 외부 바이너리 자동 다운로드 스크립트.

인스톨러 post_install 단계에서 실행된다.
GitHub Releases에서 Windows 실행 파일을 다운로드해 bin/ 디렉터리에 배치한다.

다운로드 대상:
  - mmg3d.exe     (MMG3D — 고품질 tet 최적화)
  - HOHQMesh.exe  (HOHQMesh — 고차 Hex-Quad 메쉬)
  - libjigsaw.dll (JIGSAW — tet 메쉬 생성)
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

# AutoTessell 설치 루트 (post_install에서 PREFIX로 지정)
INSTALL_ROOT = Path(__file__).resolve().parents[3]
BIN_DIR = INSTALL_ROOT / "bin"
BIN_DIR.mkdir(exist_ok=True)

# GitHub Release 다운로드 URL 및 기대 파일명
# 각 URL은 AutoTessell GitHub 릴리스 또는 공식 저장소에서 관리한다.
BINARIES: list[dict] = [
    {
        "name": "mmg3d.exe",
        "url": (
            "https://github.com/MmgTools/mmg/releases/download/v5.7.3/"
            "mmg_windows_release.zip"
        ),
        "zip_member": "mmg3d_O3.exe",
        "target": "mmg3d.exe",
    },
    {
        "name": "HOHQMesh.exe",
        "url": (
            "https://github.com/trixi-framework/HOHQMesh/releases/download/v1.5.1/"
            "HOHQMesh-v1.5.1-Windows.zip"
        ),
        "zip_member": "HOHQMesh.exe",
        "target": "HOHQMesh.exe",
    },
    {
        "name": "libjigsaw.dll",
        "url": (
            "https://github.com/dengwirda/jigsaw/releases/download/v0.9.14/"
            "jigsaw-v0.9.14-Windows.zip"
        ),
        "zip_member": "lib/libjigsaw.dll",
        "target": "libjigsaw.dll",
    },
]


def _download(url: str, dest: Path) -> bool:
    """URL에서 dest로 파일을 다운로드한다. 성공 여부 반환."""
    print(f"  다운로드: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AutoTessell-Installer"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        return True
    except Exception as e:
        print(f"  [경고] 다운로드 실패: {e}")
        return False


def _extract_from_zip(zip_path: Path, member: str, target: Path) -> bool:
    """ZIP 파일에서 특정 멤버를 target으로 추출한다."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            # member가 정확히 없으면 이름 끝 부분으로 매칭
            names = zf.namelist()
            matched = next(
                (n for n in names if n.endswith(member) or n == member),
                None,
            )
            if matched is None:
                print(f"  [경고] ZIP 내 {member} 를 찾을 수 없음. 목록: {names[:10]}")
                return False
            with zf.open(matched) as src, open(target, "wb") as dst:
                dst.write(src.read())
        return True
    except Exception as e:
        print(f"  [경고] ZIP 추출 실패: {e}")
        return False


def main() -> None:
    import tempfile

    print("\n[AutoTessell] 외부 바이너리 다운로드")
    print(f"  대상 디렉터리: {BIN_DIR}\n")

    for spec in BINARIES:
        target = BIN_DIR / spec["target"]
        if target.exists():
            print(f"  {spec['name']}: 이미 존재, 건너뜀")
            continue

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        ok = _download(spec["url"], tmp_path)
        if ok and tmp_path.exists() and tmp_path.stat().st_size > 0:
            if spec.get("zip_member"):
                ok = _extract_from_zip(tmp_path, spec["zip_member"], target)
            else:
                tmp_path.rename(target)
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

        if ok and target.exists():
            print(f"  {spec['name']}: 완료 ({target.stat().st_size:,} bytes)")
        else:
            print(f"  {spec['name']}: 실패 (수동 설치 필요)")

    # jigsawpy _lib 디렉터리에도 libjigsaw.dll 복사
    jigsaw_dll = BIN_DIR / "libjigsaw.dll"
    if jigsaw_dll.exists():
        try:
            import jigsawpy
            lib_dir = Path(jigsawpy.__file__).parent / "_lib"
            lib_dir.mkdir(exist_ok=True)
            target_dll = lib_dir / "libjigsaw.dll"
            if not target_dll.exists():
                import shutil
                shutil.copy2(jigsaw_dll, target_dll)
                print(f"  libjigsaw.dll → jigsawpy/_lib/ 복사 완료")
        except Exception as e:
            print(f"  [경고] jigsawpy DLL 복사 실패: {e}")

    print("\n[AutoTessell] 바이너리 다운로드 완료\n")


if __name__ == "__main__":
    main()
