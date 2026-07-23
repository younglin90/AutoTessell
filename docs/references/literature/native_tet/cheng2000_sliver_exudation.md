# Cheng et al. — Sliver Exudation (2000)

**DOI:** `10.1145/355483.355487`  
**Pages:** 883–904 (JACM, Vol.47 No.5)  
**Status:** FULL_READ (user-provided PDF: `C:/Users/user/Downloads/cheng2000.pdf`).

## 핵심 정리

- 목표는 임의 Delaunay triangulation에서 **sliver**를 억제하는 것.
- 핵심 아이디어는 **가중치 조정(weight pumping)** 을 통해 weighted Delaunay triangulation에서 sliver를 제거하는 것이다.
- 슬라이버 제거가 잘 동작하려면 ratio-property 계열의 기하 조건이 필요하다.
- 증명은 조건부 정리 기반이며, 실제 파이프라인에서는 강한 입력 사전조건 체크가 필수.

## Native Tet 적용 포인트

- 지금은 단기 프로덕션 경로의 핵심 기법으로는 부적합, 대신 **장기 sliver 강화 경로**로 큐잉.
- 현재 엔진에서 바로 도입하려면 다음이 필요:
  - ratio-property/spacing 사전 검사
  - 경계 보호/PLC/소프 분기와의 API 분리
  - weighted 단계와 보간/검증 단계의 원자적 롤백

## 구현 제약

- 이 논문은 PLC 품질 보강 단계를 대체하지 않으며, 수렴 성능/종결성은 입력 가정에 민감하다.
- 현재 `native_tet`에서는 `TET-SLIVER-0` 형태의 연구 카드로 유지(기능 플래그 + 충분한 선행 게이트 후 활성화).

