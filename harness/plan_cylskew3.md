# CARD CYLSKEW3 (beta2830) — offset-ring monotone best-of-two selector (sphere가 default-ON을 실측 반증)

**target_engine**: tet
**모티프**: Garimella & Shashkov 2003 §3 offset-surface node placement — 형상별 채택을 monotone dominance 로 결정 (per-vertex 필터 대체)

## 실측 결론 — 필터 가설 최종 판정 + default-ON 반증

정본 프로토콜(`bench_native_tet_matrix.py` worker, P4C=0, sphere.stl R=1.0, 642 verts,
순수 곡면·z-ring 다수·측벽정점 실재 |nz|<0.3 비율 29%). flag OFF/ON 실측:

| N | ring | cells | skew | nonOrt | wall_dev_max | area_r | vol_r | neg | degen | verdict |
|---|------|-------|------|--------|-------------|--------|-------|-----|-------|---------|
| 500 | OFF | 1280 | 1.46 | 10.6 | **0.000** | 1.0000 | 1.0000 | 0 | 0 | PASS |
| 500 | **ON** | 5643 | 2.44 | **79.7** | **0.000** | 1.0000 | 1.0033 | 0 | 0 | PASS |
| 1000 | OFF | 1458 | 2.60 | 87.1 | **0.000** | 1.0000 | 1.0012 | 0 | 0 | PASS |
| 1000 | **ON** | 5825 | 2.25 | 83.3 | **0.000** | 1.0000 | 1.0074 | 0 | 0 | PASS |

**세 가지 확정 사실:**
1. **표면·solid 4불변식은 모든 구성에서 무손상** — wall_dev_max 정확히 0.000, area_ratio
   1.0000, vol_ratio 1.00~1.007, degen 0, neg_vol 0. offset ring 은 sphere 에서도 표면
   보존·solid 안전(최우선 가드 통과).
2. **품질 효과는 형상·N 의존이며 범용 이득 아님.** cylinder(z-ring 2개)는 명확한 개선
   (skew 44.9→40.8). sphere N=500 은 명확한 **퇴행**(nonOrt 10.6→79.7 +69°, skew
   1.46→2.44, cells 4.4x). N=1000 은 미미한 개선(skew 2.60→2.25). 즉 무조건 삽입은
   dense 곡면에서 유해.
3. **원인**: ring 은 표면정점 1개당 내향 seed 1개를 무조건 삽입 → sphere 642 seed →
   near-wall 조밀 shell 이 Delaunay boundary tet 을 악화(nonOrt 폭발), cell 4.4x 팽창.

**판정 — 필터 가설(측벽 |nz| 등 per-vertex 클래스 필터)은 최종 기각.** CYLSKEW2 가
cylinder 에서 |nz| 필터는 퇴행함을 실증했고, sphere 는 문제가 vertex-class 가 아니라
**seed 밀도의 holistic 효과**임을 보인다(어떤 정점 부분집합 규칙도 근거 없음). 대신 실측이
직접 지지하는 것은 **형상별 채택 결정**이다.
**default-ON 은 위험(반증됨)** — sphere N=500 을 nonOrt 10.6→79.7, cells 4.4x 로 회귀시킴.
default 전환은 반드시 monotone 가드 뒤에 와야 함.

## 이론적 근거 (≤30줄)

- **문제 정의**: seed 집합 S 를 채택할지는 결과 mesh 품질 q(S) 가 q(∅) 를 악화시키지
  않을 때에만 True 여야 한다(monotone dominance). q = (max_skew, max_nonOrtho) 벡터.
  채택 규칙: keep(S) ⟺ skew(S) ≤ skew(∅)+τ_s ∧ nonOrt(S) ≤ nonOrt(∅)+τ_n.
- **핵심 아이디어(수식·helper)**: 순수 selector `select_offset_ring_variant(seeds,
  off_metrics, on_metrics, skew_tol, nonortho_tol)` → 두 스칼라쌍 비교로 seeds 또는
  빈 배열 반환. mesher 가 OFF/ON 두 mesh 를 재고 이 helper 로 최종 채택 — 그 caller 는
  다중·고비용이라 **이번 카드는 helper 스켈레톤(caller 없음, default OFF)**.
