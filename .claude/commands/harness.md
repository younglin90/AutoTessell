---
name: harness
description: |
  Auto-Tessell 개발 하네스. PLAN → BUILD → TEST → ASSESS 순환 루프.
  모듈별 서브에이전트를 자동 선택하여 구현/수정/디버깅을 지속적으로 수행.
  사용자가 중단할 때까지 멈추지 않고 코드를 고도화한다.
  트리거: 기능 구현, 모듈 개발, 버그 수정, 파이프라인 작업 언급 시.
argument-hint: "구현할 기능이나 방향을 설명하세요 (빈칸이면 자동 탐색)"
---

# Auto-Tessell 개발 하네스 (순환형)

## 프로젝트 방향 (2026-04-07 확정)

- **배포 타겟**: Linux CLI + PyQt/PySide6 GUI 우선. Windows .exe는 Phase C(나중).
- **핵심 비전**: CAD → CFD-ready 메쉬 (+ OpenFOAM 케이스 전체) 완전 자동, 인간 개입 0.
- **Phase A 우선 수정 항목** (autoplan 결과):
  1. pytest 3개 collection 에러 (`fastapi` importorskip, `testpaths`, `backend/tests` 이름 충돌)
  2. Drag-drop 비작동 (`DropZone(QLabel)` 서브클래스로 교체)
  3. `pip install auto-tessell` → Draft 작동 (`[starter]` extra에 pytetwild 포함)
  4. OpenFOAM 부재 시 Fine 품질 조기 감지 (run 진입점에서 probe)
  5. CLI 포맷 검증 + 성공 footer (output 경로 + 다음 단계 안내)
  6. pymeshfix 60초 타임아웃
  7. 512MB 파일 크기 게이트 (Analyzer 진입점)
  8. output_dir path traversal 보안 검증

## 초기 목표

$ARGUMENTS

## 실행 규칙 — 순환 루프

```
┌→ ASSESS ──→ PLAN ──→ BUILD ──→ TEST ─┐
│                                       │
└───────────────────────────────────────┘
```

**매 사이클마다** `_plan.md`의 `## 사이클 N` 섹션에 기록한다.
**탈출 조건**: 사용자가 중단하거나, ASSESS에서 개선점을 찾지 못할 때.

---

### 1단계: ASSESS (현황 분석)

**첫 사이클**: 초기 목표가 있으면 그것을 사용. 없으면 아래 자동 탐색 수행.
**이후 사이클**: 이전 BUILD/TEST 결과를 반영하여 다음 작업을 자동 탐색.

자동 탐색 우선순위 (위에서부터 처리):

1. **CI/테스트 오류** — `pytest tests/ -q --ignore=backend` 실행, collection 에러 포함 즉시 수정
2. **Phase A 필수 항목** — 위 "Phase A 우선 수정 항목" 목록에서 미완료 항목 선택
3. **스펙 대비 미구현** — `agents/specs/*.md`와 실제 코드 비교, 누락 기능 식별
4. **mock → 실제 구현** — mock으로만 테스트하는 영역을 실제 라이브러리 호출로 전환
5. **GUI 상태 누락** — 빈 첫 화면, 프로그레스 없음, 성공/실패 시각 피드백 미구현
6. **DX 이슈** — 에러 메시지 불친절, 포맷 미검증, 설치 실패 경로
7. **integration test 부재** — 단위 테스트만 있고 통합 테스트가 없는 파이프라인 연결
8. **코드 품질** — 에러 핸들링 미흡, edge case 미처리, 타입 힌트 누락
9. **성능/안정성** — 대용량 입력 처리, 메모리 관리, 타임아웃

탐색 결과로 **다음 작업 1개**를 선정하고 간결하게 기술한다.
개선점이 없으면 사용자에게 보고하고 루프를 종료한다.

### 2단계: PLAN

1. 선정된 작업에 해당하는 스펙(`agents/specs/*.md`)만 읽는다 (이미 컨텍스트에 있으면 생략)
2. 작업을 3개 이하의 단위로 분해, 각 단위마다 검증 명령어 정의
3. `_plan.md`에 `## 사이클 N` 아래 기록

### 3단계: BUILD — 서브에이전트 위임

| 모듈 | 서브에이전트 |
|------|------------|
| 파일 로딩·지오메트리 분석·CAD 입력 | analyzer |
| 표면 수리·변환·리메쉬·AI fix | preprocessor |
| Tier 선택·파라미터 결정·재시도 전략 | strategist |
| 메쉬 생성·Tier 구현·FoamCaseWriter·멀티솔버 출력 | generator |
| 품질 검증·checkMesh·Hausdorff·NativeMeshChecker | evaluator |
| Qt GUI·drag-drop·progress·상태 표시·PyVista | desktop |
| CLI 진입점·에러 메시지·설치·DX 개선 | generator (cli/) |
| 파티셔너·시각화·BC 분류기·utils | evaluator 또는 generator |

여러 모듈에 걸치는 작업은 관련 서브에이전트를 순서대로 사용한다.
독립적인 모듈은 병렬 위임 가능.

### 4단계: TEST

```bash
# 표준 실행 (backend 제외)
pytest tests/ -q --ignore=backend

# GUI 테스트 (헤드리스 환경)
pytest tests/test_qt_app.py -v -k "not requires_display"

# 전체 (CI 환경 동일)
pytest tests/ -q --ignore=backend --ignore=backend/integration
```

- 실패 시 해당 서브에이전트를 재호출하여 수정 (최대 3회)
- 3회 실패 → `_blocked.md`에 기록 후 다음 사이클로 진행

**TEST 통과 후**: 사이클 결과를 `_plan.md`에 기록 → **1단계 ASSESS로 복귀**

---

## 사이클별 기록 형식

```markdown
## 사이클 N — [작업 제목]
**ASSESS**: [탐색 결과 — 무엇을 왜 선정했는지]
**PLAN**: [작업 단위 목록]
**BUILD**: [위임한 서브에이전트, 수정한 파일]
**TEST**: [테스트 결과 — N passed, M failed]
**상태**: ✅ 완료 / ❌ blocked
```

---

## 제약

- 서브에이전트 스펙(`agents/specs/*.md`)을 읽지 않고 코드를 작성하지 않는다
- 한 단위에서 파일 5개 이상 동시 수정 금지
- 테스트 없이 다음 사이클로 넘어가지 않는다
- 한 사이클에서 너무 큰 작업을 잡지 않는다 (30분 이내 완료 가능한 크기)
- 매 사이클 TEST 후 현재 전체 테스트 수를 사용자에게 보고한다
- **Linux 우선**: Windows .exe 관련 코드는 Phase C까지 건드리지 않는다
- **FoamCaseWriter는 선택 기능이 아님**: Generator 완성 시 케이스 파일 생성까지 포함
