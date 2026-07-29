---
type: engine
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/preprocessor/native_tri/operator_loop.py, core/preprocessor/native_tri/bijective_shell.py, core/preprocessor/native_remesh/quad_dominant.py, core/preprocessor/native_remesh/rosy_diagnostic.py]
tags: [native-tri, native-quad, surface-meshing]
---

# Native Tri와 Quad

## Native tri

`native_tri/operator_loop.py`는 legacy L2 remesher의 wrapper가 아니라 독립 제품 엔진의 기반이다. `OperatorTransaction`이 불변형 mesh state를 소유하고 각 local proposal을 commit 또는 rollback한다.

현재 구현:

- `4L/3`보다 긴 edge split
- `4L/5`보다 짧은 edge collapse
- valence/quality 개선 기준 flip
- area-weighted tangential smoothing과 surface reprojection
- link condition, fold-over, exact orientation 검사
- 여러 round orchestration과 state-derived cache
- Dunyach/Frey 계열 오차식의 scalar curvature sizing
- 선택적 bijective-shell checkpoint

`bijective_shell.py`는 source 주위에 linear prism shell을 만들고 orient3d로 환원되는 containment와 normal condition을 검사한다. 이 shell은 최종 sampled Hausdorff보다 강한, edit 순서에 독립적인 domain/correspondence 계약이다.

모듈은 `core.preprocessor.native_tri`에서 export되고 테스트되지만 production Preprocessor나 CLI 호출부는 찾지 못했다. 즉 구현된 인프라이지 아직 연결된 제품 route는 아니다.

## Native quad-dominant

`native_remesh/quad_dominant.py`는 보수적인 quad-dominant lane이다. `rosy_diagnostic.py`에는 4-RoSy orientation field와 multiresolution 진단이 있다. Quad-dominant 엔진은 triangle remainder를 정직하게 보고하고 feature/provenance를 지켜야 하며, 임의 triangle mesh를 quad-dominant라고 이름만 바꾸면 안 된다.
