# Siemens CCMIO format — reverse-engineered spec (BETA2601)

## Source

공개 자료 기반:
- Siemens (구 CD-Adapco) **libccmio** 공식 API 헤더 — public release.
- StarCCM+ User Guide "Importing/Exporting CCM Files" 섹션.
- HDF (Hierarchical Data Format) 컨테이너 spec.

## Container

| 항목 | Siemens 원본 | 본 구현 |
|------|-------------|---------|
| Container | HDF 1.4 (Adapco custom) | HDF5 (표준) |
| 파일 확장자 | `.ccm`, `.ccmg`, `.ccmp` | `.ccm` |
| 압축 | varies | gzip level 4 |
| Endianness | little-endian | platform-native |

원본 HDF 1.4 와 표준 HDF5 는 컨테이너 다름 — StarCCM+ 신버전이 HDF5 호환 모드일 때만 import 가능.

## File Hierarchy

```
/                                     (root)
├── @CreatedBy                        ("AutoTessell ccmio_writer beta2601")
├── @CCMIOVersion                     (int32: 2)
├── @FileFormat                       ("CCMIO-HDF5")
├── State/                            (calculations)
│   └── Default/                     (default state)
├── Meshes/                           (mesh registry)
│   └── Mesh-N/                      (N = 0, 1, ...)
│       ├── Vertices/
│       │   ├── MapId                 (int32 (Nv,), 1-based vertex ID)
│       │   └── Coordinates           (float64 (Nv, 3))
│       ├── Cells/
│       │   ├── MapId                 (int32 (Nc,), 1-based cell ID)
│       │   └── CellType              (int32 (Nc,))
│       ├── InternalFaces/            (cell↔cell)
│       │   ├── MapId                 (int32 (Nf_int,))
│       │   ├── Cells                 (int32 (Nf_int, 2): owner, nbr)
│       │   ├── FaceVertices          (int32, packed CSR)
│       │   └── FaceVerticesOffset    (int32 (Nf_int+1,))
│       └── BoundaryFaces-K/          (K = patch index)
│           ├── @BoundaryRegion       (int32 region ID)
│           ├── @Name                 (string)
│           ├── @Type                 ("wall" | "patch" | "symmetry" | ...)
│           ├── MapId                 (int32 (Nf_b,))
│           ├── Cells                 (int32 (Nf_b,) — owner only)
│           ├── FaceVertices          (int32, packed CSR)
│           └── FaceVerticesOffset    (int32 (Nf_b+1,))
└── ProcessorSet/                     (parallel decomposition)
    ├── @NumberOfProcessors           (int32)
    └── Processor-N/                  (N = 0..nProcs-1)
```

## CellType codes

CCMIO 관습 (libccmio `CCMIOEntity` enum 기반):

| Code | Type | Faces |
|------|------|-------|
| 0 | polyhedral | 임의 |
| 4 | tet | 4 tri |
| 5 | pyramid | 1 quad + 4 tri |
| 6 | wedge / prism | 2 tri + 3 quad |
| 8 | hex | 6 quad |

## ID convention

- **MapId** 는 **1-based** (CCMIO 관습 — 0 은 reserved).
- 본 라이브러리는 내부적으로 0-based numpy array 사용 → write 시 +1, read 시 -1.

## Variable-length face vertices (CSR)

Polyhedral mesh 는 face 마다 vertex 수가 다름 (3-N). HDF5 는 var-length 직접 지원 가능하지만 단순한 CSR 사용:

```
face k 의 vertices = FaceVertices[FaceVerticesOffset[k] : FaceVerticesOffset[k+1]]
```

Offset 배열 크기 = (Nf + 1).

## API

```python
from core.utils.ccmio_writer import write_ccmio, read_ccmio

# write
r = write_ccmio("path/to/polyMesh", "out.ccm", mesh_name="Mesh-0")
# r.success, r.n_vertices, r.n_cells, r.n_internal_faces, r.n_boundary_patches

# round-trip read
pm_dict = read_ccmio("out.ccm")
# pm_dict = {points, faces, owner, neighbour, boundary}
```

또는 `mesh_exporter_starccm.write_starccm` 통합 진입점:

```python
from core.utils.mesh_exporter_starccm import write_starccm
write_starccm("path/to/polyMesh", "out.ccm", fmt="ccmio")
```

## 한계 / 검증 안 된 부분

| 항목 | 상태 |
|------|------|
| HDF5 vs HDF 1.4 호환성 | Siemens 원본 HDF 1.4 — 신버전 StarCCM+ 만 가능성 있음 |
| 실 StarCCM+ import | ❌ 검증 안 됨 (Siemens 라이센스 필요) |
| Solution data (state-N) | ❌ 미구현 (mesh-only) |
| Composite cell (polyhedral subgroups) | ✅ CellType=0 으로 통합 |
| 평행 (Processor-N partition data) | 🟡 single-CPU placeholder 만 |
| Solver-specific properties | ❌ 미구현 |

## 향후 작업

1. **CGNS 호환 layer** — CGNS 는 CCMIO 와 같은 hierarchical CFD format. 두 format 간 변환 가능성 검증.
2. **Real HDF 1.4 mode** — Siemens 원본 컨테이너 정확 매칭. h5py 가 HDF 1.4 미지원 → libhdf4 또는 SDS 필요.
3. **Solution data writer** — `/State/state-N` 에 cell-centered values (pressure, velocity 등) 저장.
4. **실 StarCCM+ import 검증** — Siemens 라이센스 확보 시 round-trip 테스트.

## 회귀 테스트

`tests/test_native_ai.py::test_starccm_ccmio_hdf5_round_trip`:
- 8 vertex hex cube + 1 cell + 1 walls patch.
- write → HDF5 inspect → read back.
- coordinates / boundary name / type 보존 검증.
