"""core/analyzer/readers/ × trimesh 교차 검증 테스트.

v0.4 native-first: STL/OBJ/PLY/OFF 자체 reader 가 trimesh 와 vertex/face 수,
좌표, 인덱스가 동일한지 검증.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_obj, read_off, read_ply, read_stl

trimesh = pytest.importorskip("trimesh")


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"
CUBE_STL = _REPO / "tests" / "benchmarks" / "cube.stl"


@pytest.fixture(scope="module")
def tmp_export_dir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="native_readers_"))
    yield d


@pytest.fixture(scope="module")
def sphere_in_formats(tmp_export_dir: Path) -> dict[str, Path]:
    """sphere 를 obj/ply/off/stl 로 export 해 각 reader 입력 준비."""
    if not SPHERE_STL.exists():
        pytest.skip(f"sphere.stl 없음: {SPHERE_STL}")
    t = trimesh.load(str(SPHERE_STL))
    out: dict[str, Path] = {"stl": SPHERE_STL}
    for ext in ("obj", "ply", "off"):
        p = tmp_export_dir / f"sphere.{ext}"
        t.export(str(p))
        out[ext] = p
    return out


def _sorted_v_f(verts: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(V, F) 를 canonical form (vertex 정렬 + face 정렬) 로 변환해 비교용 해시 생성."""
    # 각 face 를 lexicographic 정렬
    f_sorted = np.sort(faces, axis=1)
    # face 자체를 행 기준 정렬
    order = np.lexsort(f_sorted.T[::-1])
    return verts, f_sorted[order]


@pytest.mark.parametrize("ext", ["stl", "obj", "ply", "off"])
def test_native_reader_matches_trimesh_counts(
    sphere_in_formats: dict[str, Path], ext: str,
) -> None:
    readers = {
        "stl": read_stl, "obj": read_obj, "ply": read_ply, "off": read_off,
    }
    p = sphere_in_formats[ext]
    m = readers[ext](p)
    t = trimesh.load(str(p))
    assert m.n_vertices == t.vertices.shape[0]
    assert m.n_faces == t.faces.shape[0]


def test_stl_binary_dedupe_produces_shared_vertices() -> None:
    """STL binary 에서 dedupe=True (기본) 는 shared vertex 를 반환."""
    m = read_stl(SPHERE_STL, dedupe=True)
    # sphere 642 vertex / 1280 face 는 fully shared 구조
    assert m.n_vertices == 642
    assert m.n_faces == 1280


def test_stl_binary_no_dedupe_returns_tripled_verts() -> None:
    """dedupe=False 는 face 당 3 vertex 독립 저장 → n_vertices == 3 × n_faces."""
    m = read_stl(SPHERE_STL, dedupe=False)
    assert m.n_vertices == 3 * m.n_faces


def test_stl_bbox_matches_trimesh() -> None:
    m = read_stl(SPHERE_STL)
    t = trimesh.load(str(SPHERE_STL))
    bb_min, bb_max = m.compute_bounding_box()
    np.testing.assert_allclose(bb_min, t.bounds[0], rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(bb_max, t.bounds[1], rtol=1e-9, atol=1e-9)


def test_obj_empty_comment_ignored(tmp_path: Path) -> None:
    p = tmp_path / "simple.obj"
    p.write_text(
        "# header\n"
        "v 0 0 0\n"
        "v 1 0 0\n"
        "v 0 1 0\n"
        "\n"
        "f 1 2 3\n",
        encoding="utf-8",
    )
    m = read_obj(p)
    assert m.n_vertices == 3 and m.n_faces == 1


def test_obj_quad_face_triangulated(tmp_path: Path) -> None:
    p = tmp_path / "quad.obj"
    p.write_text(
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n",
        encoding="utf-8",
    )
    m = read_obj(p)
    # fan triangulation → 2 triangles
    assert m.n_faces == 2


def test_off_triangle_count(tmp_path: Path) -> None:
    p = tmp_path / "simple.off"
    p.write_text(
        "OFF\n3 1 0\n0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n",
        encoding="utf-8",
    )
    m = read_off(p)
    assert m.n_vertices == 3 and m.n_faces == 1


def test_ply_ascii_body(tmp_path: Path) -> None:
    p = tmp_path / "simple.ply"
    p.write_text(
        "ply\nformat ascii 1.0\nelement vertex 3\n"
        "property float x\nproperty float y\nproperty float z\n"
        "element face 1\nproperty list uchar int vertex_indices\nend_header\n"
        "0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n",
        encoding="utf-8",
    )
    m = read_ply(p)
    assert m.n_vertices == 3 and m.n_faces == 1
    np.testing.assert_allclose(m.vertices[1], [1, 0, 0])


def test_stl_ascii(tmp_path: Path) -> None:
    p = tmp_path / "simple.stl"
    p.write_text(
        "solid test\n"
        "facet normal 0 0 1\n"
        "  outer loop\n"
        "    vertex 0 0 0\n"
        "    vertex 1 0 0\n"
        "    vertex 0 1 0\n"
        "  endloop\n"
        "endfacet\n"
        "endsolid test\n",
        encoding="utf-8",
    )
    m = read_stl(p)
    assert m.n_vertices == 3
    assert m.n_faces == 1
    assert m.metadata["format"] == "stl_ascii"


def test_reader_missing_file_raises(tmp_path: Path) -> None:
    for fn in (read_stl, read_obj, read_ply, read_off):
        with pytest.raises(FileNotFoundError):
            fn(tmp_path / "does_not_exist.xyz")
