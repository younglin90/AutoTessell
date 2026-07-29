# CARD CYLSKEW4 (beta2831) — selector 를 seeding 훅에 연결 (cheap raw-Delaunay proxy best-of-two, 기존 env 게이트 유지)

**target_engine**: tet
**모티프**: Garimella & Shashkov 2003 §3 offset-surface node placement + CYLSKEW3 monotone selector 를 caller 에 연결

## 실측 — full best-of-two 비실용성 확정 (이 카드 scope 를 결정)

정본 프로토콜(P4C=0), 내부 `generate_native_tet` elapsed 측정:

| shape | full mesh 1회 | full best-of-two(=2회) | 판정 |
|-------|--------------|------------------------|------|
| cylinder(N=2000) | 1.75s | ~3.5s | 허용 |
| sphere(N=1000) | **42.8s** | **~86s** | bench +15% 초과 |

**핵심 결론**: seeding 훅(line 867)은 `generate_native_tet` 최상단이라, 여기서 OFF/ON
"두 번 full mesh 후 선택" 구조는 downstream 42s 파이프라인을 형상마다 2배로 돌린다 →
tet 레인 bench 59s→~110s+, **bench +15% 가드 즉시 위반**. default-ON 을 full best-of-two
로 여는 길은 **닫혀 있음(실측 반증)**.
→ 실현 가능한 유일 경로는 task 가 제시한 대안: **seeding 단계에서 OFF/ON 두 seed set 만
만들고 각각에 값싼 raw-Delaunay(수 ms) 만 돌려 proxy metric 으로 선택**, 그 뒤 full
pipeline 은 **선택된 seed set 으로 1회만** 실행. 추가 비용 ≈ 값싼 Delaunay 2회 + proxy 2회.

## 이론적 근거 (≤30줄)

- **문제 정의**: 채택 결정 q(S)≤q(∅) 을 full-mesh 비용 없이 근사. proxy metric
  q̃(S)=(skew̃, nonOrt̃) 를 raw Delaunay tet 에서 계산해 selector 에 공급.
  keep(S) ⟺ skew̃(S)≤skew̃(∅)+τ_s ∧ nonOrt̃(S)≤nonOrt̃(∅)+τ_n.
- **핵심 아이디어(알고리즘 단계)**:
  1. env=1 훅에서 `off_pts=all_pts`, `on_pts=vstack(all_pts, offset_ring)` 두 후보 구성.
  2. 각 후보에 `scipy.spatial.Delaunay`(파이프라인 이미 사용중) 로 raw tet 생성 — 수 ms.
  3. 기존 `_skew_proxy(pts,tets)` + 신규 `_nonortho_proxy(pts,tets)` 로 q̃ 계산.
  4. `select_offset_ring_variant(offset_pts, off_metrics, on_metrics)` 로 채택 seeds 결정.
  5. `_offset_ring_pts` = selector 결과(채택 pts 또는 빈배열) → 기존 vstack 줄이 소비.
- **기존 코드와 차이**: CYLSKEW1 훅은 offset seed 를 **무조건** vstack. 본 카드는
  selector 게이트를 통과한 경우에만 vstack — CYLSKEW3 helper 의 **최초 caller**.
- **레퍼런스**: Garimella 2003 §3, CYLSKEW3(`offset_ring.py` selector), roadmap CYLSKEW4.
- **미해결 개방 문제(정직)**: raw Delaunay(표면회복·최적화 前) proxy 가 CYLSKEW3 이 보정한
  **최종 evaluator** metric 과 상관하는지 미검증. → default-ON 은 이 카드에서 하지 않고,
  이 카드는 **env=1 경로에서 selector 결정·proxy metric 을 계측/로깅**해 상관성 자체를
  측정한다. 상관 확인되면 CYLSKEW5 가 default-ON, 아니면 full best-of-two + cost-gate 로 pivot.
- **혁신성**: novelty 2(selector 최초 연결 + cheap-proxy best-of-two) / rigor 2(default-OFF
  → 회귀 0 + solid 4불변식 보존, 상관성은 계측으로 이연) / impact 2(default-ON 경로 계측 해금) = **6**.

