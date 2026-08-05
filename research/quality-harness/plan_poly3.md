# CARD POLY-S3 — boundary-cell dual: on-plane caps + topological boundary-edge faces

**target_engine**: poly
**모티프**: OpenFOAM polyDualMesh boundary treatment — 경계 vertex 의 dual cell 을
surface cap(경계면 위) 과 boundary-edge separating face(인접 경계 cell 간 공유) 로
위상적으로 닫는다. POLY-S2 가 interior edge 에 한 것을 boundary edge 로 확장.

## 실측 위치 추적 (cube.stl draft N=500, 정본 경로)

Baseline 재확인: `POLY N=500 cells=15 ... void 2.435BAD vol 1.119BAD degen 0ok` (47.6s).
파이프라인이 dual 에 넘기는 실제 tet mesh 를 monkeypatch 로 덤프: V=15(8 corner=boundary,
7 internal), T=40, boundary tri 12, 표면적 6.000, bbox [-0.5,0.5]^3.

- **void 2.435 위치**: off-plane 경계면 84개 전부 **boundary cell(owner 0-7)의 삼각형 cap**.
  최근접 평면까지 거리 0.33(deep, 표면 아님), centroid chebyshev 0.38. deep(≥0.2) 영역이
  1.68, 근접(<0.05) 0.40. → **deep interior 가 아니라 boundary cell 이 내부를 향해 뱉은
  가짜 cap**. dual.py 의 `is_cap = any(lv >= n_tet_pts)` (line 447) 가 surface 점을 하나라도
  포함한 hull face 를 전부 cap 으로 오분류 → `b_b_faces`(line 527-533)로 one-sided 방출.
  동일 `is_cap` 집합을 CCW 정렬 면적으로 재분리: **on-plane=6.000(진짜 cap), off-plane=2.435(누출)**.
- **vol 1.119 위치**: boundary cell 합 0.768 / internal 0.351. 과충전 주체는 boundary cell.
  추가로 인접 두 boundary cell 이 **surface edge 를 가로질러 공유해야 할 내부면이 아예
  생성 안 됨**(line 511 이 boundary edge 를 skip) → 그 방향으로 cell 이 열려 pyramid 부피가
  샌다.

## 근본 원인 (2개, 둘 다 dual.py boundary 로직)

1. **cap 과분류**: `is_cap = any(surface point)` → 내부를 향한 hull face 까지 boundary 로
   방출. 진짜 surface cap 은 "모든 정점이 한 입력 평면 위"인 face 뿐(=6.000).
2. **boundary-edge 내부면 누락**: interior edge 는 POLY-S2 edge-ring 으로 공유되지만
   surface edge(인접 boundary cell 경계)는 line 511 에서 skip → 그 내부면이 없다.

## 카드 변경 (core/generator/native_poly/dual.py — 단일 파일, ~45줄)

1. **dual point 안정 id 등록** (tet_point_id 직후, ~6줄): boundary face centroid →
   `bface_pid[tri]`, boundary edge midpoint → `bedge_pid[e]` 를 `_add_point` 로 미리 등록.
2. **on-plane cap 필터** (`b_b_faces` 루프 527-533, ~8줄): `surface_planes` 를 이 지점 위로
   이동 후, 각 cap face 의 `dual_points[f]` 가 어떤 입력 평면 위(모든 정점 |n·p+d|<1e-6)일
   때만 `b_b_faces` 에 추가. off-plane 은 버린다(내부는 edge-ring/boundary-edge 로 커버됨).
3. **boundary-edge separating face** (신규 루프, ~22줄): 각 `e in boundary_edges_set` 에서
   양 끝 cell 이 존재하면 `_ordered_tet_ring(e)`(open fan) 로 ring 획득, e 를 공유하는
   boundary tri 2개(t_a,t_b) 를 찾아 face = `[bface_pid[t_a]] + [tet_point_id[ring]] +
   [bface_pid[t_b], bedge_pid[e]]` (순서유지 dedup) 구성 → `b_i_faces/b_i_own/b_i_nbr` 에 추가.

- **단조 가드**: 기존 `_area_split` 가드(pre=path A / post=path B, line 536-544) 유지.
  path B 의 post_off 가 0 이 되고 on 은 6.000 로 보존되므로 `use_topo=True` 유지되며,
  만약 어떤 mesh 에서 on-plane 필터가 표면 coverage 를 깨면(post_on < 0.95·pre_on) 가드가
  자동으로 path A(무변경)로 복귀 → **worst-case 안전**. path A 코드는 손대지 않음.

## 실측 검증 (오프라인 프로토타입, 캡처한 V,T)

| 변형 | on | off | Σ\|vol\| | degen |
|------|----|-----|--------|-------|
| baseline (현행 path B) | 6.000 | 2.435 | 1.119 | 0 |
| on-plane cap 필터만 | 6.000 | 0.000 | 0.843 | 0 |
| + boundary-edge face | **6.000** | **0.000** | **1.049** | **0** |

두 변경 모두 필요(필터만 하면 cell 이 열려 vol 0.843 로 저충전). 둘 다 적용 시 목표 충족.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 170 python3 scripts/smoke_native_poly.py
timeout 175 python3 -m pytest tests/test_native_poly_solid_volume.py -q
```

두 번째 파일의 void/vol `xfail(strict=True)` 마커를 **영구 gate 로 승격**해야 한다
(수정 성공 시 xpass → strict 실패). 같은 카드에서 test 2개(`test_native_poly_has_no_interior_voids`,
`test_native_poly_encloses_true_volume`)의 `@pytest.mark.xfail` 제거 + docstring MEASURED
수치 갱신. → **총 2 파일**(dual.py + test 파일). smoke docstring 수치는 선택 갱신.

## 합격 기준 (validator 평가)

- surface(on-plane) 6.000 ±5% **불변** (permanent gate, 절대 불파).
- void(off-plane) 2.435 → **≤1.0** (실측 0.000 예상).
- Σ|vol| 1.119 → **≤1.05** (실측 1.049 예상).
- degen 0 **불변**.
- bench 시간 ≤ 55s (추가 연산은 boundary edge 루프뿐, 무시 가능).
- tet/hex 무관 (native_poly/dual.py 단일 엔진 파일만 수정).

## 카드 시퀀스 위치

POLY 표면-충실 dual 시퀀스의 3번째(POLY-S1 measurable → S2 interior edge-ring →
**S3 boundary cap/edge**). S3 로 4개 solid gate 전부 통과 예상.
다음 후보: POLY-S4 — poly cell skewness(현 2.05) 감소용 boundary-cell Laplacian/centroid
smoothing(단조 가드: skew 비증가) 또는 non-cube 형상 일반화 검증.
