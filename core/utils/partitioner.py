"""PyMetis 기반 메쉬 파티셔닝 유틸리티.

pymetis import 실패 시 Scotch/Simple fallback을 사용한다.
"""

from __future__ import annotations

from pathlib import Path

from core.utils.logging import get_logger

log = get_logger(__name__)

# pymetis import 시도
try:
    import pymetis as _pymetis

    _PYMETIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _pymetis = None  # type: ignore[assignment]
    _PYMETIS_AVAILABLE = False


class MeshPartitioner:
    """PyMetis를 사용한 메쉬 파티셔닝.

    pymetis가 설치되지 않은 경우 단순 순환 할당(simple) fallback을 사용한다.
    """

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def partition(
        self,
        adjacency_list: list[list[int]],
        n_parts: int,
    ) -> list[int]:
        """인접 그래프를 n_parts 개의 파티션으로 분할한다.

        Parameters
        ----------
        adjacency_list:
            셀/노드별 인접 인덱스 리스트. 예: [[1, 2], [0, 2], [0, 1]]
        n_parts:
            분할할 파티션 수.

        Returns
        -------
        list[int]
            각 노드가 속하는 파티션 번호 목록.
        """
        n_nodes = len(adjacency_list)
        if n_nodes == 0:
            return []
        if n_parts <= 1:
            return [0] * n_nodes

        if _PYMETIS_AVAILABLE and _pymetis is not None:
            try:
                _cuts, membership = _pymetis.part_graph(n_parts, adjacency=adjacency_list)
                result = list(membership)
                log.info(
                    "pymetis_partition_done",
                    n_nodes=n_nodes,
                    n_parts=n_parts,
                    cuts=_cuts,
                )
                return result
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "pymetis_partition_failed_fallback",
                    error=str(exc),
                    n_parts=n_parts,
                )

        # Fallback: 단순 순환 할당
        return self._simple_partition(n_nodes, n_parts)

    def partition_polymesh(
        self,
        poly_mesh_dir: Path | str,
        n_parts: int,
        output_dir: Path | str | None = None,
    ) -> Path:
        """OpenFOAM polyMesh → adjacency → pymetis → decomposeParDict 생성.

        Parameters
        ----------
        poly_mesh_dir:
            OpenFOAM polyMesh 디렉터리 (owner, neighbour 파일 포함).
        n_parts:
            분할 수.
        output_dir:
            decomposeParDict를 저장할 system 디렉터리.
            None이면 poly_mesh_dir의 상위 case 디렉터리의 system/에 저장.

        Returns
        -------
        Path
            생성된 decomposeParDict 파일 경로.
        """
        poly_mesh_dir = Path(poly_mesh_dir)

        # owner/neighbour 파일로 adjacency 구성
        adjacency = self._build_adjacency_from_polymesh(poly_mesh_dir)

        if adjacency:
            membership = self.partition(adjacency, n_parts)
            method = "metis" if _PYMETIS_AVAILABLE else "scotch"
        else:
            membership = []
            method = "scotch"

        # decomposeParDict 경로 결정
        if output_dir is None:
            # poly_mesh_dir = .../constant/polyMesh → case = .../..
            case_dir = poly_mesh_dir.parent.parent
            system_dir = case_dir / "system"
        else:
            system_dir = Path(output_dir)

        system_dir.mkdir(parents=True, exist_ok=True)
        decompose_path = system_dir / "decomposeParDict"

        self._write_decompose_par_dict(
            decompose_path,
            n_parts=n_parts,
            method=method,
            membership=membership,
        )

        log.info(
            "decompose_par_dict_written",
            path=str(decompose_path),
            n_parts=n_parts,
            method=method,
            n_cells=len(membership),
        )
        return decompose_path

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _simple_partition(n_nodes: int, n_parts: int) -> list[int]:
        """단순 순환 할당 fallback."""
        return [i % n_parts for i in range(n_nodes)]

    @staticmethod
    def _build_adjacency_from_polymesh(
        poly_mesh_dir: Path,
    ) -> list[list[int]]:
        """owner/neighbour 파일에서 셀 인접 리스트를 구성한다.

        파일이 없거나 파싱에 실패하면 빈 리스트를 반환한다.
        """
        owner_file = poly_mesh_dir / "owner"
        neighbour_file = poly_mesh_dir / "neighbour"

        if not owner_file.exists() or not neighbour_file.exists():
            log.warning(
                "polymesh_owner_neighbour_missing",
                poly_mesh_dir=str(poly_mesh_dir),
            )
            return []

        try:
            owners = _parse_foam_label_list(owner_file)
            neighbours = _parse_foam_label_list(neighbour_file)
        except Exception as exc:  # noqa: BLE001
            log.warning("polymesh_parse_failed", error=str(exc))
            return []

        if not owners:
            return []

        all_cell_ids = owners + neighbours
        n_cells = max(all_cell_ids) + 1 if all_cell_ids else 0
        adjacency: list[set[int]] = [set() for _ in range(n_cells)]

        for face_idx, (owner, neighbour) in enumerate(zip(owners, neighbours)):
            adjacency[owner].add(neighbour)
            adjacency[neighbour].add(owner)

        return [sorted(adj) for adj in adjacency]

    @staticmethod
    def _write_decompose_par_dict(
        path: Path,
        n_parts: int,
        method: str,
        membership: list[int],
    ) -> None:
        """decomposeParDict 파일을 작성한다."""
        header = (
            "FoamFile\n"
            "{\n"
            "    version     2.0;\n"
            "    format      ascii;\n"
            "    class       dictionary;\n"
            "    object      decomposeParDict;\n"
            "}\n"
            "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n"
        )
        footer = "\n// ************************************************************************* //\n"

        content = header
        content += f"numberOfSubdomains {n_parts};\n\n"
        content += f"method          {method};\n\n"

        if method == "metis" and membership:
            content += (
                "metisCoeffs\n"
                "{\n"
                "    processorWeights ( "
                + " ".join(["1"] * n_parts)
                + " );\n"
                "}\n"
            )
        elif method == "scotch":
            content += "scotchCoeffs\n{\n}\n"
        else:
            content += "simpleCoeffs\n{\n    n ( 2 2 1 );\n    delta 0.001;\n}\n"

        content += footer
        path.write_text(content)


# ---------------------------------------------------------------------------
# 내부 파서
# ---------------------------------------------------------------------------


def _parse_foam_label_list(path: Path) -> list[int]:
    """OpenFOAM ASCII 레이블 리스트 파일을 파싱한다.

    FoamFile 헤더와 주석을 건너뛰고 숫자만 추출한다.
    """
    text = path.read_text()
    lines = text.splitlines()

    # FoamFile 헤더 건너뛰기
    in_header = False
    data_lines: list[str] = []
    brace_depth = 0
    past_header = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if "FoamFile" in stripped:
            in_header = True
            continue
        if in_header:
            brace_depth += stripped.count("{") - stripped.count("}")
            if brace_depth <= 0:
                in_header = False
                past_header = True
            continue
        if past_header:
            data_lines.append(stripped)

    # 숫자만 파싱: 첫 번째 숫자 = 항목 수, 이후 괄호 안 숫자들
    labels: list[int] = []
    inside = False
    for line in data_lines:
        if not line or line.startswith("//"):
            continue
        if line == "(":
            inside = True
            continue
        if line == ")":
            inside = False
            continue
        if inside:
            try:
                labels.append(int(line))
            except ValueError:
                pass

    return labels
