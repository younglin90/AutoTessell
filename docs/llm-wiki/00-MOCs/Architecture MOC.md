---
type: moc
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/pipeline/orchestrator.py, core/schemas.py]
tags: [architecture, moc]
---

# 아키텍처 MOC

- [[System Overview|시스템 개요]] — 제품 경계와 서브시스템 책임
- [[Pipeline Lifecycle|파이프라인 생명주기]] — 입력부터 판정까지
- [[Data Contracts|데이터 계약]] — agent 사이의 모델
- [[Native-First Routing|Native-first 라우팅]] — tier 선택과 fallback
- [[Repository Map|저장소 지도]] — 디렉터리별 책임
- [[Build and Dependencies|빌드와 의존성]] — native·optional runtime 경계

아키텍처 중심은 개별 mesher가 아니라 `PipelineOrchestrator`다. 이 객체가 분석, 전처리, 전략, 생성, 선택적 경계층, 평가, fidelity, 보고, 재시도와 단계별 산출물 저장을 조율한다.
