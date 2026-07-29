---
type: moc
status: active
updated: 2026-07-26
stability: measured
source_paths: [docs/references/literature, ROADMAP.md]
tags: [research, literature, moc]
---

# 연구 MOC

- [[Literature Workflow and Research State|문헌 워크플로와 연구 상태]] — evidence matrix, 카드, phase 순서
- [[2026-07-26 문헌 읽기와 다음 개선 카드]] — 공개 원문에서 확인한 근거, 초록만 확인한 항목, 다음 진단 카드와 DOI 대기 목록
- [[Native Tet]] — protected-CDT/Wild 분리, boundary transaction, 품질 lane
- [[Native Hex]] — 정직한 census, transition matching, feature provenance
- [[Native Poly]] — entity-classified dual과 구조적 repair
- [[Native Tri and Quad|Native Tri와 Quad]] — guarded operator, sizing, shell, field 진단
- [[Testing and Benchmarks|테스트와 벤치마크]] — 카드를 판정하는 측정 기반

공통 규칙은 **측정 먼저**다. 새 메커니즘은 카드 하나·메커니즘 하나·기본 OFF로 시작한다. 효과가 없으면 부정적 결과를 기록하고 코드는 제거한다. 병렬화는 마지막 phase다.
