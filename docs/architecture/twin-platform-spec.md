# CFD Surrogate / Digital-Twin Platform — Product Spec & Architecture Review

> Provenance: user-authored specification and architectural review, 2026-07-18.
> Stored verbatim (lightly formatted) as the durable contract for Track B of
> ROADMAP.md. The judgement, priorities, and stage gates below are the
> product owner's; implementation must not silently deviate from them.

## 종합 판정

현재 기획은 **범용 CFD 결과 기반 대리모델·연산자 학습 및 검증 플랫폼**에 가깝다.
아직은 엄밀한 의미의 운영형 디지털 트윈은 아니다. 운영형 디지털 트윈으로
분류되려면 물리 시스템이나 센서로부터 지속적으로 상태를 갱신하고, 예측을 통해
의사결정을 지원하며, 필요하면 물리 시스템과 양방향으로 상호작용하는 계층이
추가되어야 한다.

모델보다 먼저 해결해야 하는 문제 네 가지:

1. **CFD 데이터와 경계조건을 표현하는 표준 데이터 모델**
2. **격자 변환·다운샘플링·보간 과정의 물리적 일관성**
3. **데이터 조건에 따라 사용 가능한 학습 전략을 자동으로 제한하는 구조**
4. **GUI와 MPI/GPU 계산 프로세스의 완전한 분리**

모든 정상·비정상, 정렬·비정렬, 동일·상이 형상, 1D·2D·3D 데이터를 하나의
신경망으로 처리하려는 구조는 적절하지 않다. 앱이 데이터의 특성을 분석한 후,
호환되는 모델만 활성화하는 **전략 레지스트리 방식**이 필요하다.

## 1. 현재 기획의 주요 문제점과 해결 방법

| 문제 | 예상되는 실패 형태 | 해결 방법 |
|---|---|---|
| 정상·비정상, 형상, 조건만으로 데이터 분류 | 동일 형상이나 격자가 다르거나, 동일 격자이나 좌표가 변하는 경우를 구분하지 못함 | 형상, 위상, 격자, 시간, 필드 위치, 좌표계 등을 독립 속성으로 정의 |
| 결과가 없는 셀에 0 입력 | 0이 실제 물리값인지 결측값인지 모델이 구분하지 못함 | `value + valid_mask + fluid_mask + boundary_mask` 구조 사용 |
| 모든 데이터를 균일 격자로 변환 | 3D에서 빈 voxel이 급증하고, 경계층·곡률·충격파가 손실됨 | 균일 격자 경로와 native mesh 경로를 분리 |
| 단순 해상도 비율 슬라이더 | 셀 수는 줄지만 QoI, 질량보존, 벽면 전단 등이 크게 변할 수 있음 | 보존형 coarsening, 경계층 보존, patch 학습, 전처리 오차 사전 평가 |
| point/cell/face 결과를 동일하게 취급 | 물리량 위치가 변경되면서 의미가 달라짐 | 필드 association을 필수 메타데이터로 저장하고 변환을 명시적으로 수행 |
| 시간 프레임 무작위 train/test 분할 | 같은 trajectory의 인접 프레임이 양쪽에 들어가 데이터 누수 발생 | case, geometry, condition, trajectory 단위 group split |
| 경계면을 삼각형 단위로 수동 선택 | 대형 3D 모델에서 사실상 사용 불가능 | seed 선택, connectivity region growing, normal-angle threshold, lasso, patch import |
| SDF를 모든 형상에 적용 | 열린 입출구가 있는 CFD 영역에서는 signed SDF의 부호가 불안정 | 폐곡면만 signed SDF 사용. 일반 CFD 영역에는 fluid mask와 unsigned wall distance 사용 |
| 실제값이 없는 extrapolation 결과를 일반 결과처럼 표시 | 신뢰할 수 없는 외삽 결과가 정상 예측처럼 보임 | OOD 점수, 학습 데이터 거리, 불확실성, 보존 오차를 별도로 표시 |
| GUI에서 직접 MPI/GPU 계산 수행 | UI 정지, MPI 초기화 충돌, 취소·복구 곤란 | GUI, job manager, CPU/MPI worker, GPU worker를 프로세스 단위로 분리 |
| 모델을 많이 통합하는 것이 우선이라는 가정 | 전처리와 평가 방식이 달라 모델 간 비교 자체가 무의미해짐 | 데이터 계약과 평가 프로토콜을 먼저 고정하고 모델을 순차적으로 추가 |
| 1D·2D·3D만으로 차원 표현 | 2D surface가 3D 공간에 존재하는 경우를 표현하지 못함 | `topological_dimension`과 `embedding_dimension`을 분리 |

