# CARD HEX-WALLFIT-FINE (beta1) — 로컬 sizing 기반 wall-fit envelope (fine quality 복구)

**target_engine**: hex
**모티프**: fTetWild §3.2 envelope (∝ 로컬 sizing) + snappyHexMesh snap-step (로컬 셀 크기 기준). 전역 최소 edge 가 아니라 정점별 로컬 셀 크기로 envelope 를 잰다.

## 이론적 근거 (실측 데이터 포함)

**실측 (정본 측정: `tests/test_native_hex_solid_volume.py` 헬퍼 재사용, cylinder/cube, N=2000):**

| quality | wall_dev_max | mean | skew | degen | verdict | fine hard-fail |
|---------|-------------|------|------|-------|---------|----------------|
| standard | **0.0032** | 0.0015 | 4.64 | 0 | PASS_WITH_WARN | — |
| fine | **0.0353** | 0.0017 | 1.42 | 0 | FAIL | hausdorff_rel 0.0225, neg_vol 16(BL), non_ortho 90(BL) |

즉 **fine 이 게이트(≤0.02)를 실패**한다. mean 은 standard 와 동등(0.0017)인데 **max 만 11배 나쁘다** → 대부분 정점은 잘 맞고 소수 정점만 벽에서 멀다.

**문제 정의 (수식).** `_wall_fit_snap` (mesher.py:490) 은 정점 P 의 표면 투영 이동을 envelope
`|proj(P) − P| ≤ cap`, `cap = ratio·target_edge` (mesher.py:555, 619) 안에서만 허용한다.
octree 경로 호출(mesher.py:999)은 `target_edge = h_pre / 2^n_levels` = **가장 미세한 셀 크기**를
넘긴다. 그러나 벽 정점은 refinement 가 닿지 않은 **coarse octree 셀**(level 0/1)에 속할 수 있고
그 staircase 오차는 coarse 셀 edge(~h_pre) 규모다. fine 은 n_levels=4 → cap ≈ h_pre/16 ≈ 0.0045
(cylinder), 이는 coarse 셀 벽 정점의 오차 0.035 보다 작아 **snap 이 envelope 밖으로 거부**된다
(mesher.py:619 `continue # outside envelope`). standard 는 n_levels=2 → cap ≈ h_pre/4 ≈ 0.027 로
우연히 충분히 커서 통과. 이 hausdorff_rel(0.0225>0.02)이 fine cylinder 의 hard-fail 로 직결.

**핵심 아이디어.** 전역 스칼라 cap 을 **정점별 로컬 cap** 으로 교체:
`cap(v) = ratio · max(target_edge, localEdge(v))`,
`localEdge(v) = v 의 incident 셀들의 face edge 길이 최댓값` (level-transition 의 coarse 셀 크기를 포착).
= sizing-field 상대 envelope. 최소값 floor 로 `target_edge` 유지 → 기존 하한 불변.

**단조/안전 보장.** strict-decrease guard(mesher.py:624)와 no-inversion guard(mesher.py:628)는
**그대로**다. envelope 를 넓혀도 두 guard 를 통과하는 이동만 채택되므로 (a) 표면에서 멀어지는 이동
불가, (b) 셀 반전/붕괴 불가. 따라서 envelope 확대는 **엄격히 개선되는 snap 만 추가로 허용**하며
worst-case 로도 기존 상태를 악화시킬 수 없다 → standard(이미 통과) 회귀 불가. cube 벽 정점은
평면 위에 이미 있어 `d0 ≤ tol` 조기 continue(mesher.py:616) → 확대해도 불변.

**레퍼런스**: fTetWild §3.2 (envelope ∝ 로컬 sizing), snappyHexMesh snap-step (로컬 셀 크기),
Garimella 2003 (로컬 edge 스케일 기준 이동 한계).

**혁신성**: novelty 1 (확립된 로컬 sizing envelope 를 hex snap 에 적용), rigor 2 (guard 불변 →
단조 확대 증명), impact 2 (fine wall fidelity 잠금 해제, hausdorff hard-fail 제거). 합 5.

## 범위 밖 (본 카드에서 손대지 않음 — 명시)

- **cube fine hausdorff_rel 0.0258**: cube 표면 coverage=6.000/off=0.000(정확)인데도 발생 →
  BL/fidelity 측정 아티팩트(normal_dev 90°), mesher 품질과 무관. 별도 evaluator 카드.
- **cylinder fine neg_vol=16, non_ortho=90**: BL 5-layer 가 곡면 벽에서 만든 결함(mesher pre-BL
  neg_vol=0). native_bl 카드(Garimella collision)에서 처리. 본 카드는 hex mesher 만.

## 변경

- 파일 1: `core/generator/native_hex/mesher.py` — 함수 `_wall_fit_snap` (line ~490)
  1. `incident` 구축 직후(mesher.py:547 이후) 정점별 `local_scale[v]` 계산:
     incident 셀들의 각 face 인접 edge 길이 최댓값. (boundary_verts 만, O(∑incident·edges), 저렴)
  2. mesher.py:555 의 전역 `cap` 을 하한 `cap_floor = ratio·target_edge` 로 유지.
  3. mesher.py:619 envelope 검사를 `> ratio·max(target_edge, local_scale[vi])` 로 교체.
  4. `_wf_stats` 에 `n_reject_envelope` 진단 카운터 추가(디버깅용, 게이트와 무관).
  - 예상 변경 ≤35줄, 단일 함수. 호출부(mesher.py:994, 1297) 시그니처 불변 → 무수정.
- 파일 2: `tests/test_native_hex_solid_volume.py` — `test_native_hex_curved_wall_fidelity` 를
  quality 파라미터화(standard+fine) 하거나 fine 변형 추가. fine 도 `max_dev ≤ 0.02` 요구.
  (BL/verdict 무관 — polyMesh 벽 정점 반경 편차만 직접 측정.)

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 180 python3 -m pytest tests/test_native_hex_solid_volume.py -q
```

## 합격 기준 (validator 가 정량 평가)

- 회귀 PASS: 기존 4 solid-invariant + standard wall-fidelity 테스트 모두 유지.
- **fine cylinder wall_dev_max ≤ 0.02** (현 0.0353 → 목표 ≤0.02, standard 수준 지향).
- standard cylinder wall_dev_max ≤ 0.005 (현 0.0032, 단조: 회귀 금지).
- cube fine solid 4불변식 불변: surface 6.000±5%, off ≤0.3, Σvol 1.000±5%, degen 0.
- hex mesher pre-BL negative_volumes = 0 (fine/standard 모두, snap 후).
- bench 시간 ≤ 기존 +15% (envelope 확대는 몇 개 snap 추가 채택뿐, 무시 가능).

## 카드 시퀀스 위치

- "hex wall-fidelity across quality levels" 시퀀스의 2번째 (총 ~3).
  - 1(완료, 54bf77bf): standard per-vertex wall-fit snap.
  - **2(본 카드): fine 을 로컬 sizing envelope 로 복구.**
  - 3(후보): snap 후 skew 저감 — standard skew 4.64/fine 1.42 를 Klingner & Shewchuk 2007
    smart-Laplacian/optimization smoothing 으로, 단 표면 정점은 wall_dev guard 하에서만 이동
    (wall_dev 게이트 재회귀 방지 가드 필수).
- 다음 카드 후보(본 카드 PASS 후): HEX-SKEW-SMOOTH — 내부 정점 우선 smart smoothing 으로
  post-snap skew 저감, 표면 정점은 로컬 envelope+strict-decrease guard 유지.
