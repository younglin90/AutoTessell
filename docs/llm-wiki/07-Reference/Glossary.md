---
type: glossary
status: active
updated: 2026-07-26
stability: implemented
source_paths: [CLAUDE.md, ROADMAP.md, core/schemas.py]
tags: [glossary]
---

# 용어집

- **BL** — boundary layer. Wall-normal prism/hex/poly transition cell
- **boundary face key** — tet boundary topology를 나타내는 canonical sorted vertex triple
- **card** — 명시적 측정·합격 기준을 가진 하나의 문헌 근거 메커니즘
- **CDT** — constrained Delaunay tetrahedralization. 입력 edge 존재보다 강한 계약
- **cell census** — hex, prism, tet, 기타 cell의 실측 개수와 비율
- **degen** — 이름 붙인 checker/tolerance에서의 degenerate cell 수
- **entity classification** — dual 생성 전 primal boundary를 patch/type/interface provenance로 분류
- **FSL wedge** — native-tet hard corpus의 flat all-surface sliver/wedge
- **hard-12** — canonical 12형상 volume benchmark. 정확한 조건이 결과 일부
- **harness** — 엔진을 감싸는 bounded generator/evaluator 또는 diagnostic driver
- **invariant** — 품질·성능과 교환할 수 없는 조건
- **L1/L2/L3** — surface repair, remesh, 고비용 AI/reconstruction 전처리 등급
- **native-first** — AutoTessell 소유 구현·계약을 routing에서 우선하는 정책
- **PLC** — protected CDT의 clean constrained input인 piecewise linear complex
- **polyMesh** — OpenFOAM의 points/faces/owner/neighbour/boundary topology
- **provenance** — output entity와 source file/patch/feature/BL layer의 지속적 mapping
- **ScoreCHE/QHED** — 정직한 hex-dominant 보고를 위한 cluster/distribution metric
- **star-shaped validity** — poly cell에 일관된 positive signed subtet을 만드는 kernel point가 존재하는 성질
- **strict xfail** — 알려진 한계가 예상 밖으로 통과하거나 동작이 변하면 크게 알리는 test
- **surface preservation** — pre-meshing surface의 topology·geometry·semantic 보존
- **transactional local operation** — influence region 전체를 시뮬레이션·검증한 뒤 atomic commit/rollback하는 연산
- **Wild engine** — imperfect triangle soup용 epsilon-tolerant tet 경로. Protected CDT와 보장이 다름
