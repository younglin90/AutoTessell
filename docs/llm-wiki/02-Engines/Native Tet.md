---
type: engine
status: active
updated: 2026-07-26
stability: working-tree
source_paths: [core/generator/native_tet/mesher.py, core/generator/native_tet/harness.py, core/generator/native_tet/quality.py, core/generator/native_tet/boundary_invariant.py, docs/references/literature/native_tet/evidence_matrix.md]
tags: [native-tet, cdt, tetrahedral-meshing]
---

# Native Tet

Native tet은 가장 성숙하면서 실험 코드가 가장 많은 엔진이다. `generate_native_tet()`은 triangular surface를 받아 tet 후보를 생성·필터링하고, 선택적 recovery와 quality pass를 수행한 뒤 표면/볼륨 계약을 검증해 `polyMesh`를 쓴다. 결과에는 파일뿐 아니라 points/tets array와 품질·provenance 진단도 들어간다. `run_native_tet_harness()`가 이 과정을 bounded generator/evaluator loop로 감싼다.

## 메커니즘 계층

| 계층 | 주요 모듈 | 책임 |
|---|---|---|
| 입력·영역 | `input_check.py`, `boundary_clip.py`, `boolean_merge.py` | surface 검증/수리, inside/CSG 분류 |
| 초기 tessellation | `mesher.py`, `chunked.py`, `parallel.py`, `bowyer_watson.py`, `offset_ring.py` | seed와 초기 tet 구성 |
| constraint recovery | `cdt_recovery.py`, `face_recovery.py`, `edge_recovery.py`, `edge_flip_recovery.py`, `bsp_insert.py` | surface edge/face와 constraint 회복 |
| 국소 topology | `local_ops.py`, `flip.py`, `stellar.py`, `mfrc.py`, `klingner_full_sweep.py` | split/collapse/flip/Steiner/cavity 변환 |
| 좌표 최적화 | `smooth.py`, `laplacian.py`, `amips.py`, `flow2.py`, `qopt.py`, `cvt3d.py` | interior 또는 guarded boundary relocation |
| metric·품질 | `adaptive.py`, `anisotropic.py`, `quality.py`, `validate.py` | sizing, shape metric, 종료, orientation, sliver |
| fidelity·불변식 | `envelope.py`, `hausdorff.py`, `boundary_invariant.py`, `rescue_gate.py`, `near_wall.py` | 표면 보존과 unsafe transaction 거부 |
| 특수 경로 | extrusion/radial/torus wedge, rectilinear CSG, fTetWild/PyTetWild worker | 제한된 형상 또는 참조 경로 |

## 파이프라인 형태

현재 working-tree mesher는 한 교과서 알고리즘이 아니라 긴 staged program이다. Initial Delaunay, filter/remap, 선택적 Phase-B local op, AMIPS/metric, BSP insertion, CVT, Stellar queue와 여러 guarded experimental pass, Klingner sweep, final polish, validation, writer가 이어진다. 많은 기능은 `AUTO_TESSELL_*` flag로 제어된다.

`boundary_invariant.py`는 단계 전후 boundary face key와 총면적을 비교한다. Collapse, flip, Stellar, BSP, CVT, metric/GAP에서 반복된 두 버그 계열 때문에 도입됐다. 첫째는 unsafe local reconstruction이 내부면을 boundary로 노출하는 경우, 둘째는 vertex 추가/remap 뒤 stale boundary lock이 새 boundary vertex를 움직이는 경우다.

## 결과와 연구 해석

`NativeTetResult`에는 cell/point, array, quality snapshot, warning, CDT edge/face ratio, plane coverage, relative Hausdorff, input self-intersection, grade, integrity-suspect가 있다. Harness는 negative volume, cell count, non-ortho, skew를 평가하고 bounded attempt 중 최선을 보관한다.

Evidence matrix는 현재 혼합 루프를 완전한 fTetWild나 protected-CDT라고 부르는 것을 기각한다. 목표 구조는 valid PLC용 protected CDT와 triangle soup용 epsilon-tolerant Wild를 분리하고 predicate·adjacency·quality·transaction guard를 공유하는 것이다. FSL wedge, FLOW-2, recovery, near-wall quality, exact-envelope가 연구 중이며 병렬화는 마지막이다.