- **기존 코드와 차이**: 현재 `offset_ring.py` 는 seed 를 무조건 all_pts 에 vstack(가드
  없음). 이 helper 는 채택 결정 로직을 분리·형식화(아직 미연결 → 회귀 0).
- **레퍼런스**: Garimella 2003 §3(collision/spacing), harness roadmap CYLSKEW4(best-of-two).
- **혁신성**: novelty 2(dead per-vertex 필터를 monotone per-geometry 채택으로 교체) /
  rigor 3(dominance 가드가 실측 3케이스 결정을 전부 재현: cyl keep, sph N500 revert,
  sph N1000 keep) / impact 2(safe default-ON 경로 해금) = **7**.
- **검증(수기)**: cyl(40.8≤44.9)→keep✔ / sphN500(2.44>1.46, 79.7>10.6)→revert✔ /
  sphN1000(2.25≤2.60, 83.3≤87.1)→keep✔. 세 실측을 모두 정확히 재현.

## 변경

- 파일: `core/generator/native_tet/offset_ring.py` (단일 파일, ≤35줄 추가)
- 함수(신규): `select_offset_ring_variant(seeds, off_metrics, on_metrics,
  skew_tol=0.0, nonortho_tol=2.0)` (파일 말미)
- 핵심 변경:
  1. 두 metric dict(`{"skew":..,"nonortho":..}`) 를 받아 dominance 판정.
  2. keep ⟺ `on.skew ≤ off.skew+skew_tol AND on.nonortho ≤ off.nonortho+nonortho_tol`.
     True → `seeds` 반환, False → `zeros((0,3))` 반환 + `info["decision"]`.
  3. 결측/NaN metric 은 안전측(revert=빈배열)로 폴백. **caller 미연결, default OFF**.
- 단조 가드: helper 자체가 dominance 가드. caller 없음 → mesher 경로·모든 벤치 형상
  출력 완전 불변(회귀 0). cylinder ON 경로(2296/40.8)·OFF 경로(1847/44.9) 불변.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 90 python3 tests/test_native_tet_solid_volume.py
timeout 60 python3 -m pytest tests/test_native_tet_offset_ring_select.py -q
```

(신규 unit test: 실측 3케이스 표를 그대로 넣어 keep/revert 결정을 assert.)

## 합격 기준 (validator 가 평가)

- 회귀 PASS (`test_native_tet_solid_volume.py` — cube 4불변식 무변화).
- 신규 selector unit test PASS: cyl→keep, sphN500→revert, sphN1000→keep 세 결정 재현.
- **caller 미연결 → mesher 경로 출력 완전 불변**: cube/cylinder/dual_torus/perforated/
  sharp_ridge/naca **회귀 절대 금지**(=0.0). offset ring OFF 가 여전히 default.
- wall_dev_max / solid 4불변식: helper 는 mesh 를 건드리지 않으므로 자명 보존.
- bench 시간 ≤ 기존(회귀 0, 순수 helper 추가).

## 카드 시퀀스 위치

- CYLSKEW 시퀀스(offset ring → default ON) 5개 중 **3번째**.
  1(CYLSKEW1)=스켈레톤 훅 ✅ / 2(CYLSKEW2)=scale-invariant 상대가드 ✅ /
  **3(본 카드)=monotone best-of-two selector 스켈레톤 + sphere 로 default-ON 반증** /
  4=selector 를 mesher 에 연결(OFF/ON 2회 mesh 후 채택, 다중·고비용 별도 카드) /
  5=selector-gated default ON + 합격 기준 강화.
- **다음 카드 후보(본 카드 PASS 후)**: CYLSKEW4 — `select_offset_ring_variant` 를
  mesher.py 훅에 연결(ring OFF/ON 두 번 mesh → helper 로 낮은-skew 채택). cylinder 는
  ON 채택(40.8), sphere N500 은 OFF 로 revert 되는지 정본 실측으로 확인.
