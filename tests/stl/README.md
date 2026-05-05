# WildMesh 벤치마크 STL

WildMesh 엔진을 난이도별로 테스트하기 위한 5종 STL 메시.

## 생성

```bash
python tests/stl/generate_benchmarks.py
```

의존: `trimesh`, `shapely`, `mapbox_earcut` (이미 사용자 환경에 설치됨).

## 파일

| 난이도 | 파일 | faces | vertices | watertight | 주요 특징 |
|-------|------|------:|---------:|:----------:|----------|
| **하** (easy) | `01_easy_cube.stl` | 12 | 8 | ✓ | 1×1×1 정육면체, convex, sharp 90° edge만 |
| **중** (medium) | `02_medium_cylinder.stl` | 512 | 256 | ✓ | 중공 실린더 (외경 1, 내경 0.3), genus-1, 곡면 |
| **상** (hard) | `03_hard_bracket.stl` | 416 | 204 | ✓ | L-브래킷 + 볼트홀 3개, 내각 90°, 얇은 벽(0.15) |
| **극상** (extreme) | `04_extreme_gear.stl` | 1040 | 512 | ✓ | 20톱니 기어 + 샤프트홀 + 허브홀 4개, sharp edge ~80개 |
| **초극상** (ultra) | `05_ultra_knot.stl` | 16,384 | 8,192 | ✓ | 트레포일 매듭 (3,2) torus knot, 고곡률 + 꼬임 |

## WildMesh 실측 결과 (draft quality, CLI 기준)

| 파일 | tetrahedralize | 총 시간 | cells | verdict | 비고 |
|------|---------------:|--------:|------:|:--------|------|
| 01_easy_cube | 1.2s | 1.7s | 5,745 | **PASS** | baseline |
| 02_medium_cylinder | 3.7s | 4.2s | 5,131 | **PASS** | 곡면 반영 양호 |
| 03_hard_bracket | 5.3s | 5.8s | 1,938 | **PASS_WITH_WARN** | non-ortho 83.5° (얇은 벽 영향) |
| 04_extreme_gear | 1.7s | 2.2s | 1,073 | **PASS_WITH_WARN** | non-ortho 82.8° (톱니 간극) |
| 05_ultra_knot | 17s+ | 17s+ | - | **FAIL** | WildMesh 실패, fallback 도 FAIL |

난이도 라벨이 실제 파이프라인 반응과 일치:
- 하/중: clean PASS
- 상/극상: 통과하되 non-ortho 경고
- 초극상: 기본 파라미터로 통과 불가 (3 iteration max 안에)

## 실행 예시

```bash
# CLI
python -m cli.main run tests/stl/01_easy_cube.stl \
    -o /tmp/out_easy --quality draft --tier wildmesh

# 더 어려운 초극상을 시도하려면 max_iterations 늘리고 epsilon 조정
python -m cli.main run tests/stl/05_ultra_knot.stl \
    -o /tmp/out_ultra --quality fine --tier wildmesh \
    --max-iterations 5
```

## 난이도 설계 기준

- **하**: convex + sharp edge 최소 (WildMesh baseline).
- **중**: 곡면 + genus≥1 (원통면 해상도 테스트).
- **상**: sharp internal corner + thin wall (epsilon 민감도 테스트).
- **극상**: 많은 sharp feature + 좁은 간극 (dedendum/허브 간 간섭).
- **초극상**: 고 resolution + 꼬임 + 고 genus (tetrahedralize 수렴성 한계).
