# Codex 독립 세션 프롬프트

**프로젝트**: Auto-Tessell (CAD/메쉬 → OpenFOAM polyMesh 자동 생성)  
**목표**: v0.3.1 E2E 테스트 36% 성공률 진단 및 개선 시나리오 작성  
**산출물**: `E2E_FAILURE_ANALYSIS.md` + Quick wins 3-5개  

---

## 📍 현황 (한눈에)

### 프로젝트 상태
```
✅ 회귀 테스트: 98.8% (1016/1028 통과)
✅ 코어 엔진: 9-Tier 메시 생성 + 5-Agent 오케스트레이션 완성
❌ E2E 테스트: 36% (9/25 통과) ← 문제

구조:
- core/ (14.5k LOC): Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator
- cli/ (CLI 인터페이스)
- tests/ (1028+ 회귀 + E2E 벤치마크)
- desktop/, backend/ (Phase 2, 현재 미포함)
```

### 핵심 문제
```
E2E 성공률이 36%에 불과한 이유?

가설 1: 타임아웃 (120s limit)
  - 일부 복잡한 형상이 120초 초과
  - 파라미터 조정으로 30-50% 단축 가능?

가설 2: 품질 실패 (Hausdorff 거리)
  - Strategist → Generator 파라미터 드리프트
  - Quality threshold 미충족

가설 3: 메시 무효 (NaN 좌표, self-intersection 등)
  - Preprocessor 또는 Generator 버그
  - 엣지 케이스 처리 실패

가설 4: 데이터 버전 불일치
  - v0.3.1 기준(9/25) vs v0.4 기준(15/26) 혼재?
```

---

## 🎯 작업 범위

### 1단계: 데이터 수집 및 분류

**파일 위치:**
```
- E2E_TEST_RESULTS.json (테스트 결과 메타)
- BENCHMARK_ANALYSIS_DETAILED.md (상세 분석 문서)
- v0.4_FINAL_RESULTS.md (최신 벤치마크)
- PERFORMANCE_REPORT.json (성능 데이터)
- scripts/benchmark_test_cases.py (테스트 러너)
- git log (v0.3.1 → v0.4 전환점)
```

**작업:**
- [ ] 25개 E2E 테스트 케이스 목록 추출
- [ ] 각 케이스별: 테스트명, 상태(PASS/FAIL), 소요시간, 메모리, 최종 Tier
- [ ] 실패 원인 분류:
  - **TIMEOUT**: 소요시간 ≥ 120s
  - **QUALITY**: Hausdorff 거리 > threshold
  - **INVALID**: NaN, non-manifold, self-intersection
  - **OTHER**: 파일 로드 실패, 권한 문제 등

### 2단계: 실패 원인 심화 분석

**분석 대상 (9개 실패 케이스):**
- 정확한 형상명 (예: `sphere_radius_0.5`, `airfoil_naca0012`)
- 실패 직전까지 진행한 단계 (예: L1 repair 통과 → L2 remesh 실패)
- 에러 메시지 / 로그
- 에러 발생 시점 (Preprocessor vs Strategist vs Generator)

**근거 문서 읽기:**
- `IMPROVEMENTS_V0.4.md`: 최근 개선사항 (2D 감지, open boundary, 극단적 형상)
- `CURRENT_STATUS_AND_BACKLOG.md`: P0-P3 로드맵
- git 커밋 메시지 (v0.3.1 → v0.4)

### 3단계: 개선 시나리오 작성

**각 시나리오에 대해:**
```
이름: "Timeout +30s"
원인: 5개 케이스가 120s 초과
현재: timeout (FAIL)
제안: timeout limit을 150s로 증가
예상 효과: 9/25 → 14/25 (56% → 60%)
구현 노력: 15분 (Makefile + test runner)
위험도: 낮음 (테스트만 영향, 런타임 변경 없음)
```

**Quick wins (즉시 구현 가능, 30분 이내):**
1. Timeout 조정
2. 파라미터 threshold 완화
3. L2 remesh 강제 (open boundary)
4. 극단적 형상 셀 크기 조정
5. ...

### 4단계: 최종 보고서 작성

