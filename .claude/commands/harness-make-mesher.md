---
name: harness
description: |
  Auto-Tessell 개발 하네스. ASSESS → PLAN → BUILD → TEST 순환 루프.
  모듈별 서브에이전트를 자동 선택하여 구현/수정/디버깅을 지속적으로 수행.
  사용자가 중단할 때까지 멈추지 않고 코드를 고도화한다.
  트리거: 기능 구현, 모듈 개발, 버그 수정, 파이프라인 작업 언급 시.
argument-hint: "구현할 기능이나 방향을 설명하세요 (빈칸이면 자동 탐색)"
---

# Auto-Tessell 개발 하네스 (순환형)

**핵심 비전**: CAD → CFD-ready 메쉬 (+ OpenFOAM 케이스 전체) 완전 자동, 인간 개입 0.
**native-first**: 외부 메쉬 라이브러리는 레퍼런스 전용. 자체 구현이 스스로 서야 한다.

## 초기 목표

$ARGUMENTS

(빈칸이면 ASSESS 가 자동 탐색한다.)

---

## 시작 전 필수 — 건너뛰면 같은 실패를 반복한다

1. **`research/quality-harness/attempts_catalog.md` 를 읽어라.** R1~R190+ 시도 이력과 **AVOID 목록**이 있다.
   이미 reject 된 접근을 다시 계획하는 것이 이 하네스의 가장 흔한 실패 모드다.
   카드 설계 전 관련 키워드로 grep 하라. (실례: "개선 패스로 슬리버 제거" 는 AMIPS 4회 /
   collapse 1회 / Steiner 3회 / envelope-relocate 2회 reject 됐다. 모르고 또 시도했다.)
2. **fTetWild 원본이 repo 안에 vendored 돼 있다** — `vendor/dependencies/fTetWild/src/`.
   웹 검색이나 논문 기억보다 **이 원본을 직접 읽어라**. native_tet 은 이것의 포팅이므로
   *"레퍼런스는 이 술어를 쓰는데 우리는 다르다"* 가 가장 강력하고 논쟁 불가능한 근거다.
   (최대 성과였던 void-free filter 카드가 정확히 이 대조에서 나왔다.)
3. `.claude/rules/` (coding-style, lessons-learned) + 해당 `docs/contracts/*.md`.

## 1. ASSESS

인자로 목표가 주어졌으면 그것을 쓴다. 없으면 아래 순으로 **작업 1개**를 고른다:

1. 테스트/CI 실패 (`pytest tests/ -q --ignore=backend`) — 단 아래 "알려진 결함" 제외
2. **레퍼런스(vendored fTetWild) 와의 동작 불일치** — 최우선 후보
3. `docs/contracts/*.md` 대비 미구현
4. mock 으로만 검증되는 영역 → 실제 구현 전환
5. 성능/안정성 (대용량 입력, 타임아웃, 메모리)

개선점이 없으면 사용자에게 보고하고 종료.

## 2. PLAN — `code_planner`

산출물: `research/quality-harness/plan.md` (≤120줄). **단일 파일 변경** + 검증 명령 + 합격 기준 + 이론적 근거.
카드는 AVOID 목록을 명시적으로 회피해야 하고, **예상 부작용**(어떤 지표가 나빠질 수 있는지)을
미리 적는다 — 그래야 TEST 단계가 그걸 이유로 잘못 revert 하지 않는다.

## 3. BUILD — 서브에이전트 위임

| 대상 | 에이전트 |
|------|---------|
| 카드 구현 (하네스 표준) | `code_maker` |
| 메쉬 생성·Tier·OpenFOAM 출력·CLI | `generator` |
| 파일 로딩·지오메트리 분석·CAD | `analyzer` |
| 표면 수리·리메쉬 | `preprocessor` |
| Tier 선택·파라미터·재시도 | `strategist` |
| 품질 검증·checkMesh·Hausdorff | `evaluator` |
| Qt/웹 GUI | `desktop` |

독립 모듈은 병렬 위임 가능. **한 단위에서 5개 이상 파일 동시 수정 금지.**

## 4. TEST

카드의 검증 명령을 그대로 실행. 실패 시 해당 에이전트 재호출 (최대 3회) →
3회 실패 시 `research/quality-harness/_blocked.md` 기록 후 다음 사이클.

