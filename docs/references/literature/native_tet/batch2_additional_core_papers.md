# Native Tet 문헌조사 2차 (추가) - 핵심 7편 정리

일자: 2026-07-23  
범위: 1차(batch1)에서 정리된 3편(Shewchuk 1998, Si 2015, fTetWild) 및 기존 batch2 확장 목록과 중복 제외 후, 6~10편 중 우선 적용 가능한 7편 선별.

## 1) Feature-Sensitive Tetrahedral Mesh Generation with Guaranteed Quality

- **DOI**: `10.1016/j.cad.2012.01.002`
- **핵심 기법**
  - 입력 임의 표면 메쉬에서 정규 3D BCC(Body-Centered-Cubic) 격자를 이용해 적응적 4면체 생성.
  - top-down octree 분할 + 표면 근처 특수 처리로 경계에서 품질 보장.
  - 이론적으로 최소 이면 이면각이 약 `5.71°`보다 크도록 보장.
- **장점 / 한계**
  - 장점: 보장치가 있는 품질 하한, 자동 적응성(곡률 높은 영역에서 더 촘촘한 샘플), 단일 단계로 경계 민감도 반영.
  - 한계: 임의 표면 메쉬 입력에 최적화되어 있으며, 매우 복잡한 작은 feature 다층 경계에서는 경계 정합/수렴성이 모델별로 다르게 나타날 수 있음.
- **AutoTessell 적용 포인트**
  - `NativeTetPLC`에서 경계-근접 구간 초기화 단계의 후보 커널로 채택(특히 feature-preserving boundary mesh 시작점).
  - feature tag(꼭짓점/엣지/면 민감도) 기반 크기 제약을 기존 `f_size` 또는 local feature size 연동 파이프라인에 결합.
- **비고**: `ABSTRACT_ONLY` (요약 기반 정리)

## 2) Quality Meshing with Weighted Delaunay Refinement

- **DOI**: `10.1137/S0097539703418808`
- **핵심 기법**
  - 가중 Delaunay 정합 + weight pumping을 결합해 경계 보존과 sliver 제거를 함께 수행.
  - 단계적 refinement에서 boundary conformation과 sliver exudation을 하나의 결정론적 프레임워크로 통합.
- **장점 / 한계**
  - 장점: 경계 보존형 3D 품질 메싱에서 sliver 억제 이론을 명시적으로 제시.
  - 한계: 급성 경계각(acute) 입력 가정이 약함(논문에서 가정 기반 성능 보장 제시).
- **AutoTessell 적용 포인트**
  - 장기 과제로 `STELLAR-like` 고급 경로(가중 정규 삼각분할) 후보로 관리.
  - 현재 파이프라인에 직접 접목 시 `가중-반경엣지 혼합 정당성`과 `경계 각도 라벨` gate가 선행되어야 함.
- **비고**: `ABSTRACT_ONLY` (요약 기반 정리)

## 3) Improved Boundary Constrained Tetrahedral Mesh Generation by Shell Transformation

- **DOI**: `10.1016/j.apm.2017.07.011`
- **핵심 기법**
  - boundary recovery 과정에서 스테이너(추가 정점) 과다 삽입 문제를 줄이기 위해 shell transformation을 지역적으로 적용.
  - 지역적 flip/재배치로 국소 최적 패턴을 찾고 재귀적으로 확장.
- **장점 / 한계**
  - 장점: 경계 제약 충족 품질 개선에서 보수적 Steiner 증가 완화.
  - 한계: 난해 boundary case에 대해 반복 깊이/성능 제약이 크고, 설정 민감도 존재.
- **AutoTessell 적용 포인트**
  - `segment/face recovery 실패 후 리트라이` 후처리에 `steiner-guarded flip` 계층으로 추가.
  - Thin triangle strip/높은 종횡비 표면에서 스테이너 사용량 로그 및 감축률 지표를 메트릭에 포함.
- **비고**: `ABSTRACT_ONLY` (요약 기반 정리)

## 4) A Novel Geometric Flow Approach for Quality Improvement of Multi-Component Tetrahedral Meshes