## 2. CFD 표준 데이터 모델

### 2.1 핵심 엔터티

```text
Project
 ├─ Dataset
 │   ├─ Geometry
 │   ├─ MeshTopology
 │   ├─ MeshVersion
 │   ├─ Zone / Block / Partition
 │   ├─ Case
 │   │   ├─ ConditionSet
 │   │   ├─ BoundaryConditionInstance
 │   │   ├─ TimeAxis
 │   │   └─ Field
 │   └─ DerivedFeature
 ├─ PreprocessRecipe
 ├─ SplitDefinition
 ├─ TrainingRun
 ├─ ModelVersion
 └─ Prediction / Evaluation
```

Geometry와 Mesh 분리 근거 — 다음 세 경우는 서로 다른 데이터다:
(1) 형상·격자 위상 모두 동일, (2) 형상 동일·격자 상이, (3) 형상 상이.

식별자: `topology_hash`(connectivity/cell type/zone), `coordinate_hash`(node
좌표), `surface_geometry_hash`(외부 표면), `boundary_signature`(patch 종류·연결).
자동 판별 클래스:

```text
fixed_geometry_fixed_mesh | fixed_geometry_different_mesh | varying_geometry
moving_mesh_fixed_topology | moving_mesh_changing_topology
```

### 2.2 Field 메타데이터 (필수 속성)

```text
name, physical_role, association(point|cell|face), components, tensor_rank,
units, coordinate_frame, basis, intensive_or_extensive, conserved_or_derived,
time_dependence, valid_mask, source_file, source_variable_name
```

- intensive quantity(압력·온도): 일반 보간 가능
- 보존량(질량·총에너지·face flux): conservative remapping 필수
- wall shear stress: 표면·방향 기저 보존
- 속도 벡터: 좌표계/local frame 변경 시 성분 변환

### 2.3 경계조건 — 기하 정의와 case별 값의 분리

```text
BoundaryPatch: patch_id, geometry entities, patch role, outward orientation,
               periodic/interface relation
BoundaryConditionInstance: case_id, patch_id, bc_type,
               scalar/vector/profile/function, units, coordinate frame,
               time dependence
```

지원 BC 표현: 상수 scalar/vector, 공간 분포, 시간 함수, 공간·시간 함수, 파일
기반 profile, periodic pair, interface pair, symmetry/slip/no-slip,
rotating/moving wall.

### 2.4 시간 데이터

`t`, frame index, `Δt`(가변 여부), trajectory ID, restart segment, 초기조건,
시간 의존 BC, 격자 좌표의 시간 의존성, topology 변경 여부. 프레임 수가 다른
case는 sequence mask 또는 ragged storage.

## 3. 저장소 구조 (4계층)

1. **Immutable Raw Store** — 원본 VTK/CGNS 무변경 보존
2. **Canonical CFD Store** — CGNS(의미론 보존) + VTKHDF(병렬 I/O·시각화 캐시)
3. **ML Cache** — Zarr (chunked, 압축, case/time/partition 부분 읽기,
   preprocessing hash별 캐시, fixed-size tensor vs variable shard 구분)
4. **Metadata/Experiment Store** — SQLite(단일 PC)/PostgreSQL(서버), MLflow
   (run·metric·artifact·checkpoint·model lineage)

## 4. 시스템 아키텍처