**Advisor(메인 세션)가 직접 검증한다. 서브에이전트의 자기보고를 믿고 커밋하지 않는다.**
회귀 여부는 **scoped stash A/B** 로 확인 — "사전 결함" 주장은 실측으로만 인정.

**측정은 정본 스크립트로만.** cube 는 `python scripts/smoke_native_tet.py`, cylinder 는
`python scripts/smoke_native_cylinder.py`. **ad-hoc 측정 스크립트로 baseline 잡기 금지** —
BETA2827 이 planner/maker 가 서로 다른 자로 재서 (4159 vs 280) BLOCK 됐다. 서로 다른
자의 숫자는 비교 불가다.

**속도 — inner loop 는 스모크로.** 계측/A-B 반복은 `python scripts/smoke_native_tet.py`
(cube N=500, **~1.5s**, solid 4-불변식 검사 + skew 보고, 실패 시 exit≠0)를 써라.
전체 파이프라인(N=2000, ~3.5s/run)을 A/B 마다 수십 번 돌리면 사이클이 10분+ 로 늘어난다.
모든 N 이 solid 불변식·skew 결함을 동일하게 보이므로 스모크가 완전히 대표적이다.
**N=2000 pytest 게이트(`test_native_tet_solid_volume.py`)는 최종 검증에만.**
`AUTO_TESSELL_TEST_CELLS=500 pytest ...` 로 그 게이트도 스모크 크기로 돌릴 수 있다(dev 한정).

## 금지 — 위반 시 카드 무효

- **가짜 PASS**: 임계값 완화 / 평가자 수정 / 테스트 허용오차 확대로 통과시키기.
  도달 불가면 **실측과 함께 "여기가 벽이고 이유는 이것" 이라고 정직하게 보고하고 멈춰라.**
- **외부 라이브러리로 가리기**: P4C(pytetwild) 를 더 자주 띄워 자체 구현 결함을 덮기.
- **지표를 좋게 만들려고 데이터를 삭제하기.**
  실례: 슬리버를 지워 skew 10.5 를 만들었으나 부피에 구멍(경계면적 3.4배)이 뚫려 있었다.
  구멍 뚫린 메쉬보다 **정직한 나쁜 숫자가 낫다.**
- AVOID 목록 재시도 (다른 이유가 있다면 실측 근거를 카드에 대라).

## 환경 — Windows + WSL UNC

- pytest 직접 실행: `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` 필수 (콘솔 cp949).
- A/B 는 **scoped** `git stash push -- <파일>` 만. **맨 `git stash` 금지** —
  UNC 경로 바이너리가 `lstat: Function not implemented` 로 실패한다.
- 자체 구현 격리 측정: `AUTO_TESSELL_P4C_PYTETWILD=0` (외부 구제 차단).
- **`except Exception → log.debug` 가 버그를 오래 숨긴 전례가 많다.** 패스가 0ms 거나
  아무 일도 안 하는 것처럼 보이면 verbose 로깅부터 켜라.

## 알려진 결함 — 쫓지 말 것 (단, 카드 귀인 판정 시 참고)

- `test_native_tet_phase_a_improves_cube_boundary` — **플래키** (단독 실행 실패, 묶으면 통과)
- `test_cylinder_wall_fidelity` — **스위트 문맥에서 간헐 실패** (~2/3, dev 0.359 = P4C 구제
  미발동/미반영; 단독 3/3 통과). BETA2826 smooth 블록 유무 A/B 각 3회에서 **동일 실패율**
  확인 → 특정 카드 탓 아님. 근본 원인(메셔 비결정성 의심) 미규명 — **조사 후보**.
- `test_generator.py::TestTierGracefulFail::{test_tier_wildmesh_quality_params_draft,
  test_tier_wildmesh_section_topology_detects_hole}` — pristine HEAD 에서도 실패

## 사이클 기록

`research/quality-harness/plan.md` 에 기록:

```markdown
## 사이클 N — [제목]
**ASSESS**: 무엇을 왜 선정했는지
**PLAN**: 작업 단위 + 검증 명령
**BUILD**: 위임 에이전트, 수정 파일
**TEST**: N passed, M failed (실측 수치)
**상태**: ✅ 완료 / ❌ blocked
```

PASS 시 `research/quality-harness/attempts_catalog.md` 에 한 줄 추가:
Round / CARD / engine / verdict / Δ지표 / 사유. **FAIL 도 반드시 기록** — AVOID 목록의 가치는
실패를 남기는 데서 나온다.
