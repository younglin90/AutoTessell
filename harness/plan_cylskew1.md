# CARD CYLSKEW1 (beta2822) — near-wall offset-ring seeding (skeleton/진단, default OFF)

**target_engine**: tet
**모티프**: Garimella & Shashkov 2003 §3 — offset-surface node placement / advancing-layer 시드

## Garimella 기법 조사 요약 (offset ring)

- Garimella 2003 은 점성유동 BL 메쉬를 위해 벽 노드를 **smoothed vertex normal** 을
  따라 안쪽으로 제어된 거리만큼 **offset** 시켜 표면과 평행한 층(layer)들을 만든다.
  각 층은 `p = v − δ·n̂` (n̂ = 각도가중 내향 정점법선, δ = 층 두께). 층 전진 중
  **collision/gap** 을 검출해 병합한다 (native_bl.py:468 각도가중 vnorm 이 이미 이 방식).
- 본 문제 적용: cylinder.stl 측벽 z-ring 이 2개뿐(z=±0.5)이라 벽-순응 boundary face 가
  전체 높이를 덮는 flat cap → σ_b = tangential / normal_dist, normal_dist≈h/4 미소 →
  bskew 44.9 폭발. R-c7 에서 volume-only local op(flip/split/re-smooth) 3노선 전부 실측
  기각. 남은 유일 경로 = **벽 근처 내부점 삽입**(offset ring).

## 이론적 근거

- **문제 정의**: boundary skew σ_b(f) = ‖fc − proj‖ / |nd|, nd = (fc−cc_own)·n̂ (mesher.py
  _skew_proxy:146-163 과 동일). 측벽 flat cap 은 nd→h/4 로 작아 σ_b 폭발. 현 엔진은
  측벽 내부에 시드가 없어 Delaunay 가 full-height cap tet 을 만든다.
- **본 카드 핵심 아이디어** (Card 1 = 삽입 메커니즘 안전성만):
  1. 새 파일 `offset_ring.py`: 측벽 표면정점 v_i 마다 내부 후보 p_i = v_i − δ·n̂_i
     (n̂_i = 각도가중 내향법선, δ = 0.5·L, L=target_edge_length) 를 생성.
  2. **거부 가드 2종**: (a) winding-number inside 아니면 버림, (b) 기존 시드와
     min-dist < 1e-6 면 버림 → 중복/외부점 원천 차단.
  3. **훅 위치 = seeding 단계뿐** (mesher.py:862, Steiner 블록 직후·seed 로그 직전):
     후보를 `all_pts` 에 vstack 후 Delaunay. 표면 lock/envelope/clip 하류 로직은
     **한 줄도 안 건드림** — 점은 단지 Delaunay 시드가 더 늘 뿐.
  4. **default OFF** (env `AUTO_TESSELL_TET_OFFSET_RING`) → cube 회귀 정확히 0.
- **수렴/안전 보장**: p_i 는 δ>0 내향 + winding-inside 이므로 watertight+clip 메쉬의
  경계정점이 될 수 없다(strictly interior). 이 카드는 그 명제를 **실측 진단**한다:
  로그 `n_offset_inserted>0`, `n_became_boundary==0` 을 emit(하류 clip 후 경계 포함 여부).
  Card 1 은 skew 개선 목표 아님 — 개선(중간-z 분포·envelope 통합)은 후속 카드.
- **레퍼런스**: Garimella & Shashkov 2003 §3; native_bl.py:468 (각도가중 vnorm);
  mesher.py:832-863 (seeding), :146-163 (_skew_proxy).
- **혁신성 평가**: novelty 2 (BL offset-ring 을 tet skew 격파에 신규 적용) /
  rigor 2 (winding-inside + min-dist 가드 + 경계-소속 진단) /
  impact 2 (44.9 미만으로 가는 유일 생존 경로 개통). 합 = 6 (≥5).

## 변경