**산출물: `E2E_FAILURE_ANALYSIS.md`**
```
# E2E 테스트 실패 분석 (v0.3.1)

## 요약
- 총 25개 케이스
- 성공: 9개 (36%)
- 실패: 16개 (64%)

## 실패 원인별 분포
| 원인 | 케이스 수 | % |
|------|---------|---|
| TIMEOUT | 5 | 31% |
| QUALITY | 4 | 25% |
| INVALID | 0 | 0% |
| OTHER | 7 | 44% |

## 상세 분석

### TIMEOUT (5개)
- very_thin_disk_0.01mm (90s → 180s 필요)
- ...

### QUALITY (4개)
- hemisphere_open (Hausdorff 0.15 vs threshold 0.10)
- ...

### OTHER (7개)
- airfoil_naca0012: L2 remesh 실패 (feature edge 감지 이슈)
- ...

## Quick wins (즉시 구현)

### 1. Timeout +30s
예상 효과: 9/25 → 14/25 (60%)
노력: 15분

### 2. L2 remesh 강제 (open boundary)
예상 효과: 14/25 → 17/25 (68%)
노력: 30분

### 3. Complexity 파라미터 조정
예상 효과: 17/25 → 20/25 (80%)
노력: 1시간

## 다음 단계
1. Quick wins 우선순위 (즉시 vs 단기)
2. 각 개선별 구현 계획
3. E2E 테스트 재검증
```

---

## 🔍 구체적 지시사항

### Codex 실행 명령어

```bash
# Codex 시작
codex --project /path/to/AutoTessell

# 또는 프롬프트 직접 입력
```

### Codex 세션에 붙여넣을 프롬프트

```
Auto-Tessell 프로젝트 E2E 테스트 진단 작업.

현황:
- 프로젝트: CAD/메쉬 → OpenFOAM polyMesh 자동 생성 CLI
- 코어: 9-Tier 메시 생성, 5-Agent 오케스트레이션 (완성)
- 회귀 테스트: 98.8% (1016/1028)
- 문제: E2E 테스트 36% (9/25) ← 원인 불명

작업 (PHASE 1):
1. E2E_TEST_RESULTS.json 파싱 → 25개 케이스 목록 추출
2. 각 케이스별 상세 정보 수집:
   - 테스트명, 상태, 소요시간, 최종 Tier
   - 실패 원인 분류 (TIMEOUT/QUALITY/INVALID/OTHER)
3. 실패 케이스 심화 분석:
   - 어디서 실패했는가? (Preprocessor/Strategist/Generator)
   - 왜 실패했는가? (구체적 에러 메시지)
   - 어떤 형상인가? (복잡도, 특수성)
4. 개선 시나리오 작성 (Quick wins 3-5개):
   - 이름, 원인, 제안, 예상 효과, 노력, 위험도
5. 최종 보고서 작성 (E2E_FAILURE_ANALYSIS.md)

근거 문서:
- E2E_TEST_RESULTS.json (테스트 메타)
- BENCHMARK_ANALYSIS_DETAILED.md (상세 분석)
- v0.4_FINAL_RESULTS.md (최신 결과)
- PERFORMANCE_REPORT.json (성능 지표)
- IMPROVEMENTS_V0.4.md (최근 개선사항)
- CURRENT_STATUS_AND_BACKLOG.md (프로젝트 상태)
- scripts/benchmark_test_cases.py (테스트 러너)
- git log (v0.3.1 → v0.4 전환점)

산출물:
- E2E_FAILURE_ANALYSIS.md (상세 분석 + 개선 시나리오)
- 구체적 Quick wins 3-5개 (이름/원인/제안/효과/노력)

목표:
- 36% 성공률의 근본 원인 파악
- 70%+ 성공률 달성 가능성 검증
- 즉시 구현 가능한 개선 항목 식별
```

---

## 📋 체크리스트

Codex 시작 후 이 작업을 순서대로 진행하세요:

- [ ] 25개 테스트 케이스 목록 추출
- [ ] 각 케이스별 상태 + 소요시간 + Tier 수집
- [ ] 9개 실패 케이스 분류 (TIMEOUT/QUALITY/INVALID/OTHER)
- [ ] 각 분류별 심화 분석 (에러 로그, 실패 지점)
- [ ] 개선 시나리오 5개 작성
- [ ] E2E_FAILURE_ANALYSIS.md 작성

---

## 🚀 시작 방법

### 방법 1: 터미널에서 직접 입력

```bash
# 프로젝트 디렉토리로 이동
cd /home/younglin90/work/claude_code/AutoTessell

# Codex 시작
codex --project .

# 또는 (프롬프트 자동 로드)
codex rescue
```

### 방법 2: Codex 독립 웹 UI

```bash
# Codex 웹 UI 접속
# http://localhost:8000 (기본 포트)
```

---

**작성**: 2026-04-13  
**준비 상태**: ✅ 완료  
**다음**: Codex 실행 → 위 프롬프트 복사/붙여넣기 → PHASE 1 진행