초기에는 **모듈형 모놀리스 + 독립 worker 프로세스**. GUI(Qt/PySide6+VTK)는
탐색·선택·파라미터·job 제출·시각화만; MPI 초기화·GPU context·대규모 보간·학습은
worker 프로세스(CPU/MPI/GPU/Eval)로 분리. 모든 계산은 immutable job spec
(job_id, dataset_version, split_version, preprocess_recipe_hash,
strategy_name/version, hyperparameters, random_seed, hardware_request,
software_environment)으로 제출.

플러그인 인터페이스: `ReaderPlugin(probe/read_metadata/read_case)`,
`PreprocessorPlugin(validate/fit/transform)`,
`TwinStrategy(capabilities/validate/build/train/predict)`,
`MetricPlugin(requirements/evaluate)`.

## 5. DatasetSignature (데이터 조건 자동 판별)

```text
temporal_mode: steady | transient_fixed_mesh | transient_moving_coordinates
               | transient_changing_topology
geometry_relation: fixed | same_geometry_different_mesh | varying
mesh_type: structured | unstructured | point_cloud | mixed
topological_dimension: 1|2|3   embedding_dimension: 1|2|3
field_association: point|cell|face|mixed
boundary_input: scalar|vector|profile|function
output_target: volume|surface|query_point|global_qoi
maximum_entities, trajectory_length, time_step_mode
```

각 전략은 capability를 선언하고, 비호환 모델은 경고가 아니라 **선택 목록에서
비활성화**된다. (예: FNO = structured_grid required, fixed_tensor_shape
required, moving_topology unsupported.)

## 6. 전처리 파이프라인 (버전 관리되는 DAG)

Import → Integrity validation → Unit/coordinate normalization → Field semantic
mapping → Boundary labeling → Geometry feature generation → **Dataset split**
→ Train-only normalization fitting → Representation conversion → Resolution
transformation → Partition/sharding → ML cache generation.

**Split이 정규화보다 먼저.** 필수 split 4종: condition interpolation /
condition extrapolation / geometry OOD / joint OOD. 비정상 데이터는 trajectory
단위 group split (인접 프레임 분할 금지 — 시간 상관 누수).

## 7. 해상도 감소와 격자 변환

- "50%"의 의미를 명시 (축/node/cell/spacing/sampling/coarsening level) + UI에
  변환 전후 node/cell 수, RAM/VRAM 추정, 경계면 해상도, 최소 wall-normal cell
  수, downsample-reconstruct 오차, QoI 변화량 표시.
- 정렬격자: cell-centered intensive → volume-weighted restriction; conserved →
  conservative restriction; 벽면·경계층 wall-normal 우선; shock 영역
  feature-preserving. 단순 index stride는 진단용 외 금지.
- 비정렬격자 3경로: mesh coarsening(connectivity·patch·near-wall 보존) /
  point sampling(FPS·graph clustering·boundary-stratified·volume-weighted) /
  patch 학습(halo/overlap + blending).
- 균일 격자 변환은 FNO/CNN 전용. 저장: grid_values + valid_mask + fluid_mask +
  solid_mask + boundary_type_channels + wall_distance + interpolation_weight_id
  + source_mesh_id. bare zero 금지 — mask 채널 필수, loss 에서 제외:
  L = Σ mᵢwᵢ ℓ(ŷᵢ,yᵢ) / (Σ mᵢwᵢ + ε).
- 보간: ESMPy(conservative regridding), MEDCoupling(비일치 mesh 필드 전달).

## 8. 경계면 지정과 형상 특징

편집기 순서: patch import 우선 → seed face → connectivity region growing →
normal-angle threshold → lasso/brush → role/BC 지정 → 검증 (중복 지정, 미지정
face, periodic 일치, interface 연결, normal 일관성, 단위).

학습용 형상 특징: 좌표, surface normal, cell volume/face area, local mesh
size, wall distance, inlet/outlet/symmetry distance, closest boundary vector,
curvature, fluid mask, boundary one-hot, SDF(폐곡면 한정 signed; 개방 domain은
fluid_mask + unsigned wall distance + 거리 벡터 조합), geometry/무차원 파라미터.

