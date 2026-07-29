---
type: engine
status: active
updated: 2026-07-26
stability: working-tree
source_paths: [core/generator/native_hex/mesher.py, core/generator/native_hex/octree.py, core/generator/native_hex/snap.py, core/generator/native_hex/quality.py, core/generator/native_hex/metrics.py, core/generator/native_hex/match_repair.py]
tags: [native-hex, octree, hex-dominant]
---

# Native Hex

`generate_native_hex()`에는 두 생성 경로가 있다.

- 입력 영역으로 필터링한 uniform Cartesian grid
- level balancing, transition topology, snap, generic polyhedral cell-face 출력을 갖는 adaptive octree

Standard/fine의 중심은 adaptive path다. BL cell budget을 추정하고 octree cell을 만든 뒤 optional iterative snap과 guarded wall-fit projection을 수행한다. Boundary vertex는 incident cell의 orientation/volume 검사를 통과할 때만 source surface 쪽으로 움직인다. Full projection이 실패하면 backtracking으로 가장 큰 안전 이동을 찾는다. 후속 pass는 boundary를 고정하고 wall-normal thickness가 무너진 cell의 interior point만 완화한다.

## 품질·repair lane

- `quality.py`: hex quality, non-orthogonality, skew, grade
- `validate_hex_cell_volumes()`: orientation 수정과 degenerate 거부
- post-snap smooth와 feature-edge snap: quality-revert guard
- `match_diagnostic.py`: mesh 수정 없는 transition matching 감사
- `match_repair.py`: per-candidate/whole-pass rollback이 있는 opt-in HEX-MATCH-2 pillow repair

## 정직한 cell census

Phase-0 metric은 실제 cell type과 volume fraction, ScoreCHE/hex cluster, Knupp-style beta margin을 보고한다. 엔진 이름은 all-hex 증거가 아니다. Adaptive path에 일반 pairing/certification 단계가 없으므로 all-hex 주장은 실제 topology 측정으로만 해야 한다.

Cube solid invariant가 canonical all-hex 기준선이다. Curved-wall 작업은 positive volume을 유지하며 cylinder wall deviation을 줄였다. Roadmap은 standard skew 약 2.84와 fine 약 3.21을 구분한다. ECR/HexOpt와 coherent-sheet 가설은 보편 메커니즘으로 기각됐고, 연구는 transition matching과 feature provenance로 이동했다.
