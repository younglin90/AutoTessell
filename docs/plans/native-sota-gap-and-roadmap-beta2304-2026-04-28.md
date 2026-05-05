# 상용 SOTA 미구현 기능 정리 + Native 고도화 로드맵

**기준:** beta2304, 2026-04-28  
**목표:** 산업 표준 도달( tet A≥12/20, hex A≥18/20, poly A≥18/20, BL≥28/32 )

## 1) 개요

beta2231 → beta2304 간의 GUI/CLI parity 갭(교차 엔진 fallback, `max_cells`, auto_retry, Hausdorff 4-path)과 wiring 갭은 메웠다.  
남은 격차는 상용 SOTA 대비 알고리즘 핵심(geometry evolution, topology surgery, solver compatibility) 중심이다.

B+C 정책 재확인:
- native self-구현 품질이 grade A 미만일 때만 외부 fallback 허용.
- 새 의존성 추가 금지, P4.1 GPU 제외.
- `--auto-retry` off 기본값, 실패는 사용자 재시도 판단.

---

## 2) 미구현/미성숙 기능 (영역별)

### A. tet

| 항목 | 상용 SOTA | 현재 native_tet | 격차 영향 |
|---|---|---|---|
| envelope-bounded vertex relocation (fTetWild §3.5) | 항상 활성 | RRR3 단조 가드(-0.005)로 reject 경향 | grade A 0/20의 주원인 |
| edge collapse with envelope check | surface vertex ε 내 collapse | surface vertex lock | sliver 잔존 |
| input quadric-error decimation | 메쉬 단순화 후 tet | isotropic_remesh only | 입력 face 폭주 시 슬리버 증가 |
| Stellar 4-op queue | swap/split/contract/insert 동시 | collapse only(기록됨) | 품질 향상 포텐셜 미활용 |
| anisotropic metric tensor (Hessian) | 곡률 정렬 | beta500 SPD 부분 적용 | 곡률 영역 sliver 잔존 |
| BSP balanced cell split | 균등 BSP | phase F one-shot | recovery 누락 |
| volumetric Lloyd CVT | 표준 L2/3 | RRR1~3 표면 Lp only | 내부 anisotropy 대응 약함 |
| point-projection adaptive resampling | 자동 | 미구현 | feature edge 보존 저하 |
| multithreaded Delaunay | CGAL parallel | scipy QHull single thread | 대형 메쉬 성능 한계 |

### B. hex

| 항목 | 상용 SOTA | 현재 native_hex | 격차 영향 |
|---|---|---|---|
| small-bbox auto-escalate | snappy 자동 셀크기 축소 | `"inside hex 0"` fail 다수 | hard/medium tier 3 실패 |
| adaptive octree balancing (2:1 rule) | 강제 | beta92 N-level만 | skewness 잔존 |
| feature edge snap (per-edge weight) | 표준 | corner-only preserve_features | sharp edge 흐트러짐 |
| buffer layer between refinement levels | 자동 | 미구현 | 경계 jagged |
| Cartesian → all-hex templating | 옵션 | 미구현 | hex-only 한계 |
| Cooper/submapping multi-block | Cubit | 미구현 | 복잡 형상 메쉬 제약 |
| boundary-fitted hex prism stacking | Pointwise T-Rex | tet BL 만 | hex BL 분리 |

### C. poly

| 항목 | 상용 SOTA | 현재 native_poly | 격차 영향 |
|---|---|---|---|
| anisotropic CVT (curvature-aligned) | StarCCM+ | 미구현 | 곡률 경계 cell 열화 |
| L∞ Voronoi (geogram) | 옵션 | scipy Voronoi (L2) | 특이형상에서 경계 품질 저하 |
| self-intersect pre-repair | 표준 | 부분 (UUU5) | extreme 케이스 실패 |
| boundary recovery | 표준 | beta2294 boundary snap | boundary snap fail 잔존 |
| dual mesh from BCC tet | 옵션 | tet dual direct | poly dual 품질 편차 |
| periodic/cyclic poly | Fluent | 미구현 | turbomachinery 미지원 |
| conformal poly-prism transition | StarCCM+ | beta poly_bl_transition 부분 | BL→bulk 전이 품질 저하 |

### D. BL

| 항목 | 상용 SOTA | 현재 native_bl | 격차 영향 |
|---|---|---|---|
| per-vertex Layer Count Reduction (LCR) | T-Rex | 미구현 | 좁은 간극 누적 오차 |
| anisotropic prism splitting | cfMesh | 미구현 | wall-normal 정밀도 저하 |
| dynamic collision-aware stop | 자동 | 일부(collision_safety) | 일부 구간에서 OK |
| near-wall refinement zoning | 표준 | refine_wall_layer 부분 | gradient 영역 취약 |
| multi-zone BL (patch별 layers) | 표준 | 부분(allowDiscontinuity) | 부분 미적용 |
| automatic feature angle detection | 자동 | manual feature_angle_deg | UX/튜닝 비용 |
| prism→tet 유지 | 표준 | tet_bl_subdivide OK | 통과 |