## 9. 트윈 학습 전략 (전략 매트릭스)

| 데이터 유형 | 1차 전략 | 대안 | 핵심 제한 |
|---|---|---|---|
| 정상, 동일 격자, 낮은 내재 차원 | POD/PCA + MLP/RBF/GPR | FNO | 비선형·복잡 형상에서 mode 수 증가 |
| 비정상, 동일 격자, 낮은 내재 차원 | POD-DMD, OpInf | latent autoregressive | 장기 비선형 천이 한계 |
| 정상, 정렬격자, 동일 형상 | FNO/TFNO | U-Net, PINO | regular tensor 필요 |
| 비정상, 정렬격자, 동일 형상 | autoregressive/space-time FNO | latent dynamics | rollout 누적 오차 |
| 비정렬, 동일 topology, 비정상 | MeshGraphNet | UPT, Transolver temporal | edge memory·장기 rollout |
| 비정렬, 다른 형상, 정상 | Transolver, GINO | DoMINO, AB-UPT | geometry encoding·데이터 규모 |
| 대형 3D 외부유동 | DoMINO, AB-UPT | Transolver++ | 전처리·domain 구성 복잡 |
| 다른 형상, 비정상 | UPT, MGN 계열, temporal Transolver | latent NO | 최고 난도 |
| 함수형 BC/sparse sensor | DeepONet/POD-DeepONet | query UPT | dense 3D 복원 비용 |
| PDE 정보 | supervised + physics loss | PINO/PINN | pure PINN 기본값 부적절 |
| 수천만+ cell | query/patch/tiling + scalable operator | Transolver++/3, PGD-NO | 재현성 검증 필요 |

ROM 계열(POD/PCA+RBF/MLP/GP, DMD/EDMD, OpInf — pyMOR/PyDMD/OpInf)은 **필수
기준선**: 데이터 누수·전처리 오류 검출과 저차원성 판별. 장기 rollout은
one-step loss 금지 — multi-step rollout loss, 입력 노이즈, teacher forcing
감소, horizon별 검증.

제품 통합 등급: **Production Core** = POD/PCA, PyDMD/OpInf, FNO/TFNO, GINO,
Transolver, MeshGraphNet · **Domain-Specific Advanced** = UPT, DoMINO, AB-UPT,
Transolver++ · **Experimental** = Transolver-3, PGD-NO, 2026 preprints.

## 11. 평가 구조

Viewer: 실제/예측/분할/overlay/signed·abs·rel error/uncertainty/OOD — camera·
slice·colormap·range·time 동기화, **기본 공통 color range** (다른 range 는
오차 은폐). 격자가 다르면 공통 평가 공간(truth/pred/reference mesh/query
points) 필요, **remapping error 와 model error 분리** (reconstruction test 로
보간 error floor 산출). Metric: field(rel L1/L2, MAE/RMSE, percentile, max,
벡터 크기/각도), 영역별(near-wall/patch/wake/ROI), 물리 QoI(질량유량, 압력강하,
drag/lift, 열유속, 보존 imbalance), 비정상(rollout horizon, phase, spectrum,
시간평균, 안정성 실패 시점). 외부 벤치: PDEBench, CFDBench, PDEArena.

## 12. Extrapolation 표시

IN_SUPPORT / NEAR_SUPPORT_BOUNDARY / OUT_OF_SUPPORT 3단계. OOS 예측은 값은
표시하되 검증 완료 결과와 동일 상태로 저장 금지. 함께 표시: parameter support,
geometry distance, nearest training cases, ensemble uncertainty, physics
residual, conservation error, model applicability.

## 13. 병렬 처리

CPU/IO: threading(I/O), multiprocessing(전처리), MPI(case/time/zone/partition),
OpenMP(C++ 내부) — rank당 thread 명시로 oversubscription 방지. GPU: DDP(모델이
GPU에 들어갈 때) / FSDP(파라미터 shard) + graph partitioning, halo, patch
training, query batching, checkpointing, mixed precision. 실행 백엔드 3단계
(Local/Workstation/HPC)가 **동일한 job spec과 artifact 구조** 사용.

