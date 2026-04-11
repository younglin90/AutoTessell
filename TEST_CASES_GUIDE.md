# 도전적 테스트 케이스 가이드

AutoTessell 파이프라인의 견고성을 검증하기 위한 **17개의 색다르고 힘든 테스트 입력**.

---

## 📋 테스트 케이스 목록

### 기본 케이스 (9개) — 각 단계별 기능 검증

| 파일명 | 크기 | 테스트 목표 |
|--------|------|-----------|
| `sphere_watertight.stl` | 63K | 기본 watertight 메시 (baseline) |
| `nonmanifold_disconnected.stl` | 184B | **L1 repair**: Non-manifold 분리 삼각형 처리 |
| `high_genus_dual_torus.stl` | 201K | **Strategist**: 높은 위상복잡도(genus=2) Tier 선택 |
| `degenerate_faces_sliver_triangles.stl` | 16K | **L2 remesh**: 매우 작은 면적(< 1e-4) 슬릿 처리 |
| `large_mesh_250k_faces.stl` | 4.0M | **Analyzer**: 대용량(81k 면) 자동 샘플링 |
| `mixed_features_wing_with_spike.stl` | 1.1K | **Generator**: 혼합 피처(판 + 스파이크) 호환성 |
| `very_thin_disk_0_01mm.stl` | 6.4K | **Generator fallback**: 극도로 얇은 구조(h=0.01) |
| `five_disconnected_spheres.stl` | 79K | **Preprocessor**: 다중 component 병합 |
| `external_flow_isolated_box.stl` | 684B | **Strategist**: External flow 감지 (도메인 크기) |

### 고급 케이스 (8개) — Edge case & 견고성 검증

| 파일명 | 크기 | 테스트 목표 |
|--------|------|-----------|
| `self_intersecting_crossed_planes.stl` | 284B | **Non-manifold 검사**: 자기 자신과 교차하는 표면 |
| `sharp_features_micro_ridge.stl` | 384B | **BL 파라미터**: 극단적 예각 피처(< 5도 angle) |
| `multi_scale_sphere_with_micro_spikes.stl` | 21K | **Remesh 강도**: 마이크로 스케일 피처 감지 |
| `highly_skewed_mesh_flat_triangles.stl` | 384B | **Evaluator skewness**: aspect ratio > 100 납작 삼각형 |
| `many_small_features_perforated_plate.stl` | 401K | **성능 테스트**: 64개 구멍이 있는 천공판 |
| `coarse_to_fine_gradation_two_spheres.stl` | 254K | **Generator**: LOD 혼합(조잡 + 미세 메시) |
| `extreme_aspect_ratio_needle.stl` | 1.7K | **BL 처리**: 극도로 긴 실 형상(길이 100배) |
| `mixed_watertight_and_open.stl` | 16K | **Repair 필요성**: 폐곡면 + 열린 판 혼합 |

### 기존 케이스 (9개)

| 파일명 | 크기 | 설명 |
|--------|------|------|
| `sphere.stl` | 63K | 기존 baseline |
| `sphere_20k.stl` | 1001K | 고해상도 구 |
| `naca0012.stl` | 32K | 항공기 날개 프로파일 |
| `trimesh_box.stl` | 684B | 간단한 상자 |
| `trimesh_duct.stl` | 6.4K | 덕트 파이프 |
| `hemisphere_open_partial.stl` | 7.6K | 열린 반구 |
| (기타) | - | ... |

---

## 🎯 실전 테스트 명령어

### 1️⃣ 각 Tier별 성능 비교
```bash
# Draft (TetWild) — 빠름 (~1초)
auto-tessell run tests/benchmarks/sphere_watertight.stl -o ./case_draft --quality draft
➜ 검증: polyMesh 생성 확인, 셀 수 < 5000

# Standard (Netgen/snappy) — 중간 (~분)
auto-tessell run tests/benchmarks/mixed_features_wing_with_spike.stl -o ./case_std --quality standard
➜ 검증: feature 처리, 셀 수 5k~50k

# Fine (snappyHexMesh) — 느림 (~30분+)
auto-tessell run tests/benchmarks/coarse_to_fine_gradation_two_spheres.stl -o ./case_fine --quality fine
➜ 검증: hex 메시 생성, BL 활성화 확인
```

