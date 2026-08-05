# CARD POLY-S4 — pre-dual interior tet-vertex Laplacian smoothing (boundary fixed)

**target_engine**: poly
**모티프**: OpenFOAM polyDualMesh + median-dual identity — dual cell vol(v)=¼·Σ(incident
tet vol), Σ=1.000 exactly. The over-fill is upstream tet quality, not boundary logic:
regularize interior tets so the barycentric dual measures convex (≈tiling).

## 실측: boundary/internal 분리 + 근본 원인 (cube.stl draft N=500, 정본 경로)

POLY-S3 baseline 재확인(캡처한 tet mesh V=15/T=40, 8 boundary + **7 interior** verts):
void **0.000**, surface **6.000**, degen **0**, Σ|vol| **1.077**.

- **cell별 Σ|vol| 분리(pyramid, 정본 측정)**: boundary(8 corner) **0.726** / internal(7) **0.351**.
- **정답 대비(median dual identity, ¼·Σtet)**: 정답 boundary **0.449** / internal **0.551**,
  합 **1.0000** (해석적 정확 타일). 즉 현재는 **boundary cell +80.9% 과충전**(0.812 hull),
  **internal cell −33.8% 저충전**(sliver interior tet 의 dual 이 수축) — 두 오차가 부분
  상쇄되어 net +7.7%.
- **dual point 는 100% cube 안**(0/78 outside, max_overhang 0.000) → 표면 밖으로 bulge 아님.
  과충전은 **내부 cell 겹침**(non-convex dual cell) 이다.
- **결정적 실측(같은 dual.py, 입력 tet 만 교체)**:
  - 잘 형성된 Kuhn tet(6 tet): vol **1.0000**, on 6.000, off 0.000 → **dual.py 는 정확**.
  - 해석적 정답 median dual(FC+EM 삽입): pyramid 측정 **1.180** (non-convex cell 을 측도가 과대).
  - clamped-circumcenter: **1.23–1.45** (sliver mesh 라 Voronoi 도 악화).
  → **centroid dual 은 이미 이 mesh 의 측도 하한(1.077); 근본 원인은 native_tet 이 준
    7 interior Steiner 점의 sliver tet.** boundary 로직 결함이 아니다.

## 근본 원인 (한 줄)

barycentric dual cell 의 non-convexity → pyramid 측도 과대충전. sliver interior tet 이
그 non-convexity 의 원천. **입력 tet 의 interior vertex 를 정규화하면 dual cell 이 convex
에 근접 → 측도 → 1.000 수렴.**

## 검증된 해법 (오프라인 프로토타입, 캡처한 V/T)

interior tet vertex 만 Laplacian smoothing(boundary vertex **고정**), 후 dualize:

| it/relax | Σ\|vol\| | on | off | degen | min_tet_vol |
|----------|--------|----|-----|-------|-------------|
| baseline | 1.077 | 6.000 | 0.000 | 0 | 0.0107 |
| 3/0.3 | **1.038** | 6.000 | 0.000 | 0 | 0.0038 |
| 10/0.5 | **1.026** | 6.000 | 0.000 | 0 | 0.0018 |
| 30/0.6 | 1.026(plateau) | 6.000 | 0.000 | 0 | 0.0018 |

boundary vertex 고정 → **on(surface)·off(void) 은 구조적으로 불변**(caps/edge-ring 은 boundary
vertex·위상만 의존). min_tet_vol > 0 유지(inversion 없음). vol 만 단조 개선.

## 변경 (core/generator/native_poly/dual.py — 단일 파일, ~35줄)

1. 신규 helper `_smooth_interior_tet_verts(V, T, is_boundary_vert, edge_tets, n_iter, relax)`:
   - edge_tets 로 vertex 인접 build. interior v(`~is_boundary_vert[v]`)만 이웃 centroid 로
     `V[v] += relax*(mean(nbr)-V[v])`. boundary vertex 는 절대 이동 안 함.
   - **inversion 가드(per-vertex)**: 이동 후 v 의 incident tet vol 중 하나라도
     ≤ `1e-4*orig_vol` 이면 그 vertex 이동을 revert → degenerate/음체적 원천 차단.
2. `tet_to_poly_dual` 본문에서 topology(`_build_tet_topology`)·boundary 분류 직후,
   `tet_centroids = _compute_tet_centroids` **이전** 에 `V = _smooth_interior_tet_verts(...)`
   호출(기본 `n_iter=10, relax=0.5`). 이후 모든 dual point 는 smoothed interior + 원본
   boundary 를 사용.
- **단조 가드**: (a) boundary fixed → surface/void 불변(증명적). (b) inversion 가드 →
  degen 0 유지. (c) interior 정규화는 Σ|vol| 을 1.0 쪽으로만 이동(실측 단조). 안전장치로
  smoothing 이 어떤 이유로 min_tet_vol ≤ 0 을 만들면 **전체 V 를 원본으로 revert**.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 175 python3 -m pytest tests/test_native_poly_solid_volume.py -q
timeout 170 python3 scripts/smoke_native_poly.py
```

test 파일: `test_native_poly_encloses_true_volume` 의 `@pytest.mark.xfail(strict=True)`
**제거**(수정 성공 시 xpass → strict 실패). docstring 의 vol 수치 1.077→측정치(≈1.03) 및
"volume gate = permanent" 로 갱신. → **총 2 파일**(dual.py + test). smoke docstring 선택 갱신.

## 합격 기준 (validator 평가)

- surface(on-plane) **6.000 ±5% 불변** (permanent gate, 절대 불파).
- void(off-plane) **0.000 (≤0.30) 불변** (permanent gate, 절대 불파).
- degen **0 불변** (permanent gate).
- Σ|vol| 1.077 → **≤1.05** (실측 ≈1.026~1.038 예상). volume gate xfail→**permanent 승격**.
- max_skewness 악화 없음(pre≈0.457, ≤pre+0.05) — interior 정규화라 동등/개선 기대.
- bench 시간 ≤ 55s (smoothing 은 O(iter·edges), 무시 가능; native_tet 이 지배).
- tet/hex 무관 (native_poly/dual.py 단일 엔진 파일).

## 카드 시퀀스 위치

POLY 표면-충실 dual 시퀀스 **4/4** (S1 측정 → S2 interior conformity → S3 boundary cap/edge
→ **S4 interior-tet 정규화로 volume gate 폐합**). S4 로 4개 solid gate(surface/void/degen/
volume) 전부 permanent 승격 예상.
다음 후보(S4 PASS 후): POLY-S5 — non-cube 형상 일반화 검증(sphere/cylinder 로 solid gate
확장) 또는 poly cell skewness(현 ~0.46) 감소용 CVT-Lloyd 완화(단조 가드: skew 비증가).