## 14. 기술 스택

PySide6 · VTK/PyVista · CGNS MLL · VTKHDF · Zarr · ESMPy · MEDCoupling ·
NeuralOperator(FNO/TFNO/GINO) · PhysicsNeMo(MGN/Transolver/DoMINO/분산) ·
DeepXDE(PINN/DeepONet) · pyMOR · PyDMD · OpInf · PyTorch(DDP/FSDP) · MLflow ·
PDEBench/CFDBench/PDEArena. **상용 배포 전 dependency·model code 라이선스 검토.**

## 15. 개발 로드맵 (단계 0~6)

- **단계 0 — 데이터 계약과 지원 범위 고정**: canonical schema, field/BC
  ontology, unit·좌표계 규칙, topology/geometry hash, DatasetSignature, plugin
  capability contract, 검증 데이터셋, 라이선스 목록. 종료: 재import 시 동일
  hash, association 무손실, 미지원 데이터 명시적 거부.
- **단계 1 — 데이터 로드와 Viewer MVP**: VTK/CGNS reader, explorer, field
  viewer, patch import, region growing 선택, BC editor, wall distance/mask,
  raw+canonical 저장. 종료: 통계 일치, 선택 재현, GUI 비차단 로딩.
- **단계 2 — 전처리와 기준 모델**: preprocessing DAG, split manager,
  train-only normalization, down/coarsening, remap error 평가, Zarr, POD/PCA,
  PyDMD, OpInf, FNO/TFNO, MLflow, error viewer. 종료: 재현 가능 artifact,
  remap/model error 분리, leakage 자동 검사.
- **단계 3 — 비정렬·상이 형상**: graph/point 표현, Transolver, GINO, geometry
  descriptor, query 출력, patch/partition, MGN transient, ensemble/OOD. 종료:
  가변 node 수 batch, uniform 변환 없는 학습, OOD split 평가, rollout 안정성.
- **단계 4 — 대형 3D와 HPC**: multi-node DDP/FSDP, MPI 전처리, halo, query
  batching, DoMINO, AB-UPT, Transolver++, scheduler, checkpoint/resume, 자원
  추정. 종료: GUI-계산 분리 실행, 중단 복구, 확장성 측정, full-res 재구성.
- **단계 5 — 연구 모델 실험 트랙**: Transolver-3, PGD-NO, tiling/cache, 독립
  재현 검증. 종료: production 대비 개선이 내부 데이터에서도 재현.
- **단계 6 — 운영형 디지털 트윈**: sensor stream, 상태 동기화, data
  assimilation, online calibration, drift detection, rollback, 불확실성 경보,
  제어 API, 양방향 인터페이스.

## 16. 최종 구현 우선순위

1. Canonical CFD schema와 validator
2. 경계조건·mask·geometry feature 체계
3. 재현 가능한 preprocessing DAG와 split manager
4. POD/DMD/OpInf 기준선
5. 정렬격자용 FNO/TFNO
6. 상이 형상·비정렬용 Transolver와 GINO
7. 비정상 비정렬용 MeshGraphNet과 UPT
8. 대형 3D용 DoMINO, AB-UPT, Transolver++
9. Transolver-3, PGD-NO 연구 검증
10. 센서·운전 데이터가 연결되는 운영형 트윈 계층

MVP 데이터 조합 3종: 동일 형상·정렬격자·다양 조건(ROM+FNO) / 상이 형상·
비정렬·정상(Transolver+GINO) / 동일 topology·비정렬·비정상(MeshGraphNet).
최후 순위: 상이 형상 + 비정상 + topology 가변 비정렬격자.

> 핵심 자산은 특정 신경망이 아니라 **CFD 의미론을 보존하는 데이터 계약, 변환
> 이력, 호환성 판정, 공정한 평가 체계**다. 이 기반이 고정된 이후에야 여러
> SOTA 모델을 동일 조건에서 신뢰성 있게 비교하고 교체할 수 있다.
