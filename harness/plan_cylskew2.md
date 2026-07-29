# CARD CYLSKEW2 (beta2823) — offset-ring 시드 scale-invariant 상대 가드 (sidewall 필터 가설은 실측 반증)

**target_engine**: tet
**모티프**: Garimella & Shashkov 2003 §3 offset-surface node placement — CYLSKEW1 seeding-only 훅의 scale 안전성 보강

## 실측 결론 — 원래 카드(측벽 필터)는 반증됨

정본 측정 `scripts/smoke_native_cylinder.py` (P4C=0, N=2000):

| 구성 | cells | skew | wall_dev_max |
|------|-------|------|--------------|
| OFF (offset ring 없음) | 1847 | 44.9 | 0.000 |
| **CYLSKEW1 무필터 (66 pts, ON)** | **2296** | **40.8** | **0.000** |
| sidewall만 keep `\|nz\|<0.7` (64 pts, 캡중심 2개 drop) | 2289 | 44.9 | 0.000 |
| sidewall만 keep `\|nz\|<0.5` (전부 drop→no-op) | 1847 | 44.9 | 0.000 |
| cap중심만 keep `\|nz\|>=0.9` (2 pts) | 1854 | 44.9 | 0.000 |

**핵심 반증**: cylinder.stl은 z-ring이 2개(z=±0.5)뿐이라 순수 측벽 정점(|nz|≈0)이 하나도
없다. 64개 rim 정점의 각도가중 법선은 측벽면·캡면 공유로 |nz|≈0.5–0.7(대각)이고,
캡중심 2개만 |nz|≈1.0. 실측 결과 **skew 개선 44.9→40.8은 66점 전체가 있을 때만
발현**한다 — sidewall-only(64)도 44.9, cap-only(2)도 44.9. 어떤 부분집합으로 걸러도
개선이 사라진다(holistic/emergent). 즉 제안된 측벽 필터를 넣으면 skew가 **퇴행**한다.
→ **CYLSKEW1 무필터가 cylinder에서 이미 최적. 필터 카드는 폐기.**

## 재조준 — 이번 카드가 실제로 하는 일 (scale-invariant 상대 가드)

CYLSKEW1의 두 가드가 절대치라 스케일 의존적이다: de-dup 임계 `1e-6`(절대),
offset→surface 하한 없음. 스케일 1e-5로 줄인 mesh면 offset 간격 6e-7 < 1e-6 → 유효점
오제거. default ON 전환 전 반드시 제거할 취약점. **상대 가드로 일반화(파라미터 sweep
아님, 알고리즘 불변 조건 교체).**

- **문제 정의**: de-dup 조건 `d < 1e-6` 는 mesh 스케일 L에 무관해야 옳다.
  올바른 불변식: `d < ρ·target_edge_length`, ρ 상수. offset 유효성:
  `min_j |p_i - v_j| ≥ κ·depth` (near-tangent leak-to-boundary 방지).
- **핵심 변경**:
  1. de-dup 절대 `1e-6` → 상대 `rel_dedup*target_edge_length` (rel_dedup=1e-3).
     cylinder: 5.3e-4 ≪ 실측 최소간격 0.060 → **드롭 0개, 출력 불변**.
  2. offset→surface 하한 추가: `d_v < surf_floor*depth` 후보 reject
     (surf_floor=0.25). cylinder: d_v/depth≈1.0 ≫ 0.25 → **reject 0개, 출력 불변**.
  3. 두 상수는 signature default 인자 노출(호출부 무변경, 하드코딩 제거).
- **레퍼런스**: Garimella 2003 §3(collision/spacing), CLAUDE 상대-가드 원칙.
- **혁신성**: novelty 1 / rigor 2(scale-invariant 불변식 + no-op 증명) / impact 2
  (default ON 선결 안전성) = 5. 필터 카드(합<5, 실측 반증)보다 우선.

## 변경

- 파일: `core/generator/native_tet/offset_ring.py` (단일 파일)
- 함수: `offset_ring_seed_points` (line ~16, 가드 루프 ~59–77)
- 핵심 변경 (≤25줄):
  1. depth 계산 직후 `dedup_thr = rel_dedup*float(target_edge_length)` 도출,
     루프의 `if d < 1e-6` → `if d < dedup_thr`.
  2. accept 전 `if d_v < surf_floor*depth: continue` 추가 (winding-inside 이후).
  3. signature 에 `rel_dedup: float = 1e-3, surf_floor: float = 0.25` 추가, info 에
     `dedup_thr`, `surf_floor` 리포트.
- 단조 가드: cylinder에서 n_inserted 는 반드시 66 유지(어떤 후보도 새 가드에 걸리면
  안 됨). n_inserted != 66 이면 상수 재조정 후 재측정 — **출력 불변이 합격 전제**.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 90 python3 tests/test_native_tet_solid_volume.py
timeout 90 env AUTO_TESSELL_TET_OFFSET_RING=1 python3 scripts/smoke_native_cylinder.py
```

## 합격 기준 (validator 가 평가)

- 회귀 PASS (`test_native_tet_solid_volume.py`)
- **wall_dev_max == 0.000** (절대 타협 불가, 최우선)
- ON 경로 cylinder: **cells==2296, skew==40.8** (CYLSKEW1 대비 완전 불변 — 상대 가드가
  no-op 임을 실증). 값이 바뀌면 상수가 유효점을 건드린 것 → FAIL.
- OFF 경로 무변화 (1847 / 44.9), 시간 ≤ 6s
- default 여전히 OFF (`AUTO_TESSELL_TET_OFFSET_RING` 미설정 시 no-op)

## 카드 시퀀스 위치

- CYLSKEW 시퀀스(offset ring → default ON) 의 2번째/약 5개 중.
  1(CYLSKEW1)=스켈레톤 훅 ✅ / **2(본 카드)=scale-invariant 상대 가드** /
  3=2번째 형상(sphere/cube)에서 offset ring 유익성·안전성 실측(회귀 0 확인) /
  4=monotone best-of-two 셀렉터(offset seed 有/無 중 skew 낮은 쪽 채택, 다중 파일이라
    별도 카드) / 5=default ON + 합격 기준 강화.
- **다음 카드 후보(본 카드 PASS 후)**: CYLSKEW3 — offset ring 을 sphere.stl(순수 곡면,
  z-ring 다수)에 적용해 측벽 정점(|nz|≈0)이 실재하는 형상에서 skew/wall_dev 실측.
  cylinder 반증(측벽 무의미)이 곡면 형상에서도 유지되는지 검증 → 필터 가설 최종 판정.