- **DOI**: `10.1016/j.cad.2013.05.004`
- **핵심 기법**
  - 형상 개선과 위상 조정(면 스왑, 엣지 제거)을 함께 수행하는 기하/위상 하이브리드 개선.
  - 평균 곡률 기반 표면 평활(평균 곡률 유량), 내부는 품질 목표 함수 최적화 결합.
- **장점 / 한계**
  - 장점: 다중 도메인/비매니폴드 경계에서 위치+연결 동시 최적화.
  - 한계: 나쁜 valence의 잔존이 있을 수 있어 완전한 sliver 제거 보장은 제한.
- **AutoTessell 적용 포인트**
  - `NativeTetWild` 후처리에서 region/patch 분리 후 region별 개선 운영자로 도입.
  - 위상 변경 연산 전후로 경계 토폴로지/부피 보존 체크를 반드시 transaction-rollback으로 감쌀 것.
- **비고**: `ABSTRACT_ONLY` (요약 기반 정리)

## 5) Sliver-Suppressing Tetrahedral Mesh Optimization with Gradient-Based Shape Matching Energy

- **DOI**: `10.1016/j.cagd.2017.02.004`
- **핵심 기법**
  - 슬리버 억제를 위해 정형(simplex template) 기반 shape matching energy를 도입.
  - 정점 이동 + 국소 토폴로지 변경을 반복 최적화해 메쉬 요소를 이상형에 근접시킴.
- **장점 / 한계**
  - 장점: 작은 높이/얇은 요소 억제 성능이 강함, 다중 표준 지표 대비 sliver 민감도 향상.
  - 한계: 에너지 형태가 강하면 지역 최적에 빠질 가능성이 있어 스케줄/초기화가 중요.
- **AutoTessell 적용 포인트**
  - 현재 AMIPS + radius-edge만으로는 포착 어려운 sliver를 탐지/거부하는 `shape-barrier`로 통합.
  - 위상 변경 시 `전후 임계치(최소 사면각/부피)`를 교차 비교하는 rollback 조건에 shape-loss 지표 추가.
- **비고**: `ABSTRACT_ONLY` (요약 기반 정리)

## 6) Tetrahedral Mesh Improvement Using Moving Mesh Smoothing, Lazy Flips, and RBF Surface Reconstruction

- **DOI**: `10.1016/j.cad.2017.11.010`
- **핵심 기법**
  - PDE 기반 moving-mesh smoothing + lazy flip(가역적 엣지 제거 기반 탐색 flips) + 곡면 경계 보정용 RBF 재구성 결합.
  - 형태/크기/방향성 품질 목표 함수를 동시에 고려하는 통합 프레임.
- **장점 / 한계**
  - 장점: 조합 전략이 단독 smoothing/flip 대비 개선도 상승.
  - 한계: 곡면 보정 경로가 추가되며, 고정밀 경계 모델에서 계산비용 상승.
- **AutoTessell 적용 포인트**
  - 3단계 스케줄: (1) 경계 유지 smoothing, (2) lazy flip, (3) RBF boundary 재투영의 transaction형 반복으로 구성.
  - 현재 `wild`/`PLC` 모두에서 독립 파생점으로 두어 실험적으로 품질 향상 벡터를 벤치.
- **비고**: `ABSTRACT_ONLY` (요약 기반 정리)

## 7) Multi-threaded Parallel Tetrahedral Mesh Improvement by Combining Atomic Operation and Graph Coloring

- **DOI**: `10.1016/j.advengsoft.2024.103782`
- **핵심 기법**
  - 원자 연산 + 작업 분해 + 멀티스레드 메모리 모델로 overlap/경쟁을 줄여 병렬 품질 개선.
  - axis-aligned 분해로 독립 작업군 구성, 데이터 경합 완화.
- **장점 / 한계**
  - 장점: 16-thread 환경에서 10배 가량 속도 향상 보고.
  - 한계: 병렬화가 강한 품질 연산일수록 결정론 재현성과 경합 디버깅이 어려워짐.
- **AutoTessell 적용 포인트**
  - 현재는 serial correctness가 확보된 핵심 연산(안정성 높은 smoothing/topology op)에만 도입.
  - `parallel-safe kernel`으로 이동 전 동일 메쉬에 대한 2-pass deterministic 체크(입력/출력 동일성) 의무화.
- **비고**: `ABSTRACT_ONLY` (요약 기반 정리)