- **신규 파일**: `core/generator/native_tet/offset_ring.py` (~55줄)
  - `offset_ring_seed_points(V, F, target_edge_length, depth_frac=0.5) -> (P, info)`:
    1. 각도가중 내향 정점법선 계산 (native_bl.py:468 패턴 재사용, 부호는 centroid 향).
    2. 측벽 후보 = 표면정점 전부(측벽 판정은 후속 카드; Card 1 은 전 정점 대상 후
       winding-inside 로 자동 필터). p_i = v_i − depth_frac·L·n̂_i.
    3. 거부: winding-outside, min-dist<1e-6. `info={n_cand,n_inserted,min_dist}`.
- **훅**: `core/generator/native_tet/mesher.py` seeding 단계 (~line 862, 함수
  `generate_native_tet`, Steiner 블록 직후) — ~12줄:
  ```
  if os.environ.get("AUTO_TESSELL_TET_OFFSET_RING") == "1":
      P, info = offset_ring_seed_points(V, F, float(target_edge_length))
      if P.shape[0]: all_pts = np.vstack([all_pts, P])
      log.info("native_tet_offset_ring", **info)
  ```
- **단조 가드**: default OFF → cube/전체 회귀 바이트 동일. ON 이어도 하류 로직 불변
  (점은 Delaunay 시드 추가일 뿐, envelope/clip/surface-lock 그대로 실행).
  경계-소속 진단 로그로 "삽입점이 경계로 새지 않음" 을 실측 확인.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
# 1) default OFF — cube solid 4불변식 정확히 유지 (회귀 0)
timeout 90 python3 -m pytest tests/test_native_tet_solid_volume.py -q
# 2) flag ON — cube 4불변식 여전히 PASS (삽입 메커니즘 안전 증명)
AUTO_TESSELL_TET_OFFSET_RING=1 timeout 90 python3 -m pytest tests/test_native_tet_solid_volume.py -q
# 3) flag ON — cylinder wall_dev/불변식 악화 없음 + 삽입 로그 관찰
AUTO_TESSELL_TET_OFFSET_RING=1 timeout 120 python3 scripts/smoke_native_cylinder.py
```

## 합격 기준 (validator 가 평가)

- (1) default OFF: solid 4 gates PASS (surface 6.000 / off≈0 / vol 1.00x / degen 0),
  cube 결과 pre==post (회귀 0).
- (2) flag ON on cube: **동일 4 gates PASS** — 삽입점이 void/degenerate/표면손상 유발 X.
- (3) flag ON on cylinder: `wall_dev_max == 0.000` (완전정확 유지, 최우선 원칙),
  skew 변화 없어도 됨 → **skew ≤ 45.0** 회귀 가드만. 로그에서 `n_inserted > 0`,
  `n_became_boundary == 0` 확인 (삽입 메커니즘이 표면보존을 안 깬다는 실측 증명).
- bench 시간 ≤ 기존 +15% (default OFF 이므로 사실상 불변).
- BL 영향 없음 (기본 경로 OFF).

## 카드 시퀀스 위치

- 시퀀스: "near-wall offset-ring interior insertion" (Garimella 2003 §3) — 총 ~4카드 예상.
  - **CYLSKEW1 (본 카드, 1/4)**: seeding-only 삽입 + 안전성 진단 (default OFF).
  - CYLSKEW2 (2/4): 측벽 판정(surface normal ⟂ z-axis) + 중간-z 분포로 후보 제한,
    flag ON 유지, skew 하강 관찰.
  - CYLSKEW3 (3/4): 단조 가드 강화 — post-mesh bskew pre/post 비교, 악화 시 revert.
  - CYLSKEW4 (4/4): default 활성 + skew < 44.9 합격 기준 강화.
- **다음 카드 후보** (CYLSKEW1 PASS 후): CYLSKEW2 — 측벽 필터 + 중간-z offset ring 분포.
