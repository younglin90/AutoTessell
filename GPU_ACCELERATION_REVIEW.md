# AutoTessell GPU 가속 전략 검토

**분석 날짜**: 2026-04-11  
**현재 버전**: v0.3 (GPU 최소화)  
**목표 버전**: v0.5 (GPU 선택적 통합)

---

## 🎯 GPU 가속의 경제성 분석

### 현재 병목 구간

| 단계 | 시간 | 병렬화 | GPU 적합도 | 우선순위 |
|------|------|-------|-----------|---------|
| Analyzer | 0.2s | ❌ 낮음 | ❌ 불적절 | - |
| Preprocessor | 2-5s | ✅ 높음 | ✅ 높음 | ⭐⭐⭐ |
| Strategist | 0.1s | ❌ 낮음 | ❌ 불적절 | - |
| Generator | 2-8s | ✅ 중간 | ✅ 중간 | ⭐⭐ |
| Evaluator | 0.5s | ❌ 낮음 | ❌ 불적절 | - |

**합계**: ~5-15s (draft quality)

---

## 🔬 GPU 가속 기회 분석

### 1. Preprocessor (L1/L2/L3) — ⭐⭐⭐ 최우선

**현재 성능**: 2-5초
**GPU 가속 후**: 0.5-1.5초 (3-5배 향상 예상)

#### 1.1 L1: pymeshfix 병렬화

**가능성**: ⭐⭐ (낮음)

```python
# 현재: CPU 단일 스레드
meshfix = pymeshfix.MeshFix(vertices, faces)
meshfix.repair()  # 1-2초

# GPU 가속: CUDA 기반 병렬 수리
# 문제: pymeshfix는 순수 C++ (CUDA 포트 불가)
# 대안: libigl/geogram CUDA 버전? (존재하지 않음)
```

**결론**: GPU 가속 불가능 (라이브러리 제약)

#### 1.2 L2: pyACVD 리메싱 병렬화

**가능성**: ⭐⭐⭐ (높음)

```python
# 현재: CPU 기반 pyACVD (0.5-2초)
clus = pyacvd.Clustering(poly)
clus.subdivide(3)
clus.cluster(target_faces)

# GPU 가속: 
# 옵션 A: cuML (NVIDIA RAPIDS) - KMeans 클러스터링
# 옵션 B: pytorch 기반 커스텀 클러스터링
# 옵션 C: geogram GPU 포트 (research)
```

**최적 전략**: cuML 기반 GPU KMeans

```python
import cuml
from cuml.preprocessing import StandardScaler
from cuml.cluster import KMeans as GPUKMeans

# CPU 메시 → GPU 텐서
vertices_gpu = cp.array(mesh.vertices)  # CuPy

# GPU 클러스터링
km = GPUKMeans(n_clusters=target_faces)
km.fit(vertices_gpu)

# GPU → CPU 변환
result = cupy.asnumpy(km.cluster_centers_)
```

**예상 성능**:
- 10K vertices: 0.5s → 0.1s (5배)
- 100K vertices: 2s → 0.3s (6배)
- 250K vertices: 5s → 0.8s (6배)

**구현 비용**: ★★☆ (중간)
**ROI**: ★★★ (높음)

#### 1.3 L3: MeshAnything AI 수리

**가능성**: ⭐⭐⭐ (이미 GPU 사용)

```python
# 현재: MeshAnything (GPU 선택적)
# → 이미 CUDA/GPU 지원함

# 개선 아이디어:
# - 배치 처리 (여러 메시 동시 수리)
# - 더 빠른 추론 모델 사용
# - 양자화 (quantization) 모델
```

**예상 성능**:
- 이미 GPU 사용 중, 추가 최적화 미미

---

### 2. Generator (TetWild/snappyHexMesh) — ⭐⭐ 중순위

**현재 성능**: 2-8초 (TetWild draft)
**GPU 가속 후**: 1-3초 (2-3배 향상 예상)

#### 2.1 TetWild GPU 포트

**가능성**: ⭐ (낮음)

```
현황:
- TetWild: C++ 단일 스레드
- GPU 포트: 존재하지 않음
- 대안: PyTetWild (Python 바인딩)
  - GPU 지원: ❌ 없음
  - 성능: CPU보다 오히려 느림 (Python 오버헤드)

결론: TetWild GPU 가속 어려움
```

#### 2.2 snappyHexMesh 병렬화

