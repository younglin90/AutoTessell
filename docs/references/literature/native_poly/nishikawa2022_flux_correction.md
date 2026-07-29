# Nishikawa 2022 - A Flux Correction for Finite-Volume Discretizations

## 서지 및 검증

- Hiroaki Nishikawa, *A Flux Correction for Finite-Volume Discretizations: Achieving Second-Order Accuracy on Arbitrary Polyhedral Grids*, Journal of Computational Physics 462 (2022), 111481.
- DOI: `10.1016/j.jcp.2022.111481`.
- 상태: `FULL_READ` (27/27쪽, 2026-07-27). Elsevier author manuscript이며 첫 페이지의 Version of Record 링크와 원고 제목을 시각 검증했다. 보관본: `papers/pdf/55_nishikawa_2022_fv_flux_correction.pdf`.

## 핵심 결과

cell-centered single-flux-per-face finite volume은 non-planar quadrilateral face에서 자동으로 2차 정확도를 얻지 못한다. 저자는 face를 삼각분할하고, 기존 one-point flux에 flux-gradient correction을 더해 선형 flux 적분을 정확하게 만든다.

face `jk`의 triangle `T`와 triangle centroid `x_T`, flux point `x_jk`, scaled normal `n_T`에 대해 correction matrix는

`S_jk = (1 / A_jk) sum_T n_T (x_T - x_jk)^T`

이고, correction은 인접 두 지점의 flux gradient 평균과의 double contraction으로 쓴다.

`delta Phi_jk = 0.5 (grad F_j + grad F_k) : S_jk`.

이 항은 face별로 `S_jk`를 미리 저장하면 기존 numerical flux에 더하는 작은 추가 연산이다. 그러나 correction만으로는 충분하지 않다. non-planar face를 가진 control volume은 정의가 유일하지 않으므로, **같은 face triangulation에 일관된 control-volume formula**를 써야 한다. 본문의 irregular prism 실험은 baseline만, correction만, volume formula만 각각 1차이고, correction+consistent volume의 조합에서만 2차가 됨을 보인다.

## 적용 범위와 제한

- 논문의 직접 대상은 mesh generator가 아니라 Euler 계열 FV solver adapter다. mesh가 inverted, non-manifold, surface-inaccurate하거나 face pairing이 실패해도 이 correction이 이를 고치지 않는다.
- correction matrix는 face triangulation에 의존한다. export/solver가 어떤 diagonal과 face area/centroid convention을 쓰는지 provenance로 고정하지 않으면 재현성이 없다.
- viscous/diffusion term의 직접 보정에는 보통 얻기 어려운 2차 미분이 필요할 수 있다. 본문은 hyperbolic formulation을 제외한 일반 viscous solver 구현을 future work로 남긴다.
- shock/discontinuity에서는 limiter가 필요하고, 강하게 제한되면 correction이 사라질 수 있다.

## AutoTessell 판정

이 논문은 `POLY-FVERR-PLANAR1`의 위험 평가를 확증한다. warpage가 있는 dual face를 geometry quality gate로 통과시켜도 OpenFOAM 계열 single-point flux의 2차 정확도는 보장되지 않는다.

- 우선순위는 생성 경로의 face planarity/triangulation provenance report와 warpage gate다. 이 논문을 이유로 invalid poly cell 또는 warped face를 허용하지 않는다.
- 별도 solver-adapter 연구 카드 `POLY-FV-FLUXCORR1`는 manufactured-solution order test, export된 face triangulation 고정, consistent volume/centroid convention 일치가 모두 준비된 뒤에만 시작한다. 기본 generator와 checker의 합격 판정은 변경하지 않는다.
