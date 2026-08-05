# Aggressive Tetrahedral Mesh Improvement (Klingner & Shewchuk, IMR 2007)

> **출처:** Bryan M. Klingner, Jonathan R. Shewchuk, *Proc. 16th International Meshing
> Roundtable* (2007) 3–23. PDF: people.eecs.berkeley.edu/~jrs/papers/aggress.pdf
> **관련 문제:** native_tet 의 max_skew 10.02 (draft 임계 8.0 초과) — solid 는 됐으나
> 내부 품질이 나쁘다. 우리는 sliver 제거를 **8번 시도해 전부 실패**했다
> (research/quality-harness/attempts_catalog.md). 이 논문이 그 실패의 원인과 올바른 스케줄을 제시한다.

---

## 1. 핵심 결론 (우리 8번 실패의 진단)

논문의 중심 주장: **"단일 연산 repertoire 가 약하면 mesh optimizer 는 나쁜 local
optimum 에 갇힌다."** 개별 연산(smoothing 만, 또는 flip 만)은 반드시 막힌다. 세 부류를
**함께 스케줄**해야 뚫린다:

1. optimization-based **smoothing** (nonsmooth min-quality 최적화)
2. **topological transformation** (edge removal = 3-2/4-4 flip 일반화, multi-face removal, 2-3 flip)
3. **vertex insertion** (나쁜 tet 에 새 정점 삽입 — 나머지 둘로 안 뚫리는 저항을 뚫음)

> *"We demonstrate that all three techniques—smoothing, vertex insertion, and
> traditional transformations—are substantially more effective than any two alone."*

**우리 attempts_catalog 의 8번 실패는 전부 "하나만, 잘못된 순서로" 시도했다**:
AMIPS smoothing 단독(4회), collapse 단독(1회), Steiner insertion 단독(3회). 논문 기준
이건 반드시 실패하는 조합이다. **핵심은 개별 연산이 아니라 세 부류의 스케줄이다.**

---

## 2. Our Mesh Improvement Schedule (§4.2 — 그대로 옮길 대상)

**적응형 스케줄** (고정 pass 수는 "too inflexible" 이라 명시적으로 배격):

```
1. 항상 먼저: optimization smoothing 1 pass + topological 1 pass (vertex insertion 제외)
   — "these are always fruitful"
2. 이후 각 pass:
   a. smoothing 으로 시작
   b. 진전 부족하면 → topological pass (edge removal; 실패 시 그 tet 의 각 내부 face 에
      multi-face removal; 내부 face 가 경계변 포함 시 2-2 flip 시도)
   c. 그래도 부족하면 → vertex insertion (worst 3.5% tet 대상)
3. 종료: 연속 3 pass 가 "충분한 진전" 실패 시.
```

**"충분한 진전" 판정 (thresholded means — 우리가 놓친 진단 지표)**:
worst tet 품질 + 7개 thresholded mean (min-sine 기준 threshold sin1°/5°/10°/15°/25°/35°/45°).
threshold d 의 mean = 모든 tet 품질을 d 로 clip 후 평균 → **저품질 tet 의 진전만 측정,
고품질 tet 변화는 무시.** 하나라도 +0.0001 오르거나 worst 가 오르면 pass 계속.

**Smart smoothing (§3.1 — 단조성 보장)**:
> *"if a smoothing operation does not improve the minimum quality among the tetrahedra
> changed by the operation, then the operation is not done. Thus, the quality vector of
> the mesh never gets worse."*
→ **우리 `smooth.py:123` 에 이미 구현됨** (min_q >5% 하락 시 revert). 이 부분은 맞다.

**Composite operations (§3.5 — valley 탈출 + rollback)**:
vertex insertion 직후 그 정점을 smooth + 주변 tet 에 topological+smoothing pass →
**전체 품질 벡터가 개선 안 되면 삽입 직전으로 roll back.** hill-climbing 이 valley 를
넘게 해주는 핵심. (우리 Steiner 실패는 rollback 없이 넣기만 해서 hang/악화됐다.)

