# Native Engine 고도화 자율 실행 큐 (2026-07-23)

최종 목표: **Surface Quad / tri-dominant → Volume Tet → Volume Hex → Volume Poly** 순서로 엔진을 분리해 개선하고, 각 엔진은 독립 벤치·계약·실패 보고를 남긴다.

## 0) 공통 사실

- 현재 문헌 상태: `native_quad`, `native_tet`, `native_hex`, `native_poly`의 핵심 논문은 `FULL_READ` 또는 사용자 PDF로 선행 정리됨.
- 접근 불가 논문 없음 (해당 배치 기준).
- 다음 출력 규약이 공통화되어야 함:
  1. 입력 표면 계약 ID(`PLC_EXACT`, `SOUP_EPSILON`, `LABELED_SURFACE`, `FACE_FIELD`)와 충족 조건
  2. 계약 위반 시 `fallback/unsupported` 사유를 명시
  3. 엔진별 정확한 cell type census(hexa/tet/wedge/pyramid/poly 등)와 실패율
  4. 표면 적합도, 위상 일관성, 정량 품질(체적/스케일/곡률), 결정성, 재현성 기록

### 공통 출력 동기화 상태 (2026-07-23)

- `DONE`: native_tet 매트릭스 벤치 출력 스키마(`scripts/bench_native_tet_matrix.py`)에 `route`, `contract`, `fallback_reason`, `contract_details`, `cell_census` 동기화 반영.
- `DONE`: `tests/stl/verify_autoresearch_mesh_matrix.py`에 동일 메타 동기화 반영 (`_extract_tier_attempt_from_log` 활용).
- `DONE`: `core/preprocessor/pipeline.py`의 `native_quad_dominant` L2 단계 step_record.params에 `route/contract/fallback_reason` 추가.
- `RUNNING`: native_hex, native_poly의 벤치 리포트/통계도 동일 메타를 강제 수집하는 범위로 확장 예정.

## 1) Surface Quad / Quad-dominant 큐

### 상태
- `core/preprocessor/native_remesh/quad_dominant.py`는 현재는 **보수적 쌍 병합 fallback**이고, 4-RoSy/4-PoSy/특이점 해소/글로벌 컨포멀 추출은 미구현.
- 1차 근거: Alliez 2003, Jakob 2015, Huang 2018.

### 바로 실행할 카드
1. **`QUAD-ROSY1`**
   - 입력 입력 표면에 방향장(4-RoSy) 계산 + 특이점 후보 추적.
2. **`QUAD-POSY1`** (2차)
   - 4-PoSy 위치장 도입, 다중해상도 완화/슬라이딩 제어.
3. **`QUAD-FEATURE-BASIC1`**
   - 코너/에지/리짓/패치 보호 규칙을 기존 쌍 병합에 주입.
4. **`QUAD-MESH-EXTRACT1`**
   - 페어링 병합을 “fallback”로 두고, 기본 루트는 transaction 기반 사각 추출로 전환.
5. **`QUAD-INVERSION-SAFETY1`**
   - 인버전/비상태 모드 탐지 시 롤백·재시도(현재 규약과 충돌하지 않도록).

### 독립 벤치
- `test_native_quad` 스위트 + thin feature/roundness 회귀
- `quad_dominant.py` 단위 테스트에서 패치 보존, 공유 엣지 일관성, 비율(quad ratio) 모니터 추가
- `Preprocessor` L2 `native_quad_dominant` 파이프라인 테스트에서 route/contract 노출 검증 추가 (`tests/test_native_face_remesh.py`).

## 2) Volume Tet 큐

### 상태
- 문헌 증거: Shewchuk 1998, Si 2015, fTetWild 2020, Cheng 2000.
- 결론: 현재 파이프라인을 **CDT + Wild** 2 엔진으로 분리.

### 바로 실행할 카드
1. **`TET-CDT-1`**
   - `native_tet` 경로에서 segment/face 회복을 타입화(재시도 사유를 보존)한 보수 복구 루틴.