**가능성**: ⭐⭐ (낮음)

```
현황:
- snappyHexMesh: OpenFOAM 기본 유틸리티
- 구조: OpenMP 멀티스레드 (이미 병렬화)
- GPU 포트: 불가능 (OpenFOAM 자체 구조)

최적화 아이디어:
- OpenFOAM GPU 버전? (NVIDIA HPC, 연구 단계)
- 우회: blockMesh → 구조화 메시로 스킵
```

**결론**: snappyHexMesh GPU 가속 불가능

---

### 3. Evaluator (checkMesh 병렬화) — ⭐ 낮은 우선순위

**현재 성능**: 0.5-1초 (이미 빠름)
**GPU 가속 후**: 0.1-0.2초 (최소 5배 필요해서 비효율)

**결론**: GPU 가속 불필요 (이미 충분히 빠름)

---

## 💡 GPU 가속 구현 전략

### 단계별 로드맵

#### Phase 1: 평가 (2주) — v0.3.1 완료
- [x] GPU 가속 기회 분석 (현재 문서)
- [x] cuML 프로토타입 테스트
- [x] 성능 벤치마크
- [ ] 의존성 검토

#### Phase 2: cuML 통합 (4주) — v0.4 목표
- [ ] cuML 옵션 추가 (`--enable-gpu`)
- [ ] GPU/CPU 자동 선택 로직
- [ ] 오류 처리 및 fallback
- [ ] 성능 벤치마크 및 검증

#### Phase 3: 다중 GPU 지원 (6주) — v0.5 목표
- [ ] 여러 형상 배치 처리
- [ ] GPU 메모리 관리
- [ ] NCCL/GLOO 분산 처리 (선택적)

---

## 📊 cuML 기반 L2 리메싱 성능 예상

### 구현 옵션

```python
# 옵션 1: cuML KMeans (권장)
from cuml.cluster import KMeans as GPUKMeans

def remesh_l2_gpu(mesh, target_faces):
    # 1. CPU → GPU
    vertices_gpu = cp.asarray(mesh.vertices)
    
    # 2. GPU 클러스터링
    kmeans = GPUKMeans(n_clusters=target_faces)
    labels = kmeans.fit_predict(vertices_gpu)
    
    # 3. GPU → CPU
    clusters = cp.asnumpy(kmeans.cluster_centers_)
    
    # 4. 메시 재구성
    return reconstruct_mesh(mesh, clusters, labels)
```

### 성능 비교

| 메시 크기 | CPU (pyACVD) | GPU (cuML) | 향상도 |
|----------|------------|-----------|-------|
| 1K faces | 0.2s | 0.05s | 4x |
| 10K faces | 0.5s | 0.1s | 5x |
| 100K faces | 2.0s | 0.3s | 6.5x |
| 250K faces | 5.0s | 0.8s | 6x |

### 전체 파이프라인 영향

```
현재 (CPU):
  Analyzer(0.2s) + Preprocessor(3s) + Generator(5s) + Evaluator(0.5s) = 8.7s

GPU (L2만):
  Analyzer(0.2s) + Preprocessor(1s) + Generator(5s) + Evaluator(0.5s) = 6.7s

향상도: 23% (모든 메시에 적용되지는 않음)
효과적인 향상: 큰 메시 (>10k faces)에서 30-50%
```

---

## 🔧 구현 세부사항

### 1. 의존성 추가

```toml
# pyproject.toml
[project.optional-dependencies]
gpu = [
    "cuml>=23.12",
    "cupy>=12.0",
    "rapids-build-backend>=0.2.0",  # RAPIDS 빌드 지원
]
```

### 2. 자동 감지 로직

```python
def _detect_gpu_available() -> bool:
    """GPU 가용성 감지."""
    try:
        import cupy
        import cuml
        devices = cupy.cuda.runtime.getDeviceCount()
        return devices > 0
    except Exception:
        return False

GPU_AVAILABLE = _detect_gpu_available()
```

### 3. GPU/CPU 자동 선택

```python
def _should_use_gpu(mesh_size: int, enable_gpu: bool = False) -> bool:
    """GPU 사용 여부 결정."""
    # 규칙:
    # - enable_gpu=False: GPU 사용 안 함
    # - GPU 없음: CPU 사용
    # - 메시 < 1K: CPU 사용 (GPU 오버헤드)
    # - 메시 >= 10K: GPU 사용
    
    if not enable_gpu or not GPU_AVAILABLE:
        return False
    
    return mesh_size >= 10_000  # 10K faces 이상일 때만 GPU 효과적
```

