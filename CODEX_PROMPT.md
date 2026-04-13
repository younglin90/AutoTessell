# Codex 작업 프롬프트: Auto-Tessell v0.3.1 개선

## 🎯 미션

Auto-Tessell 프로젝트의 **5대 개선 영역**을 진단·해결.
현재: v0.3.1 (회귀 테스트 98.8%, E2E 테스트 36% 실패)
목표: v0.4 (E2E 성공률 70%+, 아키텍처 명확화)

---

## 📊 현황 분석

### 프로젝트 상태
- ✅ 코어 엔진: 9-Tier 메시 생성 + 5-Agent 오케스트레이션 완성
- ✅ 회귀 테스트: 1016/1028 통과 (98.8%)
- ⚠️ E2E 테스트: 9/25 통과 (36%) ← **문제 1번**
- ⚠️ 제품 방향성: CLI/Desktop/Web 3개 트랙 분산
- ⚠️ 코드 중복: Generator 9개 Tier 각각 3-5KB

### 핵심 문제
```
문제 1: E2E 성공률 36% (Draft quality)
  원인 추정:
  - 타임아웃 (120s): 일부 형상 >120s 소요
  - 파라미터 드리프트: Strategist → Generator 불일치
  - 엣지 케이스: 회귀 테스트에 없는 케이스
  - 품질 검증 실패: Hausdorff 거리 threshold 미충족

문제 2: 아키텍처 분산
  - core/ (엔진): 5 agents, 14.5k LOC, 98.8% tested
  - desktop/ (UI): 2 버전 (Godot + Qt) 미통합
  - backend/ (Web): 별도 task queue, auth 없음
  → 제품 방향성 모호, CI/CD 복잡도 높음

문제 3: 코드 조직
  - core/generator/tier*.py 9개 파일 (각 400L)
  - polymesh_writer.py (440L) + case_writer.py (570L)
  - 공통 fallback 로직 산재
  → 네비게이션 어려움, 중복 제거 불가

문제 4: 설정 산재
  - CLAUDE.md (문서) / pyproject.toml (메타) / Makefile (빌드)
  - core/max_cells_policy.py (정책) / core/runtime/ (탐지)
  → 런타임 설정 API 없음, 배포 시 환경 변수 수동 관리

문제 5: 로깅 부족
  - Tier 실패: "fallback" 판정만 기록
  - 어떤 파라미터가 실패했는지 불명확
  - 메트릭 수집 안 함
  → 최적화 불가
```

---

## 🔧 작업 우선순위

### **PHASE 1: E2E 테스트 진단 (최우선)**

**목표**: 36% 성공률의 근본 원인 파악

**작업 범위**:
1. E2E 테스트 분류:
   - `tests/e2e/simple/` (cube, sphere) — 반드시 100% 통과
   - `tests/e2e/medium/` (airfoil, elbow) — 80% 이상 기대
   - `tests/e2e/complex/` (turbine, engine) — 60% 이상 허용
   - `tests/e2e/open/` (inlet/outlet) — 신규, 70% 목표
   - `tests/e2e/timeout/` (이전 timeout 케이스) — 300s 타임아웃

2. 실패 케이스 분석:
   ```bash
   # 각 케이스별로:
   # - 정확한 실패 원인 (타임아웃 vs 품질 실패 vs 메시 무효 vs ...)
   # - 소요 시간 / 메모리 사용량
   # - Hausdorff 거리 vs threshold
   # - 마지막 성공한 Tier
   ```

3. 산출물:
   - `E2E_FAILURE_ANALYSIS.md` (각 실패 케이스 상세 분석)
   - 성공률 개선 시나리오 (타임아웃 +30s vs 파라미터 조정 vs ...)
   - 우선 개선 항목 (Quick wins)

**예상 노력**: 2-3시간

---

### **PHASE 2: 아키텍처 명확화**

**목표**: 제품 방향성 고정, 코드 분산 해결

**작업 범위**:
1. 제품 트랙 선언:
   - Primary: `core+cli` (v0.3-1.0)
   - Secondary: `desktop/godot` 또는 `desktop/qt` (선택)
   - Tertiary: `backend` (v2.0 이후)

2. 파일 구조 재정리:
   ```
   core/generator/tiers/      ← 9개 tier 구현
   core/output/               ← 메시/케이스 I/O
   core/config/               ← 통합 설정
   ```

3. 산출물:
   - `ARCHITECTURE.md` (3-track 선언 및 경계)
   - `TRACK_OWNERSHIP.md` 업데이트
   - 파일 재조직 PR

**예상 노력**: 4-5시간

---

### **PHASE 3: 코드 개선**

**목표**: 중복 제거, 설정 통합, 로깅 강화

**작업 범위**:
1. Tier 기본 클래스 추출:
   ```python
   class TierMesher(ABC):
       @abstractmethod
       def generate(...) → VolumeMesh
   ```