### E. 전처리/표면

| 항목 | 상용 SOTA | 현재 | 격차 영향 |
|---|---|---|---|
| AI surface gen (MeshAnything/MeshGPT) | optional | L3는 부분 | non-watertight 입력 처리 한계 |
| CAD direct meshing | Cubit/ANSA 급 | gmsh fallback | CAD 충실도 |
| feature edge auto extraction | 표준 | trimesh/부분 | sharp 보존 |
| curvature-aware surface remesh | 표준 | isotropic only | 곡률 영역 품질 저하 |
| non-manifold repair | 표준 | native_repair OK | 해당 없음 |
| self-intersect resolve(Boolean) | 표준 | UUU5 부분 | 복잡 형상 실패 |

### F. 솔버 호환/출력

| 항목 | 상용 SOTA | 현재 | 격차 영향 |
|---|---|---|---|
| CGNS HDF5 partition | 표준 | meshio 단일 | parallel CFD |
| Fluent native `.cas` partitioned | Fluent | meshio `.msh` | 직접 실행성 |
| StarCCM+ `.ccm` write | StarCCM+ | 미구현 | niche 사용자 이탈 |
| CFD++/Cobalt/SC-Tetra | 상용 | 미구현 | 특정 업계 니즈 미지원 |
| periodic/sliding interface | 범용 | 미구현 | 회전체 모델 미지원 |
| AMR/dynamic mesh | 일부 | 미구현 | unsteady 워크플로우 한계 |

### G. 인프라/UX

| 항목 | 상용 SOTA | 현재 | 격차 영향 |
|---|---|---|---|
| GPU 가속(CUDA/OpenCL) | 일부 상용 | 미구현 | 10~100배 성능 |
| distributed meshing(MPI) | 상용 | 미구현 | 1B+ cell 제약 |
| scripting macro | StarCCM+ JavaMacro | CLI/GUI only | 자동화 비용 |
| certified validation | NASA TMR/ERCOFTAC | 부분 | 규제산업 |
| enterprise support/SLA | 상용 | 오픈소스 | 고객 전환 장벽 |
| 3D 측정/probe 도구 | 모든 GUI | beta 일부 | 워크플로우 완결성 |

---

## 3) 우선순위 로드맵

### P1 (즉시 효과, 1사이클)

| ID | 항목 | 변경 파일 | 난이도 | 기대 효과 |
|---|---|---|---|---|
| P1.1 | hex small-bbox auto-escalate | `core/generator/native_hex/mesher.py` | 30줄 | hex A 16→19/20 |
| P1.2 | poly extreme self-intersect repair | `core/generator/native_poly/voronoi.py` | 60줄 | poly A +3~4/5 포인트 |
| P1.3 | RRR3 monotone guard 완화 | `core/generator/native_tet/mesher.py` | 10줄 | tet A 0→2~3/20 |

### P2 (단주, 1~3사이클)

| ID | 항목 | 변경 파일 | 난이도 | 기대 효과 |
|---|---|---|---|---|
| P2.1 | Stellar swap/split op 활성 | `core/generator/native_tet/stellar.py` | 120줄 | tet A 2~3→5~7/20 |
| P2.2 | edge collapse envelope-aware | `core/generator/native_tet/local_ops.py` | 80줄 | sliver 감소 |
| P2.3 | quadric-error pre-decimation | `core/preprocessor/native_remesh/decimate.py`(신규) | 150줄 | face 폭주 입력 안정성 |
| P2.4 | snappy 2:1 octree balance | `core/generator/native_hex/octree.py` | 80줄 | hex skewness 감소 |
| P2.5 | feature edge snap weight | `core/generator/native_hex/snap.py` | 80줄 | sharp edge 보존 |
| P2.6 | self-intersect Boolean resolve | `core/preprocessor/native_repair/self_intersect.py` | 120줄 | poly extreme/ tet 입력 강화 |

### P3 (알고리즘 재작성, multi-week)

| ID | 항목 | 변경 파일 | 난이도 | 기대 효과 |
|---|---|---|---|---|
| P3.1 | volumetric Lloyd CVT 3D | `core/generator/native_tet/cvt3d.py`(신규) | 300줄 | tet anisotropy 감소, A 12+ 도달 |
| P3.2 | curvature-aligned metric tensor | `core/generator/native_tet/metric.py`(신규) | 250줄 | curved boundary sliver 개선 |
| P3.3 | per-vertex LCR | `core/layers/native_bl_lcr.py`(신규) | 400줄 | BL gap 대응 |
| P3.4 | anisotropic prism splitting | `core/layers/native_bl_split.py`(신규) | 350줄 | wall-normal 해상도 개선 |
| P3.5 | multithreaded Delaunay | `core/generator/native_tet/parallel.py`(신규) | 200줄 | 100k+ cell 시간 1/4 |