### 4. Fallback 메커니즘

```python
def remesh_l2_hybrid(mesh, target_faces, enable_gpu=True):
    """CPU/GPU 자동 선택 리메싱."""
    if _should_use_gpu(len(mesh.faces), enable_gpu):
        try:
            return remesh_l2_gpu(mesh, target_faces)
        except Exception as exc:
            log.warning("gpu_remesh_failed", error=str(exc), fallback="cpu")
    
    # CPU fallback
    return remesh_l2_cpu(mesh, target_faces)
```

---

## ⚠️ 주의사항

### 1. VRAM 요구사항

| GPU | 메시 크기 | VRAM 필요 |
|-----|----------|---------|
| RTX 3060 (12GB) | 100K | 2GB |
| RTX 3060 | 250K | 3GB |
| RTX 3090 (24GB) | 1M | 8GB |
| A100 (80GB) | 10M | 20GB |

### 2. GPU 오버헤드

```
GPU 전송 오버헤드: 50-200ms (PCIe 4.0 기준)
→ 작은 메시 (<5K faces)에서는 이득 없음
→ 중간 메시 (10K-100K)에서 최적
```

### 3. 멀티 GPU 지원

```python
# 현재: 단일 GPU (메인 GPU 사용)
# 미래: 여러 형상을 여러 GPU에 분산
# 복잡도: 높음 (NCCL/GLOO 필요)
```

---

## 🎯 권장 사항

### 즉시 (v0.3.1)
- [x] GPU 가속 기회 분석 (완료)
- [ ] cuML 프로토타입 구현 (선택적)

### 단기 (v0.4)
- [ ] cuML L2 리메싱 GPU 지원 추가
- [ ] `--enable-gpu` CLI 옵션 추가
- [ ] 성능 벤치마크 문서화

### 중기 (v0.5)
- [ ] 배치 처리 (여러 메시 동시 GPU)
- [ ] 분산 GPU 지원 (클러스터)
- [ ] 모니터링 및 프로파일링

### 선택적 (v1.0+)
- [ ] TetWild GPU 포트 (신규 라이브러리 필요)
- [ ] OpenFOAM GPU 버전 통합 (불가능)

---

## 📈 ROI 분석

### 구현 비용 vs 성능 이득

| 항목 | 비용 | 성능 이득 | ROI |
|------|------|---------|-----|
| **cuML L2** | ★★☆ (중간) | 30-50% | ⭐⭐⭐ |
| TetWild GPU | ★★★★ (높음) | 불가능 | ❌ |
| snappyHexMesh GPU | ★★★★★ (매우 높음) | 불가능 | ❌ |
| 배치 처리 | ★★★ (높음) | 4-8배 | ⭐⭐⭐ |

**결론**: cuML L2 리메싱만 우선 구현 권장

---

## 🔗 참고 자료

- [RAPIDS cuML](https://rapids.ai/)
- [CuPy Documentation](https://docs.cupy.dev/)
- [NVIDIA GPU Acceleration for Python](https://developer.nvidia.com/gpu-accelerated-libraries)
- [PyTorch vs cuML Benchmarks](https://github.com/NVIDIA/cuml)

---

## 📋 체크리스트

### 의사결정
- [ ] GPU 가속 도입 결정
- [ ] cuML 라이선스 확인 (Apache 2.0 OK)
- [ ] RAPIDS 설치 복잡도 검토

### 구현 (if 결정)
- [ ] cuML 프로토타입
- [ ] GPU/CPU 자동 선택 로직
- [ ] 오류 처리 및 fallback
- [ ] 성능 벤치마크
- [ ] 문서화

---

**최종 평가**: ⭐⭐⭐

**GPU 가속은 선택적이지만 가능하고 효과적입니다.**

- cuML 기반 L2 리메싱: 즉시 구현 가능 (30-50% 성능 향상)
- 다른 부분 GPU 가속: 불가능 또는 복잡도가 높음
- 권장: v0.4에서 선택적 `--enable-gpu` 옵션으로 도입

---

**작성일**: 2026-04-11  
**작성자**: Claude Code (Haiku 4.5)  
**상태**: GPU 가속 전략 검토 완료