2. **`TET-WILD-1`**
  - triangle incremental transaction(현재 41분할/재시도 표를 바탕으로)과 봉합 가드 정합.
3. **`TET-DR-2`**
  - 반지름비는 통과해도 실패하는 sliver 판정(쌍각/체적/표면 근접성) 추가.
4. **`TET-WILD-2`**
   - 면 삽입 실패 시 커버/회복 기록을 유지한 채 재시도.

### 독립 벤치
- 비정상 면/두꺼운/얇은 채널 케이스에서 재현성(시드 고정), 실패 사유 분류
- `tests/bench_quality_matrix*.jsonl`에 tet route/contract/fallback 필드 추가

## 3) Volume Hex 큐

### 상태
- 문헌: Marechal 2009, CubeCover 2011, Gao 2017 + batch2.
- 결론: 현재 adaptive octree는 경로가 실질적으로 **polyhedral transition**이므로 “all-hex” 라벨은 분리 필요.

### 바로 실행할 카드
1. **`HEX-HD-1` (P0, honesty gate)**
   - 정확한 cell-type census 도입, 출력 경로가 진짜 all-hex인지 검증.
2. **`HEX-OCT-3`**
   - 국소 경계 교차·두께 유지 검사(얇은 막에서 빈 셀 붕괴 탐지 후 실패 플래그).
3. **`HEX-OCT-2`**
   - transition 후보군을 두 모드로 분기: (a) all-hex template mode, (b) generic poly mode, 라벨 투명성 강화.
4. **`HEX-HD-3`**
   - HybridOctree_Hex 스타일 전이 템플릿 최소 구현을 baseline으로 반영(입체 서명/방향성 검사 포함).
5. **`HEX-BL-1`**
   - BL 적용 후 타입 분포를 재계산해 보고, hexa dominant 주장 시 실제 hex 비율을 강제 표시.

### 독립 벤치
- `test_native_hex` + `harness/bench_native_tet_matrix.json`에 대응되는 hex mode route log
- orientation sensitivity: 30°/60°/90° 회전 반복에서 결과 타입 일관성/품질 열화율

## 4) Volume Poly 큐

### 상태
- 문헌: VoroCrust, Yan 2009/2013/2014, Gao 2017, Sorgente 지표.
- 결론: 현재 파이프라인은 seed/clip+local dual의 혼합 체계이며, topology 우선 규칙이 약함.

### 바로 실행할 카드
1. **`POLY-NO-DROP-HOLES1`**
   - 수정/삭제 연산에서 경계/컴포넌트 불연속을 허용하지 않는 보존형 rollback.
2. **`POLY-QUALITY-VECTOR1`**
   - 단일 “non-orthogonality”를 버리고 topology/geometry/kernel/warp/volume 품질 벡터로 승격.
3. **`POLY-VCG1`**
   - Voronoi clip/seed 전파 단계에 공유 페어링 기반(단순 최근접 탐색 대체) 경로 도입.
4. **`POLY-UNSKEW1`**
   - 조건부 Kim 2014 무결성·untangle 후처리 모듈을 보호형 트랜잭션으로 배치.

### 독립 벤치
- polyhedral 유효성: Euler/V-closedness/경계 patch 보존률/유효 체적 합성
- 복합 케이스(접합/강체 경계)에서 patch/재질 ID 보존률

## 5) 지금 즉시 수행할 다음 1차 액션 (오늘)

1. `docs/references/literature/engine_parallel_batch1_synthesis.md`와 각 엔진 evidence matrix를 기준으로
   위 카드의 실행 상태를 `TODO→RUNNING→DONE`로 갱신하는 작은 상태표 추가.
2. `tests/stl`의 엔진별 벤치 출력 스키마에 `route`, `contract`, `fallback_reason`, `cell_census` 필드 동기화.
3. `quad_dominant`, `native_tet`, `native_hex`, `native_poly` 결과 리포트에 failure transparency를 선행 반영.

다음 보고는 카드별 **PASS/FAIL 기준 위반 예시**와 함께, 위 순서대로 다음 스프린트에 넘어간다.
