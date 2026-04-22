"""PyMetis 파티셔닝 유닛 테스트."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from core.utils.partitioner import MeshPartitioner


# ---------------------------------------------------------------------------
# 공용 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture()
def partitioner() -> MeshPartitioner:
    return MeshPartitioner()


@pytest.fixture()
def simple_adjacency() -> list[list[int]]:
    """간단한 6-노드 인접 그래프 (3x2 격자)."""
    #  0-1-2
    #  | | |
    #  3-4-5
    return [
        [1, 3],      # 0
        [0, 2, 4],   # 1
        [1, 5],      # 2
        [0, 4],      # 3
        [1, 3, 5],   # 4
        [2, 4],      # 5
    ]


# ---------------------------------------------------------------------------
# 테스트 1: 기본 파티셔닝 결과 형태 검증
# ---------------------------------------------------------------------------


def test_partition_returns_list_of_correct_length(
    partitioner: MeshPartitioner, simple_adjacency: list[list[int]]
) -> None:
    membership = partitioner.partition(simple_adjacency, n_parts=2)
    assert isinstance(membership, list)
    assert len(membership) == len(simple_adjacency)


# ---------------------------------------------------------------------------
# 테스트 2: 파티션 번호 범위 검증
# ---------------------------------------------------------------------------


def test_partition_membership_values_in_range(
    partitioner: MeshPartitioner, simple_adjacency: list[list[int]]
) -> None:
    n_parts = 2
    membership = partitioner.partition(simple_adjacency, n_parts=n_parts)
    assert all(0 <= m < n_parts for m in membership), (
        f"파티션 번호가 [0, {n_parts}) 범위를 벗어남: {membership}"
    )


# ---------------------------------------------------------------------------
# 테스트 3: n_parts=2/4/8 파티션 수 검증
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_parts", [2, 4, 8])
def test_partition_nparts(
    partitioner: MeshPartitioner, simple_adjacency: list[list[int]], n_parts: int
) -> None:
    # 노드가 6개이므로 n_parts=8이면 일부 파티션은 비어있어도 됨
    membership = partitioner.partition(simple_adjacency, n_parts=n_parts)
    assert len(membership) == len(simple_adjacency)
    assert all(0 <= m < n_parts for m in membership)


# ---------------------------------------------------------------------------
# 테스트 4: pymetis 미설치 시 fallback 동작
# ---------------------------------------------------------------------------


def test_partition_fallback_when_pymetis_unavailable(
    simple_adjacency: list[list[int]],
) -> None:
    """pymetis 미설치 환경 시뮬레이션: simple fallback이 올바르게 동작해야 한다."""
    with patch("core.utils.partitioner._PYMETIS_AVAILABLE", False):
        partitioner = MeshPartitioner()
        membership = partitioner.partition(simple_adjacency, n_parts=2)
    assert isinstance(membership, list)
    assert len(membership) == len(simple_adjacency)
    # simple fallback: 순환 할당이므로 0/1 반복
    assert all(m in (0, 1) for m in membership)


# ---------------------------------------------------------------------------
# 테스트 5: decomposeParDict 파일 생성 검증
# ---------------------------------------------------------------------------


def test_partition_polymesh_creates_decompose_par_dict(
    tmp_path: Path,
    partitioner: MeshPartitioner,
) -> None:
    """polyMesh owner/neighbour 파일 없는 경우에도 decomposeParDict가 생성되어야 한다."""
    poly_mesh_dir = tmp_path / "constant" / "polyMesh"
    poly_mesh_dir.mkdir(parents=True)
    system_dir = tmp_path / "system"
    system_dir.mkdir()

    result_path = partitioner.partition_polymesh(
        poly_mesh_dir=poly_mesh_dir,
        n_parts=4,
        output_dir=system_dir,
    )

    assert result_path.exists()
    assert result_path.name == "decomposeParDict"
    content = result_path.read_text()
    assert "numberOfSubdomains" in content
    assert "4" in content


# ---------------------------------------------------------------------------
# 테스트 6: decomposeParDict 내용 검증 (owner/neighbour 파일 포함)
# ---------------------------------------------------------------------------


def test_partition_polymesh_with_owner_neighbour(
    tmp_path: Path,
    partitioner: MeshPartitioner,
) -> None:
    """owner/neighbour 파일을 파싱하여 adjacency를 구성하고 파티셔닝해야 한다.

    간단한 4-셀 메쉬를 시뮬레이션한다:
      셀 0-1, 1-2, 2-3 이 연결된 선형 메쉬
    """
    poly_mesh_dir = tmp_path / "constant" / "polyMesh"
    poly_mesh_dir.mkdir(parents=True)
    system_dir = tmp_path / "system"
    system_dir.mkdir()

    # owner/neighbour 파일 작성
    # 3개 내부 face: face0(셀0-1), face1(셀1-2), face2(셀2-3)
    _write_foam_label_list(poly_mesh_dir / "owner", [0, 1, 2])
    _write_foam_label_list(poly_mesh_dir / "neighbour", [1, 2, 3])

    result_path = partitioner.partition_polymesh(
        poly_mesh_dir=poly_mesh_dir,
        n_parts=2,
        output_dir=system_dir,
    )

    assert result_path.exists()
    content = result_path.read_text()
    assert "numberOfSubdomains" in content
    assert "2" in content
    # metis 또는 scotch 방법이 포함되어야 함
    assert "method" in content


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _write_foam_label_list(path: Path, labels: list[int]) -> None:
    """테스트용 간단한 OpenFOAM 레이블 리스트 파일 작성."""
    n = len(labels)
    content = textwrap.dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       labelList;
            object      {path.name};
        }}
        // * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

        {n}
        (
        """)
    for label in labels:
        content += f"{label}\n"
    content += ")\n"
    path.write_text(content)


# ---------------------------------------------------------------------------
# v0.4.0-beta21 추가 — 엣지 케이스 커버리지
# ---------------------------------------------------------------------------


def test_partition_empty_adjacency_returns_empty_list(
    partitioner: MeshPartitioner,
) -> None:
    """빈 그래프 입력 시 빈 리스트 반환."""
    assert partitioner.partition([], n_parts=4) == []


def test_partition_nparts_one_returns_all_zero(
    partitioner: MeshPartitioner, simple_adjacency: list[list[int]],
) -> None:
    """n_parts=1 은 모든 노드를 partition 0 으로 묶어야 함."""
    result = partitioner.partition(simple_adjacency, n_parts=1)
    assert result == [0] * len(simple_adjacency)


def test_partition_large_ring_graph_balanced(
    partitioner: MeshPartitioner,
) -> None:
    """100-node ring 그래프를 4 파티션 — 각 파티션에 노드가 할당됨 (non-empty)."""
    n = 100
    adj = [[(i - 1) % n, (i + 1) % n] for i in range(n)]
    result = partitioner.partition(adj, n_parts=4)
    assert len(result) == n
    sizes = [result.count(p) for p in range(4)]
    assert all(s > 0 for s in sizes), f"파티션 비어있음: {sizes}"


def test_simple_fallback_is_cyclic_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pymetis 없을 때 _simple_partition 이 i%n_parts cyclic 할당."""
    import core.utils.partitioner as pt  # noqa: PLC0415

    monkeypatch.setattr(pt, "_PYMETIS_AVAILABLE", False)
    monkeypatch.setattr(pt, "_pymetis", None)

    adj = [[1], [0, 2], [1, 3], [2, 4], [3]]
    result = MeshPartitioner().partition(adj, n_parts=3)
    assert result == [0, 1, 2, 0, 1]
