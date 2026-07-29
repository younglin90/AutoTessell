---
type: index
status: active
updated: 2026-07-26
stability: contract
source_paths: [docs/llm-wiki]
tags: [catalog]
---

# 전체 문서 색인

## 지식 지도

- [[Architecture MOC|아키텍처 MOC]] — 시스템 구성과 실행 흐름
- [[Engines MOC|엔진 MOC]] — 메싱 엔진과 출력 계약
- [[Verification MOC|검증 MOC]] — 합격 판정, 지표, 테스트 근거
- [[Research MOC|연구 MOC]] — 문헌 기반 개발 상태

## 아키텍처

- [[System Overview|시스템 개요]] — 제품 경계와 5단계 코어
- [[Pipeline Lifecycle|파이프라인 생명주기]] — 한 작업의 전체 실행 순서
- [[Data Contracts|데이터 계약]] — 단계 사이를 오가는 Pydantic 모델
- [[Native-First Routing|Native-first 라우팅]] — tier 선택과 fallback 의미

## 엔진

- [[Surface Stack|표면 처리 스택]] — reader, 진단, L1/L2/L3 전처리
- [[Native Tri and Quad|Native Tri와 Quad]] — 트랜잭션 tri 루프와 quad 연구
- [[Native Tet]] — tet 파이프라인, 회복, 국소 연산, 품질 가드
- [[Native Hex]] — Cartesian/octree, snap, transition matching, census
- [[Native Poly]] — tet-to-dual, entity provenance, star validity
- [[Boundary Layers|경계층]] — native BL, tet 세분화, poly transition

## 품질과 검증

- [[Evaluator and Quality Gates|평가기와 품질 게이트]]
- [[Surface Preservation Invariant|표면 보존 불변식]]
- [[Robust Predicates|강건 기하 술어]]
- [[Testing and Benchmarks|테스트와 벤치마크]]

## 인터페이스와 배포

- [[CLI and Desktop|CLI와 데스크톱]]
- [[Web Service and SaaS|웹 서비스와 SaaS]]
- [[IO and Exports|입출력과 내보내기]]

## 개발·연구·참조

- [[Build and Dependencies|빌드와 의존성]]
- [[Known Failure Modes|알려진 실패 유형]]
- [[Repository Map|저장소 지도]]
- [[Literature Workflow and Research State|문헌 워크플로와 연구 상태]]
- [[2026-07-26 문헌 읽기와 다음 개선 카드]]
- [[Environment Flags|환경변수 플래그]]
- [[Source Map|소스 지도]]
- [[Contradictions and Open Questions|문서 불일치와 열린 질문]]
- [[Glossary|용어집]]
- [[Wiki Maintenance Contract|위키 유지보수 계약]]