### P4 (장기/전환점)

| ID | 항목 | 비고 |
|---|---|---|
| P4.1 | CUDA/OpenCL 커널 도입 | CLAUDE 정책 검토 후 별도 |
| P4.2 | Cubit Sculpt형 all-hex templating | `auto_tessell_core` 후보 |
| P4.3 | Fluent/ccm 직접 포맷 writer | reverse-engineer 기반 |
| P4.4 | distributed MPI meshing | mpi4py + 도메인 분할 |
| P4.5 | NASA TMR/ERCOFTAC 인증 | 조직적 검증 체계 필요 |

---

## 4) 추천 실행 순서 (multi-cycle)

### Cycle 1 (1일)
- P1.1, P1.2 적용
- `tests/stl/bench_difficulty_tiers.py`로 hex/poly OK rate 측정

### Cycle 2 (2~3일)
- P1.3 적용
- bench 효과 측정 후 다음 카드 결정

### Cycle 3~6 (1~2주)
- P2.1 ~ P2.6 순차 적용
- 각 카드 후 단기 회귀 및 난이도별 벤치 재측정

### Cycle 7~15 (3~6주)
- P3.1 ~ P3.5 순차 적용

### Cycle 16+ (장기)
- P4 전개

---

## 5) 종료 조건/게이트

| 영역 | 현재 | 목표 | 게이트 |
|---|---:|---:|---|
| tet grade A | 0/20 | ≥12/20 | fTetWild 평균 |
| hex grade A | 16/20 | ≥18/20 | snappy/cfMesh 대비 |
| poly grade A | 16/20 | ≥18/20 | Fluent/StarCCM+ 대비 |
| BL pass rate | 26/32 | ≥28/32 | cfMesh/T-Rex 기준 |
| Hausdorff(rel) | 측정만 | ≤0.01 (1%) | Pointwise 기본 |
| sphere STL runtime | 0.6s | ≤1.0s | 1~5s 상용 대비 유지 |

**중간 달성 가정:** P1+P2 완료 시 tet 8~10/20, hex 19/20, poly 18/20.

---

## 6) 즉시 반영할 critical path

- `core/generator/native_hex/mesher.py` (P1.1, P2.4)
- `core/generator/native_hex/octree.py` (P2.4)
- `core/generator/native_hex/snap.py` (P2.5)
- `core/generator/native_poly/voronoi.py` (P1.2)
- `core/generator/native_tet/mesher.py` (P1.3)
- `core/generator/native_tet/local_ops.py` (P2.2)
- `core/generator/native_tet/stellar.py` (`_apply_op_queue`, P2.1)
- `core/preprocessor/native_remesh/decimate.py`(신규, P2.3)
- `core/preprocessor/native_repair/self_intersect.py`(확장, P2.6)

중기 신규 모듈:
- `core/generator/native_tet/cvt3d.py`, `core/generator/native_tet/metric.py`,
  `core/generator/native_tet/parallel.py`,
- `core/layers/native_bl_lcr.py`, `core/layers/native_bl_split.py`

재사용 지점:
- `core/preprocessor/native_repair.__init__.py::run_native_repair`
- `core/generator/native_tet/amips.py::smooth_amips_analytic`
- `core/generator/_tier_native_common.py` 내 `_TIER_PARAM_KEYS`/`HARNESS_PARAMS`

---

## 7) 검증 절차 (각 P 카드 적용 후 필수)

```bash
timeout 60 python3 -m pytest tests/test_native_tet_amips.py tests/test_native_tet_chunked.py tests/test_native_tet_cdt_recovery.py tests/test_native_poly.py tests/test_native_hex.py tests/test_qt_app.py -q 2>&1 | tail -5

timeout 60 python3 -m pytest tests/test_qt_app.py tests/test_cli_flags_beta20_beta23.py tests/test_tier_layers_post_bl_phase2.py -q 2>&1 | tail -5

timeout 1500 python3 tests/stl/bench_difficulty_tiers.py 2>&1 | tee /tmp/bench_tier.log | tail -30

timeout 60 python3 -m pytest tests/test_native_bl.py -q 2>&1 | tail -5
```

각 카드 PR 템플릿 체크리스트:
1) 좁은 회귀 테스트 PASS  
2) bench에서 해당 영역 OK rate 향상 확인  
3) `CHANGELOG.md` 반영  
4) `memory/`에 요약 기록(패턴: `P4-C`류)

---

## 8) 운영 정책 (강제)

- 외부 의존 신규 추가 금지(현재 정책 유지), stdlib 기반 멀티스레드는 `concurrent.futures` 사용.
- bench/pytest threshold 값 변경 금지.
- `AVOID` 마커: `smooth_amips_analytic` → BSP 직후 호출.
- 한 PR당 최대한 1 파일 변경 + 200줄 내외를 목표(필요 시 파일 수는 분리).