### 2️⃣ Preprocessor 강건성
```bash
# Non-manifold 수리
auto-tessell run tests/benchmarks/nonmanifold_disconnected.stl -o ./case_nm

# Degenerate 면 처리
auto-tessell run tests/benchmarks/degenerate_faces_sliver_triangles.stl -o ./case_degen

# 다중 component 병합
auto-tessell run tests/benchmarks/five_disconnected_spheres.stl -o ./case_multi
```

### 3️⃣ Strategist 로직 검증
```bash
# Flow type 감지 (internal vs external)
auto-tessell run tests/benchmarks/extreme_aspect_ratio_needle.stl -o ./case_flow --dry-run
auto-tessell run tests/benchmarks/external_flow_isolated_box.stl -o ./case_ext --dry-run

# Tier 자동 선택 로깅
auto-tessell run tests/benchmarks/high_genus_dual_torus.stl -o ./case_genus --dry-run --verbose
```

### 4️⃣ Generator Fallback 강제 테스트
```bash
# 얇은 구조 → snappy fallback 유도
auto-tessell run tests/benchmarks/very_thin_disk_0_01mm.stl \
  -o ./case_thin --quality fine --max-iterations 1
➜ 기대: tier2_tetwild 실패 → tier1_snappy 성공

# Self-intersecting → fallback 체인
auto-tessell run tests/benchmarks/self_intersecting_crossed_planes.stl \
  -o ./case_si --max-cells 10000
```

### 5️⃣ 대용량 성능 테스트
```bash
# 250k 면 메시 샘플링 확인
time auto-tessell analyze tests/benchmarks/large_mesh_250k_faces.stl \
  --geometry-report ./geom.json

# 메모리 프로파일링
python3 -m memory_profiler -o memprof.txt \
  auto-tessell run tests/benchmarks/large_mesh_250k_faces.stl -o ./case_large
```

---

## 📊 평가 매트릭스

### 최소 성공 기준 (P0)
```
✅ 모든 케이스에서:
   - 파이프라인 완료 (crash 없음)
   - polyMesh 생성 또는 명확한 실패 메시지
   - 모든 tier fallback 예상대로 동작
```

### 고급 검증 (P1+)
```
🎯 대용량 메시:
   - Analyzer 샘플링: < 1초
   - Preprocessor L2: < 10초
   - 메모리 사용 < 2GB

🎯 특수 케이스:
   - Non-manifold: L1 repair PASS/FAIL 결과 명시
   - Degenerate: remesh 후 face_area > threshold
   - Self-intersecting: fallback tier 기록
```

---

## 🔧 생성 방법

기존 파일들 재생성:
```bash
python3 scripts/generate_test_cases.py      # 기본 9개
python3 scripts/generate_advanced_test_cases.py  # 고급 8개
```

---

## 💡 활용 팁

1. **CI/CD 통합**: `safeguard-regression` 확대
   ```makefile
   # Makefile에 추가
   .PHONY: test-challenge-cases
   test-challenge-cases:
       @for f in tests/benchmarks/{nonmanifold,high_genus,large_mesh}*.stl; do \
           auto-tessell run "$$f" -o /tmp/test_case || exit 1; \
       done
   ```

2. **성능 프로파일링**: 느린 케이스 식별
   ```bash
   for f in tests/benchmarks/*.stl; do
       echo "Testing: $$f"
       time auto-tessell run "$$f" -o /tmp/perf_test --quality draft
   done | tee perf_results.txt
   ```

3. **회귀 테스트**: 안정적 케이스로 baseline 구축
   ```bash
   # 각 변경 후
   pytest tests/ -k "benchmark" -v
   ```

---

## 📝 로그 분석

각 테스트의 출력 파일:
```
case/
├── mesh_strategy.json      # Tier 선택 결과
├── quality_report.json     # 평가 결과 (PASS/FAIL)
├── constant/polyMesh/      # 생성된 메시
└── _work/preprocessed.stl  # 전처리 후 표면
```

핵심 로그:
```json
{
  "tier_auto_selected": {
    "tier": "tier1_snappy",
    "quality_level": "fine",
    "fallbacks": ["tier15_cfmesh", ...]
  },
  "verdict": "PASS",
  "hausdorff_relative": 0.015,
  "num_cells": 45000
}
```

---

**총 17개 케이스로 draft부터 fine까지, baseline부터 edge case까지 완전 커버! 🎉**
