# CARD BETA2829 (beta2829) — flat cap-tet detector (near-wall resolution seq #1, skeleton)

**target_engine**: tet
**모티프**: Garimella 2003 near-wall layer + fTetWild §3.4 — 곡면벽 boundary skew 의
근본원인은 *flat cap tet* (벽면에 3정점, 내부정점이 거의 공면) 이고, 이는 seeding
under-resolution 문제 → local op 로 못 고침. 이번엔 그 진단자만 (read-only, gate OFF).

## 이론적 근거 (전부 이번 라운드 실측 — 정본 smoke + scoped stash, 모두 revert 완료)

- **문제 정의**: CYL 잔여 skew=44.9 는 **전부 boundary** skew (internal max=4.64 로 무해).
  worst 셀 (예 1143): boundary face 1개(벽 3정점), 4th 정점 r-range=0.0096 로 벽에 근접
  → normal_dist=0.00186. boundary skew = |tangential_miss| / normal_dist (checker 762-779).
  유도: cap tet {a,b,c(벽), d} → normal_dist = |(d-a)·n|/4 = height(d over wall)/4.
  d 가 벽에 붙어(height 0.0074) normal_dist 미소 → skew 폭발. **곡면벽 under-resolution.**
- **BETA2828 의 후속 BETA2829(flip) 은 죽었다 — 3방향 실측 반증** (모두 mesher.py 임시패치
  → git checkout revert):
  1. post-smooth flip_edges_32+flip_faces_23, thr=1e-4(quality): skew 44.944→**44.944 불변**,
     neg tet 54→192↑. quality-gate 가 skew-slivers 를 안 건드림.
  2. thr=-1.0(any valid): skew→**2.1e15 폭발**, neg 54→856. relative-inv guard 가 revert.
  3. orientation-normalize 후 재시도: 동일 (skew 44.944 불변). in-memory 54 neg-order 정규화도
     무효. ⇒ flip 은 flat cap 을 위상적으로 제거 불가 (BETA2828 카드의 BETA2829 노선 폐기).
- **boundary-edge split 도 죽었다 — 실측**: 벽면 tall edge (양끝 표면·midpoint on-surface,
  bvh dist=0 → wall_dev 0 유지) 를 split (fresh Envelope, n_split=24): skew 44.944→**67.2 악화**;
  2-pass(n=62)→**78.4 더 악화**. flat cap 을 쪼개면 더 작은 flat cap 만 늘어 normal_dist 안 늚.
- **입력면 실측**: cylinder.stl 측벽 z-ring 이 **2개뿐**(z=±0.5, 64 side verts), 측면 64 face
  전부 full-height. ⇒ 벽 conforming tet 이 구조적으로 full-height cap → skew 44.9 는 입력면이
  강제. volume-only local op 으론 불가, **near-wall 내부점 삽입(offset ring)** 이 필요.
- **레퍼런스**: checker 762-779(bskew), 698-721(iskew); mesher.py:2150-2229(BETA2828 최종블록,
  삽입지점 2229 직후); Garimella 2003 §3(near-wall layer); fTetWild §3.4.
- **혁신성**: novelty 2(roadmap 을 실측으로 재정향 + 새 진단자) · rigor 3(공식유도 normal_dist
  =height/4 + 3방향 dead-end 실측) · impact 2(다음 활성카드의 정확한 표적 확정). 합=**7**.

## 변경 (단일 파일, ≤55줄, gate OFF = 회귀 0)

- 파일: **core/generator/native_tet/mesher.py** (module-level helper 1개 추가, 호출 없음)
- 함수: 신규 `_flat_cap_boundary_tets(pts, tets, nd_ratio=0.05, max_report=64)`
- 핵심 (≤55줄, **순수 read-only, 어떤 caller 도 없음, default OFF**):
  1. `_tet_boundary_faces(tets)` (plane_coverage) 로 boundary face 추출 → face→owner-tet map.
  2. owner tet 마다: boundary face 정확히 1개 & 나머지(내부) 정점 d 의
     height = |(pts[d]-pts[a])·n| (n=면 단위법선). face_diam = 면 최장변 길이.
  3. `height < nd_ratio * face_diam` 인 tet = flat cap 후보 → (tet_idx, height, face_diam,
     est_bskew≈face_diam/(2*height)) 리스트 반환 (내림차순, max_report cap).
  4. 반환 dict: n_cap, worst_est_bskew, median_height — mesh **불변**.
- 단조 가드: **불필요** — helper 는 순수 함수, mesh 미변경, 호출 0 → bit-exact 회귀.

## 검증 명령 (unit_tester 그대로 실행 · Windows: PYTHONUTF8=1 PYTHONIOENCODING=utf-8, WSL python3)

```bash
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 200 python3 scripts/smoke_native_cylinder.py
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 120 python3 scripts/smoke_native_tet.py
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 120 python3 scripts/smoke_native_tet.py 2000
timeout 90 python3 -m pytest tests/test_native_tet_solid_volume.py tests/test_native_tet_target_cells.py tests/test_native_tet_harness.py tests/test_cylinder_wall_fidelity.py tests/test_flip_signed_validity.py -q
```

## 합격 기준 (validator)

- **회귀 0 (bit-exact)**: helper 는 호출되지 않음 → CYL skew **44.9 그대로**, nonOrt 89.2,
  wall_dev_max 0.000; cube smoke N=500 skew 3.8 / N=2000 skew 1.81, solid 4항 전부 ok.
  (skeleton 규율: 이 카드는 skew 를 **안 낮춘다** — 다음 카드가 낮춘다. 지금은 표적확정.)
- **pytest 세트 PASS** (알려진 flaky 제외: phase_a, cylinder 스위트 간헐, TestTierGracefulFail 2건).
  test_flip_signed_validity 무회귀 (flip 코드 미변경).
- **helper 자기검증(단위테스트 권장, maker 작성)**: cylinder mesh 에서 `_flat_cap_boundary_tets`
  가 n_cap ≥ 8 & worst_est_bskew ≈ 40~50 리포트 (실측 worst 셀 normal_dist 0.00186,
  face_diam≈0.17 → est≈45 와 정합). cube mesh 에선 n_cap ≈ 0 (평면벽엔 flat cap 희소).
- bench 시간 ≤ base +2% (helper 는 호출 안 됨 → 사실상 0).

## 카드 시퀀스 위치 (near-wall cap-sliver 해소 시퀀스, 총 4장 예상 · 본 카드 1/4)

- **1/4 (본 카드)**: flat cap 진단자 추가 (read-only, gate OFF). flip/edge-split/locked-smooth
  3노선 dead-end 를 실측 확정하고 표적(flat cap, normal_dist=height/4)을 수식으로 고정.
- **2/4 (다음, PASS 후) — BETA2830**: 진단자를 BETA2828 블록 직후에서 gate ON 으로 log-only
  호출 (native_tet_capsliver_diag per-fid: n_cap, worst_est_bskew). mesh 불변, 회귀 0.
- **3/4 — BETA2831**: flat cap 의 **내부정점 d 를 -n 방향(벽 안쪽)으로 offset** 하는 국소
  relocation dry-run (mesh 불변, evidence-only). skew_proxy(BETA2828 공식) 개선폭 실측.
  BETA2826(전역 AMIPS, skew 280 폭발) 와 달리 **skew-directed(normal_dist↑)** 이라 방향 반대.
- **4/4 — BETA2832**: BETA2828 직후(disk-adjacent, 하류無) offset 적용 + skew_proxy 비악화 &
  relative-inv & wall_dev(내부점이라 0) 3중 가드. 목표 CYL skew 44.9 → ≤8 국소 달성.
