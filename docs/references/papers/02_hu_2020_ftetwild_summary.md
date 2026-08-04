# Fast Tetrahedral Meshing in the Wild (Hu et al., SIGGRAPH 2020)

> **출처:** Yixin Hu, Teseo Schneider, Bolun Wang, Denis Zorin, Daniele Panozzo,
> *ACM TOG* 39(4) (2020). arXiv:1908.03581.
> **관련:** native_tet 은 이 논문(및 전신 TetWild 2018)의 포팅. 우리 포팅이 빠뜨린
> mesh improvement 스케줄과 rollback 조건을 여기서 확정한다.

---

## 1. 4개 국소 연산 + rollback 규칙 (§3.5, 논문 line 1019 — 정본)

> *"TetWild uses four local operations for mesh improvement: (1) edge splitting,
> (2) edge collapsing, (3) edge swapping, and (4) vertex smoothing. **Every operation
> is rolled back if the tracked surface leaves the envelope after the operation or if
> any tetrahedra are inverted**, ensuring a valid output."*

**핵심 = 모든 연산이 두 조건으로 rollback 된다**:
1. tracked surface 가 ε-envelope 을 벗어나면 (표면 fidelity 위반)
2. 어떤 tet 이든 inverted 되면 (유효성 위반)

→ **이것이 우리 8번 실패의 근본 원인이다.** attempts_catalog 의 실패들은 rollback
없이(또는 min_q 만 보고) 연산을 적용했다. envelope + inversion 이중 rollback 이 없으면
연산이 표면을 밀거나 tet 을 뒤집어 악화된다. BETA2825 에서 이미 이 교훈의 축소판
(extra_area/area_coverage revert 가드)을 썼고, 그게 통했다(revert 0회).

## 2. Quality energy = conformal AMIPS 3D

- **AMIPS energy** (Rabinovich et al. 2017): scale-invariant + differentiable →
  전통 국소연산(split/collapse/swap/smooth)을 "boost". min-sine/radius-ratio 대신 이걸 씀.
- 종료 조건 (line 481): **max AMIPS energy < 10** 또는 **최적화 iteration 80회**.
- 파라미터: envelope ε = 10⁻³·d, target edge ℓ = d/20 (d = bbox 대각선).
- **부동소수 불안정성 주의** (Abstract/§3.5): AMIPS 를 float 로 계산하면 over-refinement
  유발 → 중간결과를 rational 로 계산하는 hybrid evaluation 으로 수정. 우리 포팅도
  이 함정 점검 필요.

## 3. Boundary/surface 정점 처리 (BETA2823 lock 과 대조)

- surface 정점을 **완전 고정하지 않는다** — envelope 안에서 **움직이되** envelope 이탈 시
  rollback. preprocessing 에서 ε_prep = 0.8ε 로 여유를 두는 이유가 바로
  *"leaving more freedom for surface vertices to move in the mesh improvement stage"*
  (line 180). open boundary 정점만 명시적으로 project-back.
- → **우리 BETA2823 의 "경계 정점 전체 완전 lock" 은 fTetWild 보다 보수적이다.**
  fTetWild 는 envelope 폭(10⁻³·d) 안에서 표면 정점 이동을 허용해 품질을 얻는다.
  우리는 표면을 아예 못 움직여서 경계 접촉 sliver(축퇴 50/50)를 못 푼다.

---

## 4. native_tet 적용 메모 (Klingner 요약과 합쳐 카드 토대)

**두 논문의 합의 = 우리 처방**:
1. **연산 단독 금지, 4개(split/collapse/swap/smooth)를 스케줄로.** (Klingner §4.2 순서,
   fTetWild 4-operation loop — 둘이 일치.)
2. **모든 연산에 rollback 가드**: fTetWild = envelope 이탈 OR inversion → rollback.
   우리는 이걸 "extra_area/area_coverage revert(표면) + signed-volume 양수 확인(inversion)"
   으로 구현하면 된다. BETA2825 에서 이미 부분 검증됨.
3. **표면 정점을 envelope 폭 안에서 이동 허용** — 완전 lock(BETA2823) 완화.
   경계 접촉 sliver 를 풀려면 필수. 단 envelope guard 로 fidelity 는 유지.
4. quality energy: AMIPS(fTetWild) 또는 V/ℓ³(Klingner, 더 단순). 우리 `quality.py`
   는 이미 V/ℓ³ → 먼저 이걸로 스케줄 검증, AMIPS 는 후속.

**적용 위치**: `mesher.py:1927` (BETA2825 직후, solid+축퇴0 메쉬 = 이상적 입력).
**주의**: `flip.py` 의 abs-value validity 버그(BETA2825 발견) 먼저 수정 —
edge swap 이 inversion 을 만들면 rollback 이 걸려 무한정 실패한다.
