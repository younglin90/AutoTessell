---
type: subsystem
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/utils/predicates.py, core/utils/predicates_staged.py, core/utils/predicates_exact.py, core/utils/_shewchuk/__init__.py, core/utils/_shewchuk/predicates.c]
tags: [predicates, shewchuk, robustness]
---

# 강건 기하 술어

Orientation과 in-sphere 부호 판정은 단계적으로 수행한다.

1. 오차 bound가 있는 빠른 double
2. 가능한 플랫폼에서 `numpy.float128`/extended precision
3. bundled Shewchuk adaptive C predicate
4. native code를 못 쓸 때 Python exact-rational fallback

`predicates_staged.py`는 scalar/batch `orient3d_staged`, `insphere_staged`를 제공한다. Batch는 흔한 double 경로를 vectorize하고 uncertain row만 scalar cascade로 보낸다. `predicates_exact.py`는 `Fraction` 기반 reference다.

`core/utils/_shewchuk`의 public-domain C 코드는 `ctypes`로 로드된다. Expansion arithmetic이 암묵적 FMA contraction을 허용하지 않으므로 self-build command에 `-ffp-contract=off`가 있다.

## 계약 경계

- Exact predicate는 명시적으로 표현된 floating-point 입력의 부호를 보장한다. 반올림 전 수학적 구성점을 보장하지는 않는다.
- Intersection/projection 같은 constructed point에는 indirect predicate 또는 snap-once-and-reaudit가 필요하다.
- Python fast-stage 상수는 Shewchuk 논문의 certified filter와 자동으로 동등하지 않다.
- 인자 순서와 sign convention도 API 일부다. Near-degenerate regression은 exact reference와 비교해야 한다.

이 술어층은 native-tri fold-over, tet Delaunay/recovery/legalization, shell containment와 geometry audit의 기반이다.
