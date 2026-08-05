---
type: ledger
status: active
updated: 2026-07-26
stability: working-tree
source_paths: [CLAUDE.md, ROADMAP.md, SPEC.md, products/web/app/app/page.tsx, core/pipeline/orchestrator.py, core/generator/native_tet/mesher.py]
tags: [contradictions, debt, open-questions]
---

# 문서 불일치와 열린 질문

억지로 하나의 매끈한 이야기로 합치지 않고, 서로 다른 근거가 충돌하는 지점을 보존한다.

## 확인된 drift

1. **Roadmap와 엔진 계획서**: Roadmap 앞부분은 native-tet Phase-0b를 unresolved로 서술하지만 통합 계획 후반과 최근 commit은 closure 뒤 FLOW/FSL 작업을 기록한다. 현재 카드 상태는 날짜가 있는 evidence matrix와 Git을 우선한다.
2. **Frontend tier 문구**: SaaS landing은 “5-tier pipeline: geogram → Netgen → snappyHexMesh → pytetwild+MMG”라고 쓰지만 현재 registry에는 훨씬 많은 native/external tier와 다른 순서가 있다.
3. **Version**: Python package는 `1.0.0`, Electron shell은 `1.2.0`, roadmap/spec에는 별도 beta chronology가 있다. 제품 공통 version source가 명확하지 않다.
4. **C++ 수준**: CMake project는 C++17이고 일부 target은 C++23이다. 빌드상 가능하지만 하나의 통일 표준처럼 설명하면 부정확하다.
5. **Native-first와 compatibility dependency**: Native reader가 우선이지만 loader 반환은 여전히 trimesh 객체이고 base package가 trimesh/meshio/PyVista를 요구한다.
6. **Retry 설명**: 기본값은 자동 retry OFF지만 orchestrator는 `once`, `continue`를 구현한다. Generate/evaluate loop가 없다는 설명은 기본 policy에만 해당한다.
7. **실험 기본값**: 개발 계획은 새 mechanism 기본 OFF를 요구하지만 native-tet에는 `*_OFF`로 끄는 역사적 default-on `VVV*`/quality block이 많다. Production/experiment/diagnostic/dead 분류가 필요하다.
8. **Native-tri 제품 상태**: guarded loop, curvature sizing, shell이 구현·테스트됐지만 production Preprocessor/CLI 호출부가 없다.
9. **Poly validity 의미**: Star validity를 측정하고 centroid fallback도 있지만 구조적 non-manifold invalidity가 남을 수 있다. Fallback 완료를 valid cell과 동일시하면 안 된다.
10. **Generic evaluator와 permanent gate**: `report.py`에는 tier/BL별 threshold 완화가 있고 연구 계획은 permanent gate 완화를 금지한다. 서로 다른 계층이지만 UI 용어를 더 명확히 해야 한다.

## 열린 아키텍처 질문

- CLI, Qt, desktop web, SaaS, Strategist가 하나의 engine capability registry를 공유해야 하는가?
- Native-tet flag 중 production default, experiment, diagnostic, historical dead lane은 각각 무엇인가?
- Native-tri는 기존 L2 remesh를 대체하는가, 병렬 제품으로 남는가?
- Census와 matching 진단을 넘어 adaptive hex transition cell의 인증 topology 계약은 무엇인가?
- Placement fallback 뒤에도 star-invalid인 poly dual cell의 구조적 repair는 무엇인가?
- 제품/quality tier별 fidelity는 sampled symmetric distance, accumulated envelope, exact envelope, bijective shell 중 어디까지 요구하는가?
