# CARD HEX-WALLFIT-BACKTRACK (beta1) — 반전 거부 대신 최대 안전 부분이동(line-search)

**target_engine**: hex
**모티프**: Garimella 2003 §3 collision-limited advancing step + fTetWild envelope-bounded relocation + Klingner&Shewchuk 2007 composite-op rollback-to-best. 완전투영 실패 시 revert 하지 않고 "가드를 통과하는 최대 부분이동"으로 backtrack.

## 이론적 근거 (실측 포함)

**문제 정의.** `_wall_fit_snap`(mesher.py:490)은 경계정점 v를 최근접 삼각형 위 점 p0로 **완전투영**한 뒤, incident 셀의 면 방향부호가 하나라도 뒤집히면(`_cell_ok`) 이동 **전체를 revert**(all-or-nothing). fine(n_levels=4)에서 이 no-inversion guard가 후보의 상당수를 거부 → wall_dev_max가 0.02 게이트를 못 넘음.

**직전 카드 가설 반증 확정 + 진짜 원인 실측** (instrumented, cylinder N=2000, iter0 표본):
- standard: `n_reject_vol=0`, wall_dev_max=0.0032 (게이트 통과, 이 카드로 **무변화 보장**).
- fine: `n_reject_vol=39`, wall_dev_max=0.0353.
  - 거부 사유: **flip=39/39, collapse(mag≤eps)=0/39** → eps 임계값은 병목 아님. 거부셀 |vol|/eps 중앙값 1.1e6배(붕괴와 무관, 순수 면 방향 flip).
  - 거부 정점별 "가드를 통과하는 최대 부분이동 분율" `t_max`: min=0.706, med=0.895, mean=0.850. **`t_max<0.01`(진짜 막힘)=0/39** — 단 하나도 진짜로 못 움직이지 않음. 가드가 과도 보수적.
  - 부분이동 후 편차 `dev_at_tmax`: max=0.0099, med=0.0036 (원래 d0 med 0.0338). 편차 회수율 med **0.895**.
  - 최악 정점: d0=0.0355 → t=0.821 부분이동 시 dev 0.0064.

**핵심 아이디어.** 완전투영이 면을 뒤집으면 revert하지 말고, orig→p0 선분에서 **동일 가드(`_cell_ok`)를 통과하는 최대 분율 t\***를 이분탐색(≤12회, 분해능 1/4096)으로 찾아 그 위치를 채택. t\*는 항상 "마지막으로 가드를 통과한 안전점"이므로 반전/붕괴 절대 불가 — **가드 완화가 아니라 가드를 통과하는 더 나은 해를 탐색**. (attempts R31/SSS2 FAIL은 envelope를 *완화*한 실패 사례 — 본 카드는 반대 방향, 안전.)

**단조·안전 보장.** (a) t\*>0에서 채택된 위치는 완전투영과 **동일한 `_cell_ok`**를 통과 → incident 셀 전부 부호 유지 + |vol|>eps → negative_volumes=0 불변. (b) 채택 전 완전투영과 동일한 strict-decrease 검사(`d_partial < d0 - 1e-15`) 재적용 → 표면거리 단조 감소 유지. (c) 정점은 staircase 위치와 참 표면 사이로만 이동(envelope 내) → off-surface void 생성 불가, surface coverage 개선.

**레퍼런스**: Garimella&Shashkov 2003 §3(incident-cell collision → step 제한); Klingner&Shewchuk 2007(composite op, 실패 시 최선점 rollback); fTetWild(Hu 2020) envelope-bounded relocation. 코드: `core/generator/native_hex/mesher.py` `_wall_fit_snap`.

**혁신성**: novelty 2(기존 line-search를 hex wall-fit에 신규 적용) / rigor 3(39/39 flip·t_max 분포·회수율 실측, 동일 가드+strict-decrease 보존, neg_vol=0 증명) / impact 3(fine 게이트 0.035→<0.01, xfail 해제) = **8**.

## 변경

- 파일 1: `core/generator/native_hex/mesher.py` — `_wall_fit_snap` (line ~653-658, vol-reject `else` 분기). **≤25줄**.
  1. `stats`에 `n_snapped_partial` 키 추가(init).
  2. 완전투영이 `_cell_ok` 실패 시: `lo=0, hi=1` 이분탐색 ≤12회 — `mid` 위치가 모든 incident 셀 `_cell_ok` 통과면 `lo=mid` 아니면 `hi=mid`.
  3. `lo>0`이고 그 위치의 재투영거리 `< d0-1e-15`이면 `pts[vi]=orig+lo*(p0-orig)`, `n_snapped_partial+=1`, `moved+=1`; 아니면 `pts[vi]=orig`, `n_reject_vol+=1`.
- 파일 2: `tests/test_native_hex_solid_volume.py` — fine 파라미터의 `xfail(strict=True)` 제거(정상 param화), docstring STATUS를 본 카드 결과로 갱신.
- 단조 가드: vol-reject 경로에만 진입(정상경로 무영향). 채택 위치는 기존 `_cell_ok`+strict-decrease를 그대로 통과. 둘 중 하나라도 실패 시 orig revert.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 300 python3 -m pytest tests/test_native_hex_solid_volume.py -q
```

## 합격 기준 (validator 가 평가)

- 회귀 PASS: cube 4대 불변식(surface 6.0 / void 0 / volume 1.0 / no-degenerate) 불변.
- **fine**: `test_native_hex_curved_wall_fidelity[fine]` PASS, wall_dev_max ≤ 0.02 (목표 <0.01, 실측 추정 ~0.0064-0.0099).
- **standard**: wall_dev_max 불변(0.0032, n_reject_vol=0이라 무변화 보장), PASS 유지.
- **negative_volumes=0 불변** (guard 미완화 — 동일 `_cell_ok` 통과점만 채택).
- bench 시간 ≤ 기존 + 15% (이분탐색 ≤12회 × reject당 소수 incident 셀, reject 경로만 — 무시가능).
- BL 영향 없음 (경계정점만 참표면 쪽으로 소폭 이동, prism 부착면 위상 불변).

## 카드 시퀀스 위치

- "hex wall-fit fidelity" 시퀀스: HEX-WALLFIT(standard PASS) → HEX-WALLFIT-FINE(envelope 일반화, 가설 반증) → **본 카드(backtrack, N/N)** — 진짜 병목(all-or-nothing revert) 해소.
- 다음 카드 후보(PASS 후): HEX-WALLFIT-TANGENT — 부분이동 후 잔여 편차(dev_at_t의 상위 tail)를 접선방향 재투영으로 추가 회수, 또는 harder geometry(sphere/wedge)로 게이트 확장.
