# TetWild-lite 포팅 계획 — native_tet MVP → Production

작성일: 2026-04-24 (v0.4 beta104 시작점)

## 배경

`core/generator/native_tet/mesher.py` (221 줄) 은 scipy.Delaunay + centroid
inside-test 기반 MVP. TetWild / fTetWild 의 핵심 알고리즘 (envelope 보존,
iterative local operations, feature preservation) 이 없어 복잡 형상에서
품질 실망 사례 발생.

사용자 방향: **"외부 엔진 부활 (참고/폴백용) + 우리 native_tet 을 fTetWild 수준으로
병행 고도화"**. 목표는 2~3 주 내 production-grade native_tet (OSS MPL-2.0 fTetWild
를 참고해 알고리즘 구조를 포팅).

## 라이선스 고지 (선행)

fTetWild (Yixin Hu et al. 2020, `https://github.com/wildmeshing/fTetWild`) 는
**MPL-2.0** 라이선스. AutoTessell 은 사용자 코드베이스의 기존 라이선스를
따르며, fTetWild 로부터 포팅한 모든 파일에는:

1. 파일 상단 헤더에 `Original: fTetWild by Yixin Hu et al., MPL-2.0, 2020` 명시.
2. 포팅된 자료 유지 — 알고리즘적 재구현 (Python) 이 법적으로 도출물에 해당.
3. MPL-2.0 per-file copyleft 의무 준수 (수정 시 변경 사항 공개).

C++ 원본을 기계적으로 변환하지 않고 **논문 + 헤더 구조 참조 + Python 재구현**
원칙. 알고리즘 단계별 reference 는 paper "Fast Tetrahedral Meshing in the
Wild" (2020) 으로 연결.

## Phase A (Week 1) — "Looks Less Weird"

**목표**: 사용자 체감 품질 즉시 개선. 220 → ~800 LoC.

### A1. Surface triangle 강제 보존 (Constrained Delaunay 대체)

- scipy.Delaunay 결과에서 입력 triangle 이 tet facet 으로 나타나지 않는 경우
  edge/face recovery 수행. TetWild 의 "Insertion" 단계 (§3.2 of paper).
- 구현: 입력 triangle 의 세 vertex 가 tet 의 한 face 를 이루지 않으면 해당
  영역에 1-4 split 으로 tet subdivide.

파일: `core/generator/native_tet/insertion.py` (신규, 200 줄).

### A2. Boundary sliver 예외 처리

- 현재 `q < 0.05` 일괄 drop → boundary tet 손실로 구멍 발생.
- 새 로직: boundary tet (≥1 vertex 가 surface) 는 q_thresh 낮게 (0.01),
  interior 는 0.05 유지. Alternative: sliver 는 drop 대신 edge flip.

파일: `core/generator/native_tet/filter.py` (신규, 50 줄).

### A3. Feature edge detection + 고정

- dihedral angle > 120° 인 edge 를 feature 로 감지.
- 해당 edge 의 vertex 는 smoothing / flip 에서 고정.

파일: `core/generator/native_tet/features.py` (신규, 80 줄).

**검증**: sphere + cube + bracket 3 개 STL 에서 시각적으로 "구멍 없음",
sharp corner 보존, checkMesh non-orthogonality < 70°.

## Phase B (Week 2) — "Decent Quality"

**목표**: 품질 지표가 fTetWild 대비 80% 수준. 800 → ~2000 LoC.

### B1. Laplacian + ODT smoothing

- Interior vertex 는 neighbor centroid 로 이동 (Laplacian).
- Boundary vertex 는 surface tangent 평면 내에서만 이동.
- ODT (Optimal Delaunay Triangulation) smoothing 은 옵션.

파일: `core/generator/native_tet/smooth.py` (신규, 200 줄).

### B2. Local operations 루프

fTetWild §3.3 의 4 종 local op 를 1 iteration 씩 적용:

1. **Edge split** — 긴 edge (> 4/3 × target) 분할.
2. **Edge collapse** — 짧은 edge (< 4/5 × target) 합치기.
3. **Edge flip** — Lawson 2-3 / 3-2 / 4-4 flip 으로 품질 개선.
4. **Vertex smooth** — B1 의 smoothing.

파일: `core/generator/native_tet/local_ops.py` (신규, 400 줄).

### B3. Adaptive target edge length

- 곡률 기반 edge length field: 곡률 높은 영역 짧게.
- `core/analyzer/topology.py::curvature_per_vertex` 이미 존재.

파일: 기존 `mesher.py` 수정, 60 줄 추가.

**검증**: bench_v04 standard quality 에서 평균 aspect ratio < 5, non-ortho
평균 < 30°, max < 70°.

## Phase C (Week 3) — "TetWild-lite 완성"

**목표**: 어려운 형상 (ultra-knot, extreme-gear) 에서 성공. ~2500 LoC.

### C1. Envelope-based surface preservation

- fTetWild 의 핵심 아이디어: 입력 surface 의 ε-envelope 내에 최종 tet
  boundary 가 있도록 iterative projection.
- 각 surface vertex 마다 ε 거리 내 sphere 유지.
- Rejection strategy: operation 후 boundary 가 envelope 을 벗어나면 reject.

파일: `core/generator/native_tet/envelope.py` (신규, 300 줄).

### C2. AABB tree + winding number 최적화

- 현재 `inside_winding_number` 는 O(F) per query. AABB tree 로 가속
  (scipy.cKDTree 혹은 libigl 의 fast winding number).
- envelope 내 projection 도 AABB 쿼리 필요.

파일: `core/utils/aabb.py` (신규, 200 줄).

### C3. Quality stop criterion

- iteration 중 max quality 개선이 < threshold 면 종료.
- fTetWild stop_quality (기본 10) 모방.

## 파일 구조 (최종)

```
core/generator/native_tet/
├── __init__.py
├── mesher.py          # 진입점 (기존, 축소됨)
├── harness.py         # quality/retry 기존
├── insertion.py       # Phase A1 — CDT / triangle recovery
├── filter.py          # Phase A2 — boundary-aware sliver filter
├── features.py        # Phase A3 — sharp edge detection & lock
├── smooth.py          # Phase B1 — Laplacian + ODT
├── local_ops.py       # Phase B2 — split/collapse/flip
└── envelope.py        # Phase C1 — surface envelope preservation
```

## 테스트 전략

`tests/test_native_tet_quality.py` 신규:
- Phase A 완료 시: sphere/cube/bracket watertight + feature preservation.
- Phase B: 평균 aspect < 5, non-ortho < 30°.
- Phase C: ultra-knot 성공률 > 80%.

`tests/stl/bench_v04_matrix.py` 에 native_tet 단독 30 조합 벤치 자동화.

## Weekly milestone

| Week | 커밋 태그 | Definition of Done |
|------|-----------|--------------------|
| 1 (Phase A) | `v0.4.0-beta110` | sphere visual "구멍 없음", ultra-knot crash 없음. |
| 2 (Phase B) | `v0.4.0-beta120` | bench_v04 standard 성공률 +20%p. |
| 3 (Phase C) | `v0.4.0-beta130` | native_tet 이 strategist 의 standard/fine 기본. |

## 병행 트랙: 외부 엔진 "참고용" 유지

beta104 에서 ENGINE_GROUPS 에 참고용 카테고리 복귀. native_tet Phase C 완료
시점에 "참고용" 꼬리표 제거 검토 (여전히 독립 검증 가치 있어 유지 가능).