## 변경

- 파일: `core/generator/native_tet/mesher.py` (단일 파일, ≤60줄)
- 함수: (신규) `_nonortho_proxy(pts, tets)` — `_skew_proxy` 옆(line ~166), internal
  face own/nbr 중심선과 face normal 사이 각(도) 최대값. `_skew_proxy` 의 face-map 구조 재사용(~25줄).
- 훅(line 866–872) 재작성:
  1. env≠1 → 현행과 **완전 동일**(무변경, `_offset_ring_pts` 빈배열) → 회귀 0.
  2. env=1 → off/on 두 seed set, 각 raw `Delaunay`, `_skew_proxy`+`_nonortho_proxy` 계산,
     `select_offset_ring_variant` 호출, 결정된 seeds 를 `_offset_ring_pts` 에 대입.
  3. `log.info("native_tet_offset_ring_select", decision=.., off_skew=.., on_skew=..,
     off_nonortho=.., on_nonortho=..)` — 상관성 측정용 계측.
- 단조 가드: (a) default(env unset) 경로 byte-identical → 모든 벤치 형상 회귀 0.
  (b) env=1 경로에서 selector revert 시 `_offset_ring_pts` 빈배열 → OFF 와 동일 seed →
  결과 OFF 와 동일. keep 시에만 offset seed 삽입(현행 ON 과 동일 downstream). Delaunay
  실패/NaN proxy → 안전측 revert(빈배열).

## 검증 명령 (unit_tester 가 그대로 실행, 각 ≤3분)

```bash
timeout 90  python3 -m pytest tests/test_native_tet_offset_ring_select.py -q
timeout 90  python3 tests/test_native_tet_solid_volume.py
timeout 120 python3 scripts/smoke_native_cylinder.py                    # default 경로 불변: skew 44.9
AUTO_TESSELL_TET_OFFSET_RING=1 timeout 120 python3 scripts/smoke_native_cylinder.py   # env=1 계측
timeout 150 python3 scripts/bench_native_tet_matrix.py --stl tests/benchmarks/sphere.stl   # default sphere 불변
```

## 합격 기준 (validator 가 평가)

- 회귀 PASS: `test_native_tet_solid_volume.py`(cube 4불변식), selector unit(CYLSKEW3) 불변.
- **default(env unset) 경로 완전 불변**: cylinder skew 44.9/nonOrt 89.2/1851 cells 재현,
  sphere PASS(skew 2.62, area_r 1.0, vol_r 1.008, degen 0, neg 0) 재현 — 회귀 0.
- env=1 경로: 에러 없이 완주 + `native_tet_offset_ring_select` 로그에 decision+proxy metric 출력.
  solid 4불변식(wall_dev, area_r, vol_r, degen, neg) 무손상(seed set 무관 downstream 안전).
- bench 시간: default 경로 무변 → tet 레인 ≤ 기존(회귀 0). env=1 은 값싼 Delaunay 만 추가.
- **품질 개선 주장 없음** — proxy↔final 상관성은 이 카드가 계측만; default-ON 은 CYLSKEW5.

## 카드 시퀀스 위치

- CYLSKEW 시퀀스(offset ring → default ON) 5개 중 **4번째**.
  1=스켈레톤 훅✅ / 2=scale-invariant 가드✅ / 3=monotone selector 스켈레톤(sphere 로
  default-ON 반증)✅ / **4(본 카드)=selector 최초 연결(cheap raw-Delaunay proxy best-of-two,
  env 게이트 유지, default 회귀 0, 상관성 계측)** / 5=proxy 상관 확인 시 default-ON.
- **다음 카드 후보(본 카드 PASS 후)**: CYLSKEW5 — env=1 로그의 cheap-proxy 결정이 최종
  metric 결정(cyl keep / sph revert)과 일치하면 `AUTO_TESSELL_TET_OFFSET_RING` 을 selector-
  gated default ON 으로 전환 + 합격 기준(cyl skew↓, sph 불변) 강화. 불일치면 full
  best-of-two 를 저비용 형상(mesh<5s)에만 적용하는 cost-gated 경로로 pivot.
