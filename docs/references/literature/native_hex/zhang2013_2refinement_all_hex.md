# Zhang et al. — A Robust 2-Refinement Algorithm in Octree or Rhombic Dodecahedral Tree Based All-Hexahedral Mesh Generation (2013)

**DOI:** `10.1016/j.cma.2012.12.020`  
**Pages:** 88–100 (CMA, Vol.256)  
**Status:** FULL_READ (user-provided PDF: `C:/Users/user/Downloads/zhang2013.pdf`).

## 핵심 정리

- 2-refinement octree/RD-tree all-hex 파이프라인으로 hanging-node 제거와 국소 전이를 최소 확장(radius-like)으로 제어한다.
- boundary 기반 error function으로 feature를 감지해 국소 정제와 버퍼/코어 구성 후 표면 투영을 수행한다.
- RHOMBIC dodecahedral tree도 함께 실험해 경계/균질성 대체안을 제시한다.
- 이후 pillowing/기하학적 flow/최적화로 품질 개선.

## Native Hex 적용 포인트

- `native_hex/octree.py`의 transition 및 2:1 계열 전이 비교 대상.
- thin region에서의 전환 반경, feature 보존(경계 모서리), 셀 수 증가율, 전환 성공률 비교 벤치.
- 순수 all-hex 주장 대신 **증명 가능한 상태 변수(transition signature, 면 접합, 방향성, 2:1 propagation 반경)** 를 기록.

## 도입 전략

1. 현재 transition 베이스라인과 동일 입력에서 정합성 비교.
2. hanging-node 제거 템플릿을 템플릿 시그니처 기반으로 분류/검증.
3. 경계 투영 실패 시 fallback을 명확히 보고(`HEURISTIC_HEX_FALLBACK`).