2. 통합 설정 스키마:
   ```python
   class TessellConfig(BaseModel):
       quality_levels: Dict[str, QualityProfile]
       tier_engines: Dict[str, TierConfig]
   ```

3. 실패 컨텍스트 로깅:
   ```python
   @dataclass
   class TierFailure:
       tier_name: str
       params: Dict
       reason: str  # "timeout", "nan_coords", ...
   ```

**예상 노력**: 6-8시간

---

## 📝 구체적 지시사항

### 작업 명령어 (Codex 실행)

```bash
# 방법 1: E2E 실패 원인 분석 (PHASE 1)
/codex:rescue

분석 대상:
- tests/e2e/ 전체 케이스 (25개)
- 각 케이스별 실패 원인 분류
- 성공률 개선 시나리오 제시

산출물:
- E2E_FAILURE_ANALYSIS.md
- 우선 개선 항목 (Quick wins 3-5개)

# 방법 2: 코드 중복 제거 (PHASE 2)
/codex:rescue

리팩토링 대상:
- core/generator/tier*.py (9개 파일, 3-5KB 각각)
- 공통 fallback 로직 추출

산출물:
- TierMesher 기본 클래스 구현
- 각 Tier 리팩토링 (100L 코드 감소 예상)

# 방법 3: 아키텍처 정리 (PHASE 3)
/codex:rescue

설계 대상:
- 통합 config schema (pyproject.toml + runtime)
- 3-track 분리 (core/cli/desktop/backend)
- 실패 컨텍스트 로깅

산출물:
- core/config/schema.py
- ARCHITECTURE.md 업데이트
```

---

## 🎯 우선 추천: PHASE 1 (E2E 진단)

**Why**: 
- 36% 성공률은 사용자 신뢰도에 직결
- 다른 개선의 기초 (파라미터 조정 근거)
- 타임아웃/품질/메시 무효 중 어떤 게 주범인지 알아야 다음 단계 결정 가능

**Expected Output**:
```
E2E_FAILURE_ANALYSIS.md
├── Summary: 25개 중 9개 실패
├── Breakdown:
│   ├── Timeout (120s): 5개 (timeout +30s 제안)
│   ├── Quality (Hausdorff): 4개 (파라미터 조정 제안)
│   └── Invalid mesh: 0개 (다행)
├── Quick wins (즉시 구현 가능):
│   ├── Timeout +30s → 70% 성공률
│   ├── Complexity threshold 조정 → 80% 성공률
│   └── L2 remesh 강제 → 75% 성공률
└── Next steps: 각 시나리오별 구현 순서
```

---

## 🚀 실행 방법

1. **현재 창에서** `/codex:rescue` 명령 실행
2. **Codex 프롬프트에** 아래 내용 복사:

```
Auto-Tessell v0.3.1 개선 프로젝트.

현황:
- 회귀 테스트: 98.8% (1016/1028)
- E2E 테스트: 36% (9/25)
- 코어 엔진: 9-Tier 메시 생성 + 5-Agent 완성
- 제품 트랙: CLI/Desktop/Web 3개 분산 중

즉시 작업:
1. E2E 테스트 25개 케이스 분석
2. 각 케이스별 실패 원인 분류 (timeout/quality/mesh validity)
3. 성공률 개선 시나리오 (e.g., timeout +30s → 70%)
4. Quick wins 3-5개 (즉시 구현 가능한 개선)

산출물:
- E2E_FAILURE_ANALYSIS.md (상세 분석 + 시나리오)
- 우선 개선 항목 (이름/노력/예상 효과)

근거 문서:
- CURRENT_STATUS_AND_BACKLOG.md
- PLAN.md
- v0.3.1 벤치마크 결과 (최근 커밋 메시지 참고)
```

3. **Codex 출력 검토** → 다음 작업 결정

---

## 📚 참고 문서

```
프로젝트 기초:
- CLAUDE.md (5-Agent 파이프라인, 2-Phase 메싱)
- PLAN.md (v0.1-v3.0 로드맵)
- CURRENT_STATUS_AND_BACKLOG.md (P0-P2 상태 추적)

테스트:
- tests/test_cli.py (E2E 테스트)
- tests/test_*.py (회귀 테스트)
- TEST_COUNTING_POLICY.md (테스트 수 정책)

코드:
- core/pipeline/orchestrator.py (546L, 메인 오케스트레이션)
- core/strategist/tier_selector.py (Tier 선택 로직)
- core/generator/tier*.py (9개 Tier 구현)
```

---

## ✅ 체크리스트

- [ ] E2E 케이스 분류 완료
- [ ] 실패 원인 분석 완료
- [ ] 성공률 개선 시나리오 작성
- [ ] Quick wins 식별
- [ ] Codex 프롬프트로 실행
- [ ] 산출물 검토 후 다음 PHASE 결정

---

**작성**: 2026-04-13  
**상태**: 준비 완료  
**다음**: `/codex:rescue` 실행 → E2E 분석 시작
