# Tetrahedral Meshing in the Wild (Hu et al., SIGGRAPH 2018) — 원본 TetWild

> **출처:** Yixin Hu, Qingnan Zhou, Xifeng Gao, Alec Jacobson, Denis Zorin,
> Daniele Panozzo, *ACM TOG* 37(4) (2018), Article 1. DOI: 10.1145/3197517.3201353
> **관련:** native_tet 이 포팅한 mesh improvement framework 의 **원형**.
> fTetWild(2020)가 *"we adapt the framework proposed in TetWild"* 라 한 그 프레임워크.
> fTetWild 요약이 "정본" 이라 미룬 스케줄·energy·invariant 정의가 여기 있다.

---

## 1. 핵심 수식 — Conformal AMIPS 3D Energy (Eq. 1)

$$
E = \sum_t \frac{\mathrm{tr}(J_t^{T} J_t)}{\det(J_t)}
$$

- **$J_t$** = 사면체 $t$ 를 정사면체(regular tet)로 보내는 유일 3D 변형의 Jacobian.
- **의미**: isotropic scaling 에 불변(scale-invariant). needle / flat-and-fat / sliver
  를 자연스럽게 penalize. **부피가 0 에 가까워지면 ∞ 로 발산 → inversion 을 원천 차단**
  (우리 축퇴 tet 은 이 energy 에서 ∞ = 강제로 밀어냄).
- 미분 가능 → Newton / Quasi-Newton 으로 최소화. 우리 `quality.py` 의 V/ℓ³ 도 유효하나,
  AMIPS 는 inversion 발산이라는 안전장치를 energy 자체에 내장.

## 2. 3개 Invariant — 모든 연산이 지켜야 할 것 (§3.2, 우리 8번 실패의 정확한 진단)

연산은 **invariant 를 깨지 않을 때만** 적용/수락된다:
- **Invariant 1**: rational-number geometry 유효성 (부동소수 rounding 시에도 유지).
- **Invariant 2 (Envelope)**: embedded surface(입력 삼각형과 정확히 일치하는 tet face
  집합)의 각 face 가 입력에서 거리 **ε 이내**. ε-envelope 을 벗어나는 연산은 **금지**.
- **Invariant 3 (No inversion)**: 어떤 tet 도 뒤집히지 않음.

> *"All these operations are performed only if they do not break any of the invariants,
> and if they increase the mesh quality (with the exception of (1) splitting)."*

**← 이것이 우리 attempts_catalog 8번 실패의 핵심.** 우리 시도들은 invariant 가드
(envelope + inversion + quality)를 붙이지 않고 연산을 적용했다. TetWild 는 세 가드를
모두 통과할 때만 수락하고 아니면 **연산을 안 한다** (rollback).

## 3. Mesh Improvement Schedule (§3.2 — 정본, 그대로 옮길 대상)

**4 pass 를 이 순서로 반복** (asymmetric optimization scheme):

```
(1) Splitting  (refine)  — target edge length ℓ 보다 4/3·ℓ 긴 edge 를 split.
                            ★ 유일하게 quality 개선 안 해도 적용 (quality-oblivious).
                            우선순위: longest edge first (priority queue).
(2) Collapsing (coarsen) — quality 개선 시에만. 우선순위: shortest edge first.
(3) Swapping             — face swap(3-2/4-4/5-6 bistellar flip), quality 개선 시에만.
                            우선순위: longest edge first.
(4) Smoothing            — 각 정점을 one-ring 의 AMIPS 평균 최소화로 이동(Newton,
                            analytic gradient+Hessian). float 로 round 가능한 정점만.
                            순서: random. quality 개선 시에만.
```

**Asymmetric 핵심 (over-refinement 방지)**:
- coarsen/swap/smooth 는 **quality 개선 시에만** 적용 (smart, 단조).
- refine(split)만 quality 무시하고 target edge length 까지 무조건 적용.
- 이유: *"avoid over-refinement where it is not necessary … add vertices only to match
  density or locally if necessary to improve quality."*

**Fig. 7 (★ 우리 8번 실패를 그림으로 설명)**:
> *"The quality might **decrease during the iterations due to the local refinement
> ignoring quality**, but it quickly improves after additional passes of collapsing,
> swapping, and smoothing."*

→ **우리는 이 dip 을 보고 "악화됐다" 며 revert/reject 했다.** attempts_catalog 의
"worst-mq 0.076→0.055 악화" 패턴이 정확히 이 refinement dip 이다. 논문은 split 후
**collapse+swap+smooth 를 이어서** 돌리면 회복+초과한다고 말한다. 우리는 split 단독,
또는 smooth 단독으로 끊어서 dip 만 보고 포기했다. **연산을 끊으면 반드시 실패한다.**

## 4. Boundary/surface 정점 처리 (BETA2823 전면 lock 재고 근거)

- surface 정점을 **완전 고정하지 않는다.** embedded surface 를 tracking 하며 연산으로
  **이동시키되**, envelope(ε) 을 벗어나면 rollback. 즉 "envelope 폭 안에서 자유 이동".
- fTetWild 요약(§3)과 동일하나, 원본은 envelope 을 **invariant 2 로 정식화**했다 —
  "표면을 못 움직이게" 가 아니라 "표면이 ε 밖으로 못 나가게".
- → **우리 BETA2823 의 경계 정점 전면 lock 은 이 invariant 의 과도한 근사.**
  올바른 처방: lock 대신 "이동 후 envelope 검사 → 위반 시 rollback". cube 는 평면이라
  envelope 안에서 평면 위 이동이 자유롭고, 그래야 경계 접촉 축퇴 tet 이 풀린다.

---

## 5. native_tet 적용 메모 (Klingner + fTetWild 요약과 합쳐 최종 처방)

**세 논문 합의 = 다음 harness 카드의 청사진**:

1. **4 pass 스케줄을 통째로** (split→collapse→swap→smooth), 끊지 말고 반복.
   우리는 개별 연산 단독 카드로 8번 실패했다. **한 카드에 4 pass 전부** 넣어야 한다.
2. **각 연산에 3중 가드**: (a) inversion 없음(signed vol > eps), (b) envelope 이탈 없음
   (표면 face 가 입력 평면에서 ε 이내 — 우리 extra_area/plane 거리 가드로 구현),
   (c) quality 개선(split 제외). BETA2825 의 extra_area revert 가 (b)의 축소판이었고 통했다.
3. **split 의 quality dip 을 revert 사유로 삼지 말 것.** collapse+swap+smooth 가
   회복시킨다(Fig.7). 이게 우리가 매번 놓친 지점.
4. **경계 정점 전면 lock(BETA2823) → envelope 가드 하 이동 허용** 으로 완화.
   축퇴 50/50 이 경계 접촉이므로 필수.
5. energy: 먼저 기존 V/ℓ³(`quality.py:76`)로 스케줄 검증. AMIPS(Eq.1)는 inversion
   발산 안전장치가 매력적이나 Newton+Hessian 구현 비용 → 후속 카드.

**선행 수정**: `flip.py` 의 abs-value validity 버그(BETA2825 발견) — swap pass 가
inversion 을 만들면 가드에 걸려 무한 실패. signed validity 로 먼저 고쳐야 (3) swap 가능.

**적용 위치**: `mesher.py:1927` (BETA2825 직후, solid+축퇴0 = 이상적 입력).
**달성 목표**: skew 10.02 → draft 임계 8.0 이하. Klingner 상한(dihedral 31°~149°)
= skew ≪ 8 이므로 도달권.