---

## 3. Quality measure & boundary 처리 (우리 상황 직결)

**Quality measure (§2)**: 4개 시험 → **V/ℓ³ (volume-length) measure 추천.**
`V/ℓ³_rms` 정규화, 등변사면체=1. radius-ratio 는 "inferior … even when the goal is to
optimize the radius ratio" 라고 명시적으로 열등하다 판정.
→ **우리 `quality.py:76` 의 `8.48·V/emax³` 가 바로 이 measure.** 이것도 맞다.
min-sine measure 는 dihedral 만 penalize (needle 못 잡음), V/ℓ³ 는 skinny 도 잡음.

**Boundary 정점 처리 (§3.1, §3.4 — BETA2823 lock 과 직접 충돌/보완)**:
- 우리는 BETA2823 에서 **경계 정점 전체를 lock** 했다 (표면 fidelity 확보).
- 논문은 경계 정점을 **완전 고정하지 않고 "제약 하에 이동"** 시킨다:
  인접 경계삼각형이 (허용오차 내) **공통 평면**이면 그 평면 안에서 smooth,
  경계 **직선 능선(ridge)** 위 정점은 그 능선 따라 이동. 곡면 경계는 미구현(→ 그런
  메쉬는 boundary smoothing 이득 없음).
- **cube 는 6개 평면 + 직선 능선뿐** → 논문의 제약 boundary smoothing 이 **정확히
  적용 가능**. 우리 lock 은 과하게 보수적(평면 내 이동까지 막음)일 수 있다.
- **핵심 인용**: *"Most mesh generation algorithms create their worst tetrahedra on the
  boundary of the mesh, and boundary tetrahedra are the hardest to repair."* — 우리
  실측(축퇴 50/50 이 경계 접촉)과 정확히 일치. boundary edge removal + boundary
  face barycenter 삽입이 이걸 겨냥한다.

**결과 (달성 가능 상한)**: 규칙적 정점 간격 메쉬 → **모든 dihedral 31°~149°**,
때로 40°~140°. 어떤 기존 SW 도 22°/155° 를 일관되게 못 냄. → skew 8.0 은 충분히 도달권.

---

## 4. native_tet 적용 메모 (다음 harness 카드 토대)

- **적용 위치**: `mesher.py:1927` (BETA2825 축퇴 제거 블록 직후, disk write 직전).
  이미 solid + 축퇴 0 인 메쉬가 입력이므로, 논문의 mesh improvement 스케줄에 **이상적
  입력**(과거 8번은 구멍/축퇴 있는 메쉬 위라 실패).
- **핵심 처방 3가지 (우리가 놓친 것)**:
  1. **세 부류를 함께 스케줄** — smoothing 단독 금지. `smooth.py`(smart, V/ℓ³ 이미 맞음)
     + `flip.py` edge removal(단 signed-validity 버그 수정본) + composite vertex
     insertion(rollback 포함) 을 §4.2 순서로 엮는다.
  2. **thresholded-means 종료 판정** 도입 — 고정 pass 수(우리 현재 방식) 대신 worst +
     7 thresholded mean 으로 "3 pass 무진전 시 종료".
  3. **boundary 를 완전 lock 하지 말고 평면-내/능선-따라 제약 smooth** 허용 —
     BETA2823 lock 을 "평면 내 이동 허용" 으로 완화 (extra_area 가드로 표면 이탈 방지).
     worst tet 이 경계에 있으므로 이게 결정적.
- **회피할 함정 (attempts_catalog + 논문 대조)**: 개별 연산 단독 카드 금지. composite
  insertion 은 반드시 rollback 동반(§3.5). `flip.py` abs-value validity 버그(BETA2825
  에서 발견) 먼저 수정해야 edge removal 이 overlap 안 만든다.

**레퍼런스 교차**: Freitag & Ollivier-Gooch 1997 (min-sine + swap/smooth 원조,
dihedral <10° 잔존 한계), fTetWild §"mesh improvement" (AMIPS energy, 우리가 포팅한 대상).
