---
type: moc
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/generator, core/preprocessor, core/layers]
tags: [engines, moc]
---

# 엔진 MOC

## 표면

- [[Surface Stack|표면 처리 스택]] — import, 진단, repair, remesh
- [[Native Tri and Quad|Native Tri와 Quad]] — 제품급 표면 엔진 기반과 quad-dominant 연구

## 볼륨

- [[Native Tet]] — all-tet 생성과 가장 깊은 연구 파이프라인
- [[Native Hex]] — Cartesian/adaptive octree hex 생성
- [[Native Poly]] — tet-to-dual과 hex-backed 경로
- [[Boundary Layers|경계층]] — wall-normal layer와 transition

## 공통

- [[Native-First Routing|Native-first 라우팅]] — family, alias, fallback, strict 선택
- [[Evaluator and Quality Gates|평가기와 품질 게이트]] — 생성 후 공통 합격 의미
